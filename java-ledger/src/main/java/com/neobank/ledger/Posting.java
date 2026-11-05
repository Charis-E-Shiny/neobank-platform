package com.neobank.ledger;

import java.util.Objects;

/**
 * One signed leg of a journal. A positive amount increases the account balance, and a negative
 * amount decreases it. Amounts are in minor units (for example, cents), so no floating point is used.
 */
public record Posting(String accountId, long amountMinor) {

    public Posting {
        Objects.requireNonNull(accountId, "accountId");
        if (accountId.isBlank()) {
            throw new IllegalArgumentException("accountId must not be blank");
        }
        if (amountMinor == 0) {
            throw new IllegalArgumentException("posting amount must be non-zero");
        }
    }
}
