from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class CreateUserInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: Literal["admin", "user"] = "user"

class CustomerInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr

class InvoiceInput(BaseModel):
    customer_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)

class TaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: Literal["Low", "Medium", "High"] = "Medium"
    assigned_to: int | None = None
