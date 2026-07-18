from enum import Enum


class SaleStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PayoutType(str, Enum):
    ADVANCE = "advance"
    FINAL = "final"
    WITHDRAWAL = "withdrawal"
    RECOVERY = "recovery"


class PayoutStatus(str, Enum):
    INITIATED = "initiated"
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
