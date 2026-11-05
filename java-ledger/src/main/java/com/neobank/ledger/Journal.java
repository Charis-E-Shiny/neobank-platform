package com.neobank.ledger;

import java.util.List;
import java.util.Objects;

/**
 * A balanced, immutable transaction. The invariant is that postings sum to zero, and the
 * constructor enforces it, so an unbalanced journal cannot be represented.
 *
 * @param reference idempotency key chosen by the caller
 * @param postings  at least two legs whose amounts sum to zero
 */
public record Journal(String reference, List<Posting> postings) {

    public Journal {
        Objects.requireNonNull(reference, "reference");
        if (reference.isBlank()) {
            throw new IllegalArgumentException("reference must not be blank");
        }
        postings = List.copyOf(Objects.requireNonNull(postings, "postings"));
        if (postings.size() < 2) {
            throw new IllegalArgumentException("a journal needs at least two postings");
        }
        long sum = 0;
        for (Posting posting : postings) {
            sum = Math.addExact(sum, posting.amountMinor());
        }
        if (sum != 0) {
            throw new IllegalArgumentException("journal does not balance: net " + sum);
        }
    }

    /** Convenience factory for the common two-leg transfer. */
    public static Journal transfer(String reference, String fromAccount, String toAccount, long amountMinor) {
        if (amountMinor <= 0) {
            throw new IllegalArgumentException("transfer amount must be positive");
        }
        return new Journal(
                reference,
                List.of(new Posting(fromAccount, -amountMinor), new Posting(toAccount, amountMinor)));
    }
}
