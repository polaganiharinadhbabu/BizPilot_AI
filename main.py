import os
import hashlib
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from decimal import Decimal
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from google.oauth2 import id_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.auth.transport import requests as google_requests

import models, schemas
from database import Base, engine, get_db
from security import hash_password, verify_password, create_token, decode_token
from chatbot import router as chatbot_router

load_dotenv()
Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    connection.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_customers_owner_id ON customers (owner_id)"))
    connection.execute(text("ALTER TABLE invoices ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_invoices_owner_id ON invoices (owner_id)"))

app = FastAPI(
    title="BizPilot AI API",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True}
)
bearer_scheme = HTTPBearer(auto_error=False)
origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5500")
origins = list(dict.fromkeys([origin, "https://polaganiharinadhbabu.github.io", "http://localhost:5500", "http://127.0.0.1:5500"]))
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

app.include_router(chatbot_router)



def user_view(user):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}

def authenticate_user(db: Session, email: str, password: str):
    user = db.scalar(select(models.User).where(models.User.email == email.lower()))
    if not user or not user.password_hash or not verify_password(password, user.password_hash) or not user.is_active:
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Please log in."
        )

    payload = decode_token(credentials.credentials)

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=401,
            detail="Invalid login token."
        )

    user = db.get(models.User, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User account is inactive or missing."
        )

    return user

def require_business_user(user=Depends(get_current_user)):
    return user


def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required.")
    return user

@app.get("/")
def root():
    return {"app": "BizPilot AI", "status": "running", "docs": "/docs"}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok", "database": "connected"}

