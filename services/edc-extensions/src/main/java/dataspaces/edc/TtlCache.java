package dataspaces.edc;

import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * A short-lived decision cache that cannot grow without limit.
 *
 * <p>Two decision caches in this unit were plain {@link ConcurrentHashMap}s
 * holding an expiry per entry and evicting nothing: a lookup skipped an expired
 * entry but left it in place, so the map only ever grew. Both are keyed on
 * counterparty-supplied values — a participant identity and scope in
 * {@link AccessScopeFunction}, a dataset, consumer and purpose list in
 * {@link ConsentPendingGuard} — so the key space is not bounded by anything this
 * connector controls. A counterparty negotiating for a stream of distinct asset
 * ids is enough to grow the map for the life of the JVM.
 *
 * <p><b>Bounded by construction, and the bound is a constant.</b> Same reasoning
 * as {@code AgreementConsentFunction}'s failure threshold: this exists to remove
 * an unbounded-growth defect, and a setting that lets a deployment raise it to
 * infinity puts the defect back. The limit is far above any realistic working
 * set — the entries live for seconds, so it is reached only by a key space that
 * is being enumerated.
 *
 * <p>Overflow drops the entry expiring soonest, which is the one whose loss
 * costs least: it was about to be re-fetched anyway. Dropping a cache entry is
 * never a decision — the caller re-asks the connector and gets the authoritative
 * answer.
 */
final class TtlCache<V> {

    /**
     * Entries retained before the soonest-expiring one is dropped.
     *
     * <p>1024 short-lived decisions is more than any real dataspace holds at
     * once, and small enough that the overflow scan is irrelevant next to the
     * HTTP call it saves.
     */
    static final int DEFAULT_MAX_ENTRIES = 1024;

    private record Entry<V>(V value, Instant expiresAt) {
        boolean isExpired(Instant now) {
            return now.isAfter(expiresAt);
        }
    }

    private final Duration ttl;
    private final int maxEntries;
    private final Map<String, Entry<V>> entries = new ConcurrentHashMap<>();

    TtlCache(Duration ttl) {
        this(ttl, DEFAULT_MAX_ENTRIES);
    }

    TtlCache(Duration ttl, int maxEntries) {
        this.ttl = ttl;
        this.maxEntries = maxEntries;
    }

    /**
     * The cached value, or {@code null} when absent or expired.
     *
     * <p>An expired entry is removed on the way out, so the common path keeps
     * the map clean without a sweeper thread.
     */
    V get(String key) {
        Entry<V> entry = entries.get(key);
        if (entry == null) {
            return null;
        }
        if (entry.isExpired(Instant.now())) {
            entries.remove(key, entry);
            return null;
        }
        return entry.value();
    }

    void put(String key, V value) {
        if (entries.size() >= maxEntries && !entries.containsKey(key)) {
            evict();
        }
        entries.put(key, new Entry<>(value, Instant.now().plus(ttl)));
    }

    /** Entries currently held, expired ones included. Package-visible for tests. */
    int size() {
        return entries.size();
    }

    /**
     * Make room: drop everything already expired, and if that freed nothing,
     * drop the entry closest to expiring.
     */
    private void evict() {
        Instant now = Instant.now();
        entries.entrySet().removeIf(e -> e.getValue().isExpired(now));
        if (entries.size() < maxEntries) {
            return;
        }
        entries.entrySet().stream()
            .min(Comparator.comparing(e -> e.getValue().expiresAt()))
            .map(Map.Entry::getKey)
            .ifPresent(entries::remove);
    }
}
