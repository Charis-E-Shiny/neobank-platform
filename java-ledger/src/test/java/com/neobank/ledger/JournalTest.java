package com.neobank.ledger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;

class JournalTest {

    @Test
    void balancedTwoLegJournalIsAccepted() {
        Journal journal = new Journal("tx-1", List.of(new Posting("alice", -500), new Posting("bob", 500)));
        assertEquals(2, journal.postings().size());
    }

    @Test
    void unbalancedJournalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new Journal("tx-2", List.of(new Posting("alice", -500), new Posting("bob", 400))));
    }

    @Test
    void singleLegJournalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new Journal("tx-3", List.of(new Posting("alice", 100))));
    }

    @Test
    void zeroAmountPostingIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> new Posting("alice", 0));
    }

    @Test
    void blankReferenceIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> Journal.transfer("  ", "alice", "bob", 100));
    }

    @Test
    void transferFactoryRejectsNonPositiveAmounts() {
        assertThrows(IllegalArgumentException.class, () -> Journal.transfer("tx", "alice", "bob", 0));
        assertThrows(IllegalArgumentException.class, () -> Journal.transfer("tx", "alice", "bob", -1));
    }

    @Test
    void postingsAreCopiedAndImmutable() {
        java.util.ArrayList<Posting> legs = new java.util.ArrayList<>(
                List.of(new Posting("alice", -100), new Posting("bob", 100)));
        Journal journal = new Journal("tx-4", legs);
        legs.add(new Posting("mallory", 999));
        assertEquals(2, journal.postings().size());
    }
}
