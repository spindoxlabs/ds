package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.time.Duration;
import java.util.Map;

/**
 * Evaluates {@code {namespace}Membership eq "dataspaces.query"} by calling
 * {@code GET /internal/participants/check} on ds-connector.
 *
 * <p>The left-operand IRI is configured via {@code dataspaces.odrl.namespace}
 * (default: {@code https://w3id.org/dsp/policy/}).
 *
 * <p>All participant registry logic lives in Python — this function is a thin
 * HTTP proxy. Results are cached with a configurable TTL (default 60 s) to
 * avoid calling the connector on every policy evaluation. The cache is bounded:
 * see {@link TtlCache}.
 *
 * <p>Fails closed: if the connector is unreachable, or the right operand cannot
 * be read as a single scalar, returns {@code false}.
 *
 * <p>Generic in the context type so it can be registered on the narrowest
 * context that carries a participant agent, rather than on
 * {@link ParticipantAgentPolicyContext} itself — the engine matches a function
 * with {@code contextType().isAssignableFrom(context.getClass())}, and the
 * catalogue, negotiation and transfer contexts all implement that interface. See
 * {@code DataspacesExtension.registerPolicy}.
 */
public class AccessScopeFunction<C extends ParticipantAgentPolicyContext>
    implements AtomicConstraintRuleFunction<Permission, C> {

    private static final String PATH = "/internal/participants/check";

    private final ConnectorClient client;
    private final Monitor monitor;
    private final TtlCache<Boolean> cache;

    public AccessScopeFunction(ConnectorClient client, long cacheTtlSeconds, Monitor monitor) {
        this.client = client;
        this.monitor = monitor;
        this.cache = new TtlCache<>(Duration.ofSeconds(cacheTtlSeconds));
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, C context) {
        if (operator != Operator.EQ) return false;

        ParticipantAgent agent = context.participantAgent();
        String participantId = agent != null ? agent.getIdentity() : null;
        if (participantId == null) return false;

        // Not `rightValue.toString()`. A policy that reached the store through
        // EDC's JSON-LD expansion carries the operand wrapped, and the dump that
        // toString() produces is not a scope any registry knows — so the check
        // failed on exactly the policies that took the expanded path, silently.
        String scope = Purposes.unwrapScalar(rightValue);
        if (scope == null || scope.isBlank()) {
            monitor.warning("AccessScopeFunction: unreadable membership operand %s — denying"
                .formatted(Purposes.describeValue(rightValue)));
            return false;
        }

        String cacheKey = participantId + "|" + scope;
        Boolean cached = cache.get(cacheKey);
        if (cached != null) {
            return cached;
        }

        boolean allowed = checkScopeViaHttp(participantId, scope);
        cache.put(cacheKey, allowed);
        return allowed;
    }

    private boolean checkScopeViaHttp(String participantId, String scope) {
        JsonNode body = client.getJson(PATH, Map.of("participant_id", participantId, "scope", scope));
        return body != null && body.path("allowed").asBoolean(false);
    }
}