@app.post("/auth/bootstrap-admin", status_code=201)
def bootstrap_admin(
    data: dict,
    x_bootstrap_secret: str | None = Header(default=None),
    db: Session = Depends(get_db)
):
    # One-time setup endpoint. Keep BOOTSTRAP_SECRET configured only until the
    # first account is created, then remove it from the Render environment.
    configured_secret = os.getenv("BOOTSTRAP_SECRET", "")
    if not configured_secret or not x_bootstrap_secret or not __import__("secrets").compare_digest(x_bootstrap_secret, configured_secret):
        raise HTTPException(status_code=403, detail="Invalid bootstrap secret.")

    if db.scalar(select(models.User.id).limit(1)):
        raise HTTPException(status_code=409, detail="Bootstrap is disabled because a user account already exists.")

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise HTTPException(status_code=422, detail="Enter a valid name.")
    if not isinstance(email, str) or "@" not in email or len(email) > 255:
        raise HTTPException(status_code=422, detail="Enter a valid email.")
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be 12 to 128 characters.")

    user = models.User(
        name=name.strip(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role="admin",
        is_active=1
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Initial admin created. Remove BOOTSTRAP_SECRET from Render now.", "user": user_view(user)}



@app.post("/auth/signup", status_code=201)
def signup(data: dict, db: Session = Depends(get_db)):
    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise HTTPException(status_code=422, detail="Enter a valid name.")
    if not isinstance(email, str) or "@" not in email or len(email) > 255:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    if not isinstance(password, str) or len(password) < 12 or len(password) > 128:
        raise HTTPException(status_code=422, detail="Password must be 12 to 128 characters.")
    email = email.strip().lower()
    if db.scalar(select(models.User.id).where(models.User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = models.User(name=name.strip(), email=email, password_hash=hash_password(password), role="user", is_active=1)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully. You can now sign in.", "user": user_view(user)}


def send_password_reset_email(email: str, reset_url: str):
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", username or "")
    if not all([host, username, password, sender]):
        raise HTTPException(status_code=503, detail="Password reset email is not configured yet. Please contact the administrator.")
    message = EmailMessage()
    message["Subject"] = "Reset your BizPilot AI password"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        "We received a request to reset your BizPilot AI password.\n\n"
        f"Open this one-time link within 30 minutes:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    port = int(os.getenv("SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)


@app.post("/auth/password/forgot")
def forgot_password(data: dict, db: Session = Depends(get_db)):
    email = str(data.get("email", "")).strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    user = db.scalar(select(models.User).where(models.User.email == email, models.User.is_active == 1))
    # Always use the same response for existing and unknown accounts.
    if user:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user.id,
            models.PasswordResetToken.used_at.is_(None)
        ).update({"used_at": datetime.now(timezone.utc)})
        reset = models.PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
        db.add(reset)
        db.commit()
        base_url = os.getenv("PASSWORD_RESET_URL", "https://polaganiharinadhbabu.github.io/BizPilot_AI/reset-password.html")
        reset_url = f"{base_url}?token={raw_token}"
        try:
            send_password_reset_email(user.email, reset_url)
        except Exception:
            db.delete(reset)
            db.commit()
            raise HTTPException(status_code=503, detail="Password reset email could not be sent. Please contact the administrator.")
    return {"message": "If that email belongs to an active account, a password reset link will be sent."}


@app.post("/auth/password/reset")
def reset_password(data: dict, db: Session = Depends(get_db)):
    raw_token = data.get("token")
    new_password = data.get("password")
    if not isinstance(raw_token, str) or len(raw_token) < 20:
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired.")
    if not isinstance(new_password, str) or len(new_password) < 12 or len(new_password) > 128:
        raise HTTPException(status_code=422, detail="Password must be 12 to 128 characters.")
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    reset = db.scalar(select(models.PasswordResetToken).where(
        models.PasswordResetToken.token_hash == token_hash,
        models.PasswordResetToken.used_at.is_(None),
        models.PasswordResetToken.expires_at > datetime.now(timezone.utc)
    ))
    if not reset:
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired.")
    user = db.get(models.User, reset.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="This reset link is invalid or expired.")
    user.password_hash = hash_password(new_password)
    reset.used_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Password updated. You can now sign in."}


@app.post("/auth/login")
def login(data: schemas.LoginInput, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.email, data.password)
    return {"access_token": create_token(user.id, user.role), "token_type": "bearer", "user": user_view(user)}

@app.get("/auth/google-config")
def google_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    return {"client_id": "" if client_id.startswith("YOUR_") else client_id}

@app.post("/auth/google")
def google_login(data: dict, db: Session = Depends(get_db)):
    credential = data.get("credential")
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    if not credential or not client_id or client_id.startswith("YOUR_"):
        raise HTTPException(status_code=400, detail="Google login is not configured. Set GOOGLE_CLIENT_ID in backend/.env.")
    try:
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Google credential could not be verified.")
    email = (info.get("email") or "").lower()
    if not email or not info.get("email_verified"):
        raise HTTPException(status_code=401, detail="A verified Google email is required.")
    google_sub = info.get("sub")
    user = db.scalar(select(models.User).where(models.User.email == email))
    # Google sign-in is allowed only for accounts already created by an admin.
    if not user:
        raise HTTPException(status_code=403, detail="Your account has not been created by an admin yet.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Your account is inactive.")
    if user.google_sub and user.google_sub != google_sub:
        raise HTTPException(status_code=403, detail="This account is linked to a different Google identity.")
    if not user.google_sub:
        user.google_sub = google_sub
        db.commit()
        db.refresh(user)
    return {"access_token": create_token(user.id, user.role), "token_type": "bearer", "user": user_view(user)}

@app.patch("/auth/profile")
def update_my_profile(data: dict, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if set(data) != {"name"}:
        raise HTTPException(status_code=422, detail="Only the profile name can be updated here.")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="Name cannot be empty.")
    user.name = name.strip()[:100]
    db.commit()
    db.refresh(user)
    return user_view(user)

@app.get("/auth/me")
def me(user=Depends(get_current_user)):
    return user_view(user)

@app.get("/admin/users")
def list_users(db: Session = Depends(get_db), admin=Depends(require_admin)):
    users = db.scalars(select(models.User).order_by(models.User.created_at.desc())).all()
    return [user_view(u) | {"is_active": bool(u.is_active), "created_at": u.created_at} for u in users]

@app.post("/admin/users", status_code=201)
def create_user(data: schemas.CreateUserInput, db: Session = Depends(get_db), admin=Depends(require_admin)):
    email = data.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user = models.User(name=data.name.strip(), email=email, password_hash=hash_password(data.password), role=data.role, is_active=1)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_view(user)

@app.patch("/admin/users/{user_id}/status")
def change_user_status(user_id: int, data: dict, db: Session = Depends(get_db), admin=Depends(require_admin)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    active = data.get("is_active")
    if not isinstance(active, bool):
        raise HTTPException(status_code=422, detail="is_active must be true or false.")
    if user.id == admin.id and not active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own admin account.")
    user.is_active = 1 if active else 0
    db.commit()
    return {"message": "Account status updated."}

@app.get("/customers")
def list_customers(db: Session = Depends(get_db), user=Depends(require_business_user)):
    query = select(models.Customer).order_by(models.Customer.id.desc())
    query = query.where(models.Customer.owner_id == user.id)
    rows = db.scalars(query).all()
    return [{"id": x.id, "name": x.name, "email": x.email, "created_at": x.created_at} for x in rows]

@app.get("/customers/{customer_id}/history")
def customer_history(customer_id: int, db: Session = Depends(get_db), user=Depends(require_business_user)):
    customer = db.scalar(select(models.Customer).where(models.Customer.id == customer_id, models.Customer.owner_id == user.id))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")
    invoices = db.scalars(select(models.Invoice).where(models.Invoice.customer_id == customer_id, models.Invoice.owner_id == user.id).order_by(models.Invoice.created_at.desc())).all()
    return {
        "customer": {"id": customer.id, "name": customer.name, "email": customer.email, "created_at": customer.created_at},
        "invoice_history": [{"id": invoice.id, "amount": float(invoice.amount), "status": invoice.status, "created_at": invoice.created_at} for invoice in invoices],
        "invoice_count": len(invoices)
    }

@app.post("/customers", status_code=201)
def create_customer(data: schemas.CustomerInput, db: Session = Depends(get_db), user=Depends(require_business_user)):
    if db.scalar(select(models.Customer).where(models.Customer.email == data.email.lower(), models.Customer.owner_id == user.id)):
        raise HTTPException(status_code=409, detail="Customer email already exists.")
    item = models.Customer(name=data.name.strip(), email=data.email.lower(), owner_id=user.id)
    db.add(item); db.commit(); db.refresh(item)
    return {"id": item.id, "name": item.name, "email": item.email, "created_at": item.created_at}

@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db), user=Depends(require_business_user)):
    item = db.get(models.Customer, customer_id)
    if not item or item.owner_id != user.id: raise HTTPException(status_code=404, detail="Customer not found.")
    if db.scalar(select(models.Invoice.id).where(models.Invoice.customer_id == customer_id, models.Invoice.owner_id == user.id).limit(1)):
        raise HTTPException(status_code=409, detail="Cannot delete a customer who has invoices.")
    db.delete(item); db.commit()
    return {"message": "Customer deleted."}

@app.get("/invoices")
def list_invoices(db: Session = Depends(get_db), user=Depends(require_business_user)):
    query = select(models.Invoice, models.Customer.name).join(models.Customer, models.Invoice.customer_id == models.Customer.id).order_by(models.Invoice.id.desc())
    query = query.where(models.Invoice.owner_id == user.id)
    rows = db.execute(query).all()
    return [{"id": inv.id, "customer_id": inv.customer_id, "customer_name": name, "amount": float(inv.amount), "status": inv.status, "created_at": inv.created_at} for inv, name in rows]

@app.post("/invoices", status_code=201)
def create_invoice(data: schemas.InvoiceInput, db: Session = Depends(get_db), user=Depends(require_business_user)):
    customer = db.get(models.Customer, data.customer_id)
    if not customer or customer.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Customer not found.")
    item = models.Invoice(customer_id=data.customer_id, owner_id=user.id, amount=data.amount, status="Pending")
    db.add(item); db.commit(); db.refresh(item)
    return {"id": item.id, "customer_id": item.customer_id, "amount": float(item.amount), "status": item.status}

@app.patch("/invoices/{invoice_id}")
def update_invoice(invoice_id: int, data: schemas.InvoiceInput, db: Session = Depends(get_db), user=Depends(require_business_user)):
    """Update an existing invoice without creating a new invoice ID."""
    item = db.get(models.Invoice, invoice_id)
    if not item or item.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    customer = db.get(models.Customer, data.customer_id)
    if not customer or (user.role != "admin" and customer.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Customer not found.")
    item.customer_id = data.customer_id
    item.amount = data.amount
    db.commit()
    db.refresh(item)
    return {"message": "Invoice updated successfully.", "id": item.id, "customer_id": item.customer_id, "amount": float(item.amount), "status": item.status}

@app.patch("/invoices/{invoice_id}/pay")
def mark_invoice_paid(invoice_id: int, db: Session = Depends(get_db), user=Depends(require_business_user)):
    item = db.get(models.Invoice, invoice_id)
    if not item or (user.role != "admin" and item.owner_id != user.id): raise HTTPException(status_code=404, detail="Invoice not found.")
    item.status = "Paid"; db.commit()
    return {"message": "Invoice marked as paid."}
# TASKS
@app.get("/tasks")
def list_tasks(
    db: Session = Depends(get_db),
    user=Depends(require_business_user)
):
    query = select(models.Task).order_by(models.Task.id.desc())

    query = query.where(models.Task.assigned_to == user.id)

    rows = db.scalars(query).all()

    return [
        {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "assigned_to": task.assigned_to,
            "created_at": task.created_at
        }
        for task in rows
    ]


@app.post("/tasks", status_code=201)
def create_task(
    data: schemas.TaskInput,
    db: Session = Depends(get_db),
    user=Depends(require_business_user)
):
    assigned_to = user.id

    item = models.Task(
        title=data.title.strip(),
        description=data.description,
        priority=data.priority,
        assigned_to=assigned_to,
        status="Pending"
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "priority": item.priority,
        "assigned_to": item.assigned_to
    }


@app.patch("/tasks/{task_id}")
def update_task(
    task_id: int,
    data: dict,
    db: Session = Depends(get_db),
    user=Depends(require_business_user)
):
    item = db.get(models.Task, task_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Task not found."
        )

    if item.assigned_to != user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot update another user's task."
        )

    allowed_fields = {"title", "description", "priority", "status"}
    invalid_fields = set(data.keys()) - allowed_fields

    if invalid_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid fields: {', '.join(sorted(invalid_fields))}"
        )

    if "title" in data:
        title = data["title"]

        if not isinstance(title, str) or not title.strip():
            raise HTTPException(
                status_code=422,
                detail="Task title cannot be empty."
            )

        item.title = title.strip()

    if "description" in data:
        description = data["description"]

        if description is not None and not isinstance(description, str):
            raise HTTPException(
                status_code=422,
                detail="Description must be text."
            )

        item.description = description

    if "priority" in data:
        priority = data["priority"]

        if priority not in ("Low", "Medium", "High"):
            raise HTTPException(
                status_code=422,
                detail="Priority must be Low, Medium, or High."
            )

        item.priority = priority

    if "status" in data:
        task_status = data["status"]

        if task_status not in ("Pending", "In Progress", "Completed"):
            raise HTTPException(
                status_code=422,
                detail="Invalid task status."
            )

        item.status = task_status

    db.commit()
    db.refresh(item)

    return {
        "message": "Task updated successfully.",
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "priority": item.priority,
        "assigned_to": item.assigned_to
    }


