"""
Wallet and orders schemas.
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class WalletBalanceResponse(BaseModel):
    """Wallet balance response"""
    balance: float
    currency: str
    last_updated: str


class TopupWalletRequest(BaseModel):
    """Request to top up wallet"""
    amount: float = Field(..., gt=0, description="Amount to add")
    payment_method: str = Field(..., pattern="^(crypto|card)$")
    crypto_currency: Optional[str] = Field(None, pattern="^(btc|eth|ltc|doge|usdt_erc20|usdt_trc20)$")


class TransactionResponse(BaseModel):
    """Transaction information"""
    id: int
    type: str
    amount: float
    balance_after: float
    description: str
    created_at: str


class OrderResponse(BaseModel):
    """Order information"""
    id: int
    type: str
    status: str
    amount: float
    description: str
    created_at: str
    completed_at: Optional[str]
