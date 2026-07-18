from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.enums import PayoutStatus, PayoutType, SaleStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Sale:
    sale_id: str
    user_id: str
    brand: str
    earning: Decimal
    status: SaleStatus = SaleStatus.PENDING
    advance_paid: bool = False
    advance_paid_amount: Decimal = Decimal("0.00")
    finalized: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class UserWallet:
    user_id: str
    withdrawable_balance: Decimal = Decimal("0.00")
    last_withdrawal_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Payout:
    payout_id: str
    user_id: str
    amount: Decimal
    payout_type: PayoutType
    status: PayoutStatus
    sale_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class LedgerEntry:
    entry_id: str
    user_id: str
    amount: Decimal
    entry_type: str
    note: str
    sale_id: Optional[str] = None
    payout_id: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
