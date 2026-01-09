from pydantic import BaseModel, condecimal
from decimal import Decimal
from typing import Optional
from uuid import UUID

class TransactionCreate(BaseModel):
    account_id: UUID
    transaction_type: str
    amount: condecimal(max_digits=18, decimal_places=2)
    currency: Optional[str] = "USD"

class TransactionOut(TransactionCreate):
    transaction_id: UUID
    status: str
    created_at: Optional[str]

    class Config:
        orm_mode = True
