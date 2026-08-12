package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.ContractNegotiationPolicyContext;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
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
 */
class TtlCacheTest {

    private static class NoopMonitor implements Monitor {
    }

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

    // ── as the membership check uses it ──────────────────────────────────────

    private static AccessScopeFunction<ContractNegotiationPolicyContext> membership(
        AtomicInteger calls, String answer
    ) {
        var connector = new ConnectorClient("http://ds-connector:30001", b -> true, new NoopMonitor()) {
            @Override
            public JsonNode getJson(String path, Map<String, String> query) {
                calls.incrementAndGet();
                try {
                    return answer == null ? null : new ObjectMapper().readTree(answer);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }
        };
        return new AccessScopeFunction<>(connector, 60L, new NoopMonitor());
    }

    private static ContractNegotiationPolicyContext context() {
        return new ContractNegotiationPolicyContext(
            new ParticipantAgent("did:web:third-party.dataspaces.localhost", Map.of(), Map.of()));
    }

    private static boolean evaluate(
        AccessScopeFunction<ContractNegotiationPolicyContext> function, Object rightValue
    ) {
        return function.evaluate(
            Operator.EQ, rightValue, Permission.Builder.newInstance().build(), context());
    }

    @Test
    void theMembershipDecisionIsCached() {
        var calls = new AtomicInteger();
        var function = membership(calls, "{\"allowed\": true}");

        assertTrue(evaluate(function, "owner:rec:member"));
        assertTrue(evaluate(function, "owner:rec:member"));

        assertEquals(1, calls.get());
    }

    @Tag("rule:A-11")
    @Test
    void anUnreachableConnectorDeniesMembership() {
        var calls = new AtomicInteger();
        assertFalse(evaluate(membership(calls, null), "owner:rec:member"));
    }

    @Test
    void anExpandedScopeOperandIsUnwrappedRatherThanStringified() {
        // `rightValue.toString()` on {"@value": "owner:rec:member"} produces an
        // object dump, which is not a scope any registry knows — so the check
        // failed on exactly the policies that took the expanded path, and failed
        // by denying, silently.
        var calls = new AtomicInteger();
        assertTrue(evaluate(membership(calls, "{\"allowed\": true}"),
            Map.of("@value", "owner:rec:member")));
        assertEquals(1, calls.get(), "the connector must actually be asked, with the unwrapped scope");
    }

    @Tag("rule:A-11")
    @Test
    void anUnreadableScopeOperandDenies() {
        var calls = new AtomicInteger();
        assertFalse(evaluate(membership(calls, "{\"allowed\": true}"),
            java.util.List.of("owner:rec:member", "owner:rec:partner")));
        assertEquals(0, calls.get(), "an operand that cannot be read must not become a question");
    }
}