@app.delete("/tasks/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_business_user)
):
    item = db.get(models.Task, task_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Task not found."
        )

    if user.role != "admin" and item.assigned_to != user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot delete another user's task."
        )

    db.delete(item)
    db.commit()

    return {
        "message": "Task deleted successfully.",
        "id": task_id
    }
@app.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user=Depends(require_business_user)):
    customer_query = select(func.count(models.Customer.id))
    invoice_query = select(func.count(models.Invoice.id))
    total_query = select(func.coalesce(func.sum(models.Invoice.amount), 0))
    paid_query = select(func.coalesce(func.sum(models.Invoice.amount), 0)).where(models.Invoice.status == "Paid")
    pending_query = select(func.coalesce(func.sum(models.Invoice.amount), 0)).where(models.Invoice.status != "Paid")
    task_query = select(func.count(models.Task.id))
    customer_query = customer_query.where(models.Customer.owner_id == user.id)
    invoice_query = invoice_query.where(models.Invoice.owner_id == user.id)
    total_query = total_query.where(models.Invoice.owner_id == user.id)
    paid_query = paid_query.where(models.Invoice.owner_id == user.id)
    pending_query = pending_query.where(models.Invoice.owner_id == user.id)
    task_query = task_query.where(models.Task.assigned_to == user.id)
    customers = db.scalar(customer_query) or 0
    invoices = db.scalar(invoice_query) or 0
    total = db.scalar(total_query) or Decimal("0")
    paid = db.scalar(paid_query) or Decimal("0")
    pending = db.scalar(pending_query) or Decimal("0")
    tasks = db.scalar(task_query) or 0
    return {"customer_count": customers, "invoice_count": invoices, "task_count": tasks, "total_invoiced": float(total), "paid_total": float(paid), "pending_total": float(pending), "role": user.role}

