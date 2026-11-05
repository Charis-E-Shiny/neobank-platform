package com.neobank.ledger;

/** Thrown when a journal would leave a customer account with a negative balance. */
public final class InsufficientFundsException extends RuntimeException {

    public InsufficientFundsException(String accountId, long resultingBalance) {
        super("account '" + accountId + "' would be left with " + resultingBalance);
    }
}
