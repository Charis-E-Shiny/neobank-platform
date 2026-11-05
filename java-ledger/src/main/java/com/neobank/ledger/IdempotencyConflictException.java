package com.neobank.ledger;

/** Thrown when a reference is reused for a journal that differs from the original. */
public final class IdempotencyConflictException extends RuntimeException {

    public IdempotencyConflictException(String reference) {
        super("reference '" + reference + "' was already used for a different journal");
    }
}
