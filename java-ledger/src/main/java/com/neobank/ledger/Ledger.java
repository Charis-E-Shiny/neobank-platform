package com.neobank.ledger;

import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/**
 * In-memory ledger that enforces the posting rules. Persistence and concurrency control belong to
 * the storage layer (see the SQL schema). This class defines what a valid state transition is.
 *
 * <ul>
 *   <li>Posting is idempotent by reference. Replaying an identical journal is a no-op. Reusing a
 *       reference for a different journal is rejected.</li>
 *   <li>Accounts that are not in {@code overdraftAllowed} (customer accounts) cannot go negative.
 *       System clearing accounts are typically in that set.</li>
 * </ul>
 *
 * <p>Not thread-safe. Wrap access in a lock, or use the database as the source of serialization.
 */
public final class Ledger {

    private final Set<String> overdraftAllowed;
    private final Map<String, Long> balances = new HashMap<>();
    private final Map<String, Journal> journalsByReference = new HashMap<>();

    public Ledger(Set<String> overdraftAllowed) {
        this.overdraftAllowed = Set.copyOf(Objects.requireNonNull(overdraftAllowed, "overdraftAllowed"));
    }

    /**
     * Applies a journal. Returns {@code true} if it was newly applied and {@code false} if an
     * identical journal was already applied.
     *
     * @throws IdempotencyConflictException if the reference was used for a different journal
     * @throws InsufficientFundsException   if the journal would overdraw a customer account
     */
    public boolean post(Journal journal) {
        Journal existing = journalsByReference.get(journal.reference());
        if (existing != null) {
            if (existing.equals(journal)) {
                return false;
            }
            throw new IdempotencyConflictException(journal.reference());
        }

        Map<String, Long> proposed = new HashMap<>();
        for (Posting posting : journal.postings()) {
            proposed.merge(posting.accountId(), posting.amountMinor(), Math::addExact);
        }
        for (Map.Entry<String, Long> change : proposed.entrySet()) {
            String account = change.getKey();
            long next = Math.addExact(balance(account), change.getValue());
            if (next < 0 && !overdraftAllowed.contains(account)) {
                throw new InsufficientFundsException(account, next);
            }
        }

        proposed.forEach((account, delta) -> balances.merge(account, delta, Math::addExact));
        journalsByReference.put(journal.reference(), journal);
        return true;
    }

    public long balance(String accountId) {
        return balances.getOrDefault(accountId, 0L);
    }

    /** Sum of all balances. Always zero for a correct ledger, because every journal is balanced. */
    public long netTotal() {
        return balances.values().stream().mapToLong(Long::longValue).sum();
    }
}
