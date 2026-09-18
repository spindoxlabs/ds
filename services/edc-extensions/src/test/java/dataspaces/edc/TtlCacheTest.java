package dataspaces.edc;

import org.junit.jupiter.api.Test;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The decision caches, and the growth they used to have.
 *
 * <p>Both were {@link java.util.concurrent.ConcurrentHashMap}s holding a
 * per-entry expiry and evicting nothing: a lookup skipped an expired entry and
 * left it in place. Their keys come from the counterparty — a participant
 * identity and scope, a dataset and consumer — so nothing in this connector
 * bounded how many there could be.
 *
 * <p>The membership half of this file is gone with {@code AccessScopeFunction}:
 * dataspace membership is read off the verified credential now, with no call and
 * so nothing to cache. {@code AccessPolicyFunctionsTest} is where it went.
 */
class TtlCacheTest {

    @Test
    void avalueIsReturnedUntilItExpires() {
        var cache = new TtlCache<Boolean>(Duration.ofMinutes(1));
        cache.put("k", true);
        assertEquals(Boolean.TRUE, cache.get("k"));
    }

    @Test
    void anExpiredEntryIsNotReturnedAndIsRemoved() {
        // Removed on the way out, so the common path keeps the map clean without
        // a sweeper thread. Returning it would be the worse bug; leaving it was
        // the one that was there.
        var cache = new TtlCache<Boolean>(Duration.ZERO);
        cache.put("k", true);

        assertNull(cache.get("k"));
        assertEquals(0, cache.size(), "an expired entry must not survive the lookup that skipped it");
    }

    @Test
    void theCacheStopsGrowing() {
        var cache = new TtlCache<Boolean>(Duration.ofMinutes(1), 8);
        for (int i = 0; i < 1000; i++) {
            cache.put("key-" + i, true);
        }
        assertTrue(cache.size() <= 8, "held " + cache.size() + " entries against a limit of 8");
    }

    @Test
    void overflowDropsTheEntryExpiringSoonest() {
        // The one whose loss costs least — it was about to be re-fetched anyway.
        // Dropping an entry is never a decision: the caller re-asks the connector.
        var cache = new TtlCache<Boolean>(Duration.ofMinutes(1), 2);
        cache.put("oldest", true);
        cache.put("newer", true);
        cache.put("newest", true);

        assertNull(cache.get("oldest"));
        assertEquals(Boolean.TRUE, cache.get("newest"));
    }

    @Test
    void overwritingAnExistingKeyDoesNotEvict() {
        var cache = new TtlCache<Boolean>(Duration.ofMinutes(1), 2);
        cache.put("a", true);
        cache.put("b", true);
        cache.put("a", false);

        assertEquals(Boolean.FALSE, cache.get("a"));
        assertEquals(Boolean.TRUE, cache.get("b"), "a refresh must not cost an unrelated entry");
    }

}
