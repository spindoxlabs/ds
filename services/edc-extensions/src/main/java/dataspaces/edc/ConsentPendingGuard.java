package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.ContractNegotiationPendingGuard;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiation;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiationStates;
import org.eclipse.edc.connector.controlplane.contract.spi.types.offer.ContractOffer;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.Constraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Parks a provider-side contract negotiation while a data subject decides.
 *
 * <p>GDPR consent is a decision by a natural person, on that person's own
 * timescale. DSP has no representation of a natural person and no notion of a
 * negotiation waiting for one — but it does treat {@code REQUESTED} as an
 * ordinary non-terminal state with no provider deadline, and it defines
 * {@code callbackAddress} for exactly the asynchronous settings this produces.
 * EDC turns that into a supported extension point: a {@link PendingGuard} that
 * marks an entity pending removes it from the state machine until something
 * external clears the flag.
 *
 * <p>This is upstream's own recommendation for this case. In Connector
 * discussion #4460 maintainer <em>jimmarino</em> declined open-ended policy
 * properties such as {@code consentingParty} and pointed at modelling the
 * requirement as an explicit constraint plus a
 * {@link ContractNegotiationPendingGuard} blocking the transition out of
 * {@code REQUESTED}, with the external workflow driving it onward.
 *
 * <h2>Why this replaced a request API</h2>
 *
 * <p>The connector used to expose a cross-participant {@code POST
 * /consent/request} authenticated by a self-asserted header. By the time this
 * guard runs, EDC has already established who is asking — from a DCP-verified
 * credential presentation — and put it in
 * {@link ContractNegotiation#getCounterPartyId()}. The negotiation *is* the
 * request; re-deriving the requester from a header was duplicating what the
 * protocol already proves, and proving it more weakly.
 *
 * <h2>What it does not decide</h2>
 *
 * <p>Nothing. Every question — is this dataset consent-gated, is the requester a
 * processor who should be disclosed rather than asked, is there already an
 * outstanding ask, is there anybody to ask — is answered by ds-connector. The
 * guard's whole contribution is the boolean EDC needs.
 *
 * <p>Returning {@code false} is <b>not</b> an allow. The {@code ds:consentStatus}
 * ODRL constraint still evaluates and still denies. {@code false} only means
 * <em>parking would not help</em>, because no human decision is pending that
 * could unblock it.
 *
 * <h2>Cost</h2>
 *
 * <p>The state-machine query filters {@code isNotPending()} and the guard is
 * applied to that already-filtered batch, so once it returns {@code true} the
 * negotiation is excluded from every later batch until {@code pending} is
 * cleared — the guard is not re-invoked while parked. Its blocking call is
 * therefore bounded by the rate of <em>new</em> negotiations, not by how many
 * are parked. The short-TTL cache exists for the realistic burst: several
 * consumers negotiating the same dataset and purpose at once.
 */
public class ConsentPendingGuard implements ContractNegotiationPendingGuard {

    /** Both the compact form and the form ODRL's context expands it to. */
    private static final List<String> CONSENT_OPERAND_SUFFIXES = List.of("consentStatus", "ConsentStatus");

    private record CacheEntry(boolean park, Instant expiresAt) {
        boolean isExpired() {
            return Instant.now().isAfter(expiresAt);
        }
    }

    private final ConsentApi consent;
    private final ConsentAskApi asks;
    private final Duration cacheTtl;
    private final Monitor monitor;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();

    public ConsentPendingGuard(ConsentApi consent, ConsentAskApi asks, long cacheTtlSeconds, Monitor monitor) {
        this.consent = consent;
        this.asks = asks;
        this.cacheTtl = Duration.ofSeconds(cacheTtlSeconds);
        this.monitor = monitor;
    }

    @Override
    public boolean test(ContractNegotiation negotiation) {
        // The same guard instance is handed to both managers and to every state
        // they process. Only a provider negotiation that has just been asked for
        // can be waiting on a data subject.
        if (negotiation.getType() != ContractNegotiation.Type.PROVIDER) {
            return false;
        }
        if (negotiation.getState() != ContractNegotiationStates.REQUESTED.code()) {
            return false;
        }

        ContractOffer offer = negotiation.getLastContractOffer();
        if (offer == null) {
            return false;
        }
        Permission permission = consentGatedPermission(offer);
        if (permission == null) {
            return false;
        }

        String consumerId = negotiation.getCounterPartyId() != null ? negotiation.getCounterPartyId() : "";
        String datasetId = offer.getAssetId();
        List<String> purposes = Purposes.of(permission);

        if (purposes.isEmpty()) {
            // The connector denies a consent-gated dataset with no declared
            // purpose, so this would park the negotiation on a question nobody
            // can answer. Say why rather than leaving a negotiation stuck in
            // REQUESTED with nothing in the log.
            monitor.warning(
                "ConsentPendingGuard: consent-gated offer for %s carried no readable purpose — raw: %s"
                    .formatted(datasetId, Purposes.describe(permission)));
        }

        String cacheKey = String.join("|", datasetId, consumerId, String.join(",", purposes));
        CacheEntry cached = cache.get(cacheKey);
        if (cached != null && !cached.isExpired()) {
            return cached.park;
        }

        boolean park = decide(negotiation, datasetId, consumerId, purposes);
        cache.put(cacheKey, new CacheEntry(park, Instant.now().plus(cacheTtl)));
        return park;
    }

    private boolean decide(
        ContractNegotiation negotiation, String datasetId, String consumerId, List<String> purposes
    ) {
        ConsentApi.Decision decision = consent.check("", datasetId, consumerId, purposes);
        if (decision == null) {
            // The connector could not answer. Parking would strand the
            // negotiation on an outage rather than on a person, and the ODRL
            // constraint will fail closed on the same outage anyway.
            monitor.warning("ConsentPendingGuard: consent check unavailable for negotiation %s — not parking"
                .formatted(negotiation.getId()));
            return false;
        }
        if (decision.satisfied(false)) {
            return false;
        }
        if (!decision.shouldAsk()) {
            monitor.debug(() -> "ConsentPendingGuard: %s is covered for %s — disclosed, not asked"
                .formatted(consumerId, datasetId));
            return false;
        }

        ConsentAskApi.Outcome outcome = asks.record(
            negotiation.getId(), negotiation.getCorrelationId(), datasetId, consumerId, purposes
        );
        if (outcome == null || !outcome.asked()) {
            monitor.info("ConsentPendingGuard: negotiation %s not parked (%s)".formatted(
                negotiation.getId(), outcome == null ? "connector unavailable" : outcome.reason()
            ));
            return false;
        }

        monitor.info("ConsentPendingGuard: parking negotiation %s — %d consent request(s) awaiting a decision"
            .formatted(negotiation.getId(), outcome.requestIds().size()));
        return true;
    }

    /**
     * The permission carrying a {@code ds:consentStatus} constraint, or
     * {@code null} when this offer is not consent-gated.
     *
     * <p>Matched on the local name so the profile namespace stays configurable:
     * the operand is {@code {namespace}ConsentStatus}, and the compact
     * {@code ds:consentStatus} appears when the ODRL context was not applied.
     */
    static Permission consentGatedPermission(ContractOffer offer) {
        if (offer.getPolicy() == null || offer.getPolicy().getPermissions() == null) {
            return null;
        }
        for (Permission permission : offer.getPolicy().getPermissions()) {
            if (permission.getConstraints() == null) {
                continue;
            }
            for (Constraint constraint : permission.getConstraints()) {
                if (!(constraint instanceof AtomicConstraint atomic)) {
                    continue;
                }
                if (isConsentOperand(atomic)) {
                    return permission;
                }
            }
        }
        return null;
    }

    private static boolean isConsentOperand(AtomicConstraint constraint) {
        if (!(constraint.getLeftExpression() instanceof LiteralExpression literal)) {
            return false;
        }
        Object value = literal.getValue();
        if (value == null) {
            return false;
        }
        String operand = value.toString();
        return CONSENT_OPERAND_SUFFIXES.stream().anyMatch(operand::endsWith);
    }
}
