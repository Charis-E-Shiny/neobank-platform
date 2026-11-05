package com.neobank.ledger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class LedgerTest {

    private static final String SYSTEM = "SYS-CASH-USD";

    private Ledger ledger;

    @BeforeEach
    void setUp() {
        ledger = new Ledger(Set.of(SYSTEM));
        ledger.post(Journal.transfer("dep-1", SYSTEM, "alice", 10_000));
    }

    @Test
    void transferMovesMoneyBetweenAccounts() {
        assertTrue(ledger.post(Journal.transfer("tx-1", "alice", "bob", 2_500)));
        assertEquals(7_500, ledger.balance("alice"));
        assertEquals(2_500, ledger.balance("bob"));
    }

    @Test
    void replayingTheSameJournalIsANoOp() {
        Journal journal = Journal.transfer("tx-1", "alice", "bob", 500);
        assertTrue(ledger.post(journal));
        assertFalse(ledger.post(journal));
        assertEquals(9_500, ledger.balance("alice"));
    }

    @Test
    void reusingReferenceForDifferentJournalIsRejected() {
        ledger.post(Journal.transfer("tx-1", "alice", "bob", 500));
        assertThrows(IdempotencyConflictException.class,
                () -> ledger.post(Journal.transfer("tx-1", "alice", "bob", 900)));
        assertEquals(9_500, ledger.balance("alice"));
    }

    @Test
    void customerCannotOverdraw() {
        assertThrows(InsufficientFundsException.class,
                () -> ledger.post(Journal.transfer("tx-2", "alice", "bob", 10_001)));
        assertEquals(10_000, ledger.balance("alice"));
        assertEquals(0, ledger.balance("bob"));
    }

    @Test
    void systemAccountMayGoNegative() {
        Ledger fresh = new Ledger(Set.of(SYSTEM));
        assertTrue(fresh.post(Journal.transfer("dep-x", SYSTEM, "carol", 100)));
        assertEquals(-100, fresh.balance(SYSTEM));
    }

    @Test
    void ledgerNetTotalStaysZeroAcrossActivity() {
        ledger.post(Journal.transfer("tx-1", "alice", "bob", 1_000));
        ledger.post(Journal.transfer("tx-2", "bob", "carol", 300));
        assertEquals(0, ledger.netTotal());
    }
}
