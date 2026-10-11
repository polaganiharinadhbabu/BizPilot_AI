import os
from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import HTTPException, status
from dotenv import load_dotenv

load_dotenv()
password_hash = PasswordHash.recommended()
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except Exception:
        return False

def create_token(user_id: int, role: str) -> str:
    if not JWT_SECRET or JWT_SECRET.startswith("CHANGE_THIS"):
        raise HTTPException(status_code=500, detail="Set a secure JWT_SECRET in backend/.env first.")
    minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "role": role, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    if not JWT_SECRET or JWT_SECRET.startswith("CHANGE_THIS"):
        raise HTTPException(status_code=500, detail="Server authentication is not configured.")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login token.")
