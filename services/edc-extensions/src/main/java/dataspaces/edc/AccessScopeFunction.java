package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Evaluates {@code {namespace}Membership eq "dataspaces.query"} by calling
 * {@code GET /internal/participants/check} on ds-connector.
 *
 * <p>The left-operand IRI is configured via {@code dataspaces.odrl.namespace}
 * (default: {@code https://w3id.org/dsp/policy/}).
 *
 * <p>All participant registry logic lives in Python — this function is a thin
 * HTTP proxy. Results are cached with a configurable TTL (default 60 s) to
 * avoid calling the connector on every policy evaluation.
 *
 * <p>Fails closed: if the connector is unreachable, returns {@code false}.
 */
public class AccessScopeFunction implements AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext> {

    private static final String PATH = "/internal/participants/check";

    private record CacheEntry(boolean allowed, Instant expiresAt) {
        boolean isExpired() { return Instant.now().isAfter(expiresAt); }
    }

    private final ConnectorClient client;
    private final Duration cacheTtl;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();

    public AccessScopeFunction(ConnectorClient client, long cacheTtlSeconds) {
        this.client = client;
        this.cacheTtl = Duration.ofSeconds(cacheTtlSeconds);
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, ParticipantAgentPolicyContext context) {
        if (operator != Operator.EQ) return false;

        ParticipantAgent agent = context.participantAgent();
        String participantId = agent != null ? agent.getIdentity() : null;
        if (participantId == null) return false;

        String scope = rightValue.toString();
        String cacheKey = participantId + "|" + scope;

        CacheEntry cached = cache.get(cacheKey);
        if (cached != null && !cached.isExpired()) {
            return cached.allowed;
        }

        boolean allowed = checkScopeViaHttp(participantId, scope);
        cache.put(cacheKey, new CacheEntry(allowed, Instant.now().plus(cacheTtl)));
        return allowed;
    }

    private boolean checkScopeViaHttp(String participantId, String scope) {
        JsonNode body = client.getJson(PATH, Map.of("participant_id", participantId, "scope", scope));
        return body != null && body.path("allowed").asBoolean(false);
    }
}
