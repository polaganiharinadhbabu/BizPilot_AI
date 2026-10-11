from getpass import getpass
from sqlalchemy import select
from database import Base, engine, SessionLocal
import models
from security import hash_password

def main():
    Base.metadata.create_all(bind=engine)
    name = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = getpass("Admin password (minimum 12 characters): ")
    confirm = getpass("Confirm password: ")
    if not name or not email:
        raise SystemExit("Name and email are required.")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    with SessionLocal() as db:
        existing = db.scalar(select(models.User).where(models.User.email == email))
        if existing:
            raise SystemExit("That email already exists. Use a different email.")
        user = models.User(name=name, email=email, password_hash=hash_password(password), role="admin", is_active=1)
        db.add(user)
        db.commit()
        print(f"Admin account created for {email}")

if __name__ == "__main__":
    main()