@app.get("/admin/overview")
def admin_overview(db: Session = Depends(get_db), admin=Depends(require_admin)):
    total_users = db.scalar(select(func.count(models.User.id))) or 0
    active_users = db.scalar(select(func.count(models.User.id)).where(models.User.is_active == 1)) or 0
    return {"users": total_users, "active_users": active_users, "inactive_users": total_users - active_users}

@app.post("/assistant")
def assistant(data: dict, user=Depends(get_current_user)):
    message = (data.get("message") or "").strip().lower()
    if not message: raise HTTPException(status_code=422, detail="Message is required.")
    if "invoice" in message or "payment" in message:
        answer = "You can review invoice totals and payment status from the Invoices section."
    elif "task" in message:
        answer = "Open Tasks to review your work. You can update a task's status when you make progress."
    elif "customer" in message:
        answer = "Open Customers to review or add customer records."
    else:
        answer = "I can help you navigate customers, invoices, payments, tasks, and dashboard summaries. This starter assistant uses simple rules, not a connected LLM."
    return {"answer": answer, "mode": "rule-based"}

@app.delete("/invoices/{invoice_id}")
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_business_user)
):
    item = db.get(models.Invoice, invoice_id)

    if not item or (user.role != "admin" and item.owner_id != user.id):
        raise HTTPException(
            status_code=404,
            detail="Invoice not found."
        )

    db.delete(item)
    db.commit()

    return {
        "message": "Invoice deleted successfully.",
        "id": invoice_id
    }
