"""Domain errors. Each class carries the HTTP status the API returns for it."""


class NeobankError(Exception):
    status_code = 422


class NotFoundError(NeobankError):
    status_code = 404


class ConflictError(NeobankError):
    """A request clashes with existing state, e.g. a reused idempotency key."""

    status_code = 409


class LedgerError(NeobankError):
    """A posting rule was violated: invalid amount, unbalanced journal, reserved id."""


class InsufficientFundsError(LedgerError):
    """The source account balance is below the requested amount."""


class CurrencyMismatchError(LedgerError):
    """The request currency does not match the account currency."""
