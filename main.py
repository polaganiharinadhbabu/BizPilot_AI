import os
from decimal import Decimal
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func
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

app = FastAPI(
    title="BizPilot AI API",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True}
)
bearer_scheme = HTTPBearer(auto_error=False)
origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5500")
origins = list(dict.fromkeys([origin, "http://localhost:5500", "http://127.0.0.1:5500"]))
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
def list_customers(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.scalars(select(models.Customer).order_by(models.Customer.id.desc())).all()
    return [{"id": x.id, "name": x.name, "email": x.email, "created_at": x.created_at} for x in rows]

@app.post("/customers", status_code=201)
def create_customer(data: schemas.CustomerInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if db.scalar(select(models.Customer).where(models.Customer.email == data.email.lower())):
        raise HTTPException(status_code=409, detail="Customer email already exists.")
    item = models.Customer(name=data.name.strip(), email=data.email.lower())
    db.add(item); db.commit(); db.refresh(item)
    return {"id": item.id, "name": item.name, "email": item.email, "created_at": item.created_at}

@app.delete("/customers/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.get(models.Customer, customer_id)
    if not item: raise HTTPException(status_code=404, detail="Customer not found.")
    if db.scalar(select(models.Invoice.id).where(models.Invoice.customer_id == customer_id).limit(1)):
        raise HTTPException(status_code=409, detail="Cannot delete a customer who has invoices.")
    db.delete(item); db.commit()
    return {"message": "Customer deleted."}

@app.get("/invoices")
def list_invoices(db: Session = Depends(get_db), user=Depends(get_current_user)):
    rows = db.execute(select(models.Invoice, models.Customer.name).join(models.Customer, models.Invoice.customer_id == models.Customer.id).order_by(models.Invoice.id.desc())).all()
    return [{"id": inv.id, "customer_id": inv.customer_id, "customer_name": name, "amount": float(inv.amount), "status": inv.status, "created_at": inv.created_at} for inv, name in rows]

@app.post("/invoices", status_code=201)
def create_invoice(data: schemas.InvoiceInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not db.get(models.Customer, data.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found.")
    item = models.Invoice(customer_id=data.customer_id, amount=data.amount, status="Pending")
    db.add(item); db.commit(); db.refresh(item)
    return {"id": item.id, "customer_id": item.customer_id, "amount": float(item.amount), "status": item.status}

@app.patch("/invoices/{invoice_id}")
def update_invoice(invoice_id: int, data: schemas.InvoiceInput, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Update an existing invoice without creating a new invoice ID."""
    item = db.get(models.Invoice, invoice_id)
    if not item:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if not db.get(models.Customer, data.customer_id):
        raise HTTPException(status_code=404, detail="Customer not found.")
    item.customer_id = data.customer_id
    item.amount = data.amount
    db.commit()
    db.refresh(item)
    return {"message": "Invoice updated successfully.", "id": item.id, "customer_id": item.customer_id, "amount": float(item.amount), "status": item.status}

@app.patch("/invoices/{invoice_id}/pay")
def mark_invoice_paid(invoice_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    item = db.get(models.Invoice, invoice_id)
    if not item: raise HTTPException(status_code=404, detail="Invoice not found.")
    item.status = "Paid"; db.commit()
    return {"message": "Invoice marked as paid."}
# TASKS
@app.get("/tasks")
def list_tasks(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    query = select(models.Task).order_by(models.Task.id.desc())

    if user.role != "admin":
        query = query.where(
            (models.Task.assigned_to == user.id) |
            (models.Task.assigned_to.is_(None))
        )

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
    user=Depends(get_current_user)
):
    assigned_to = data.assigned_to

    if user.role != "admin":
        assigned_to = user.id
    elif assigned_to is not None and not db.get(models.User, assigned_to):
        raise HTTPException(
            status_code=404,
            detail="Assigned user not found."
        )

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
    user=Depends(get_current_user)
):
    item = db.get(models.Task, task_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Task not found."
        )

    if user.role != "admin" and item.assigned_to not in (None, user.id):
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
    user=Depends(get_current_user)
):
    item = db.get(models.Task, task_id)

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Task not found."
        )

    if user.role != "admin" and item.assigned_to not in (None, user.id):
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
def dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    customers = db.scalar(select(func.count(models.Customer.id))) or 0
    invoices = db.scalar(select(func.count(models.Invoice.id))) or 0
    total = db.scalar(select(func.coalesce(func.sum(models.Invoice.amount), 0))) or Decimal("0")
    paid = db.scalar(select(func.coalesce(func.sum(models.Invoice.amount), 0)).where(models.Invoice.status == "Paid")) or Decimal("0")
    pending = db.scalar(select(func.coalesce(func.sum(models.Invoice.amount), 0)).where(models.Invoice.status != "Paid")) or Decimal("0")
    tasks = db.scalar(select(func.count(models.Task.id))) or 0
    return {"customer_count": customers, "invoice_count": invoices, "task_count": tasks, "total_invoiced": float(total), "paid_total": float(paid), "pending_total": float(pending), "role": user.role}

@app.get("/admin/overview")
def admin_overview(db: Session = Depends(get_db), admin=Depends(require_admin)):
    return {"users": db.scalar(select(func.count(models.User.id)) ) or 0,
            "customers": db.scalar(select(func.count(models.Customer.id))) or 0,
            "invoices": db.scalar(select(func.count(models.Invoice.id))) or 0,
            "tasks": db.scalar(select(func.count(models.Task.id))) or 0}

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
    user=Depends(get_current_user)
):
    item = db.get(models.Invoice, invoice_id)

    if not item:
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
