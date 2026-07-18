class PayoutSystemError(Exception):
    """Base exception for payout system errors."""


class ValidationError(PayoutSystemError):
    """Raised when input data is invalid."""


class NotFoundError(PayoutSystemError):
    """Raised when an entity cannot be found."""


class ConflictError(PayoutSystemError):
    """Raised when a business rule is violated."""
