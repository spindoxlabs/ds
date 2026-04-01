package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Evaluates {@code ds:accessScope eq "dataspaces.query"} by calling
 * {@code GET /internal/participants/check} on ds-connector.
 *
 * <p>All participant registry logic lives in Python — this function is a thin
 * HTTP proxy. Results are cached with a configurable TTL (default 60 s) to
 * avoid calling the connector on every policy evaluation.
 *
 * <p>Fails closed: if the connector is unreachable, returns {@code false}.
 */
public class AccessScopeFunction implements AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext> {

    private record CacheEntry(boolean allowed, Instant expiresAt) {
        boolean isExpired() { return Instant.now().isAfter(expiresAt); }
    }

    private final String connectorBaseUrl;
    private final Duration cacheTtl;
    private final OkHttpClient http;
    private final ObjectMapper mapper;
    private final Monitor monitor;
    private final Map<String, CacheEntry> cache = new ConcurrentHashMap<>();

    public AccessScopeFunction(String connectorBaseUrl, long cacheTtlSeconds, Monitor monitor) {
        this.connectorBaseUrl = connectorBaseUrl.replaceAll("/+$", "");
        this.cacheTtl = Duration.ofSeconds(cacheTtlSeconds);
        this.http = new OkHttpClient.Builder()
            .connectTimeout(Duration.ofSeconds(5))
            .readTimeout(Duration.ofSeconds(5))
            .build();
        this.mapper = new ObjectMapper();
        this.monitor = monitor;
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
        String url = String.format(
            "%s/internal/participants/check?participant_id=%s&scope=%s",
            connectorBaseUrl,
            encode(participantId),
            encode(scope)
        );
        int[] backoffMs = {100, 500, 2000};
        for (int attempt = 0; attempt <= backoffMs.length; attempt++) {
            try {
                Request request = new Request.Builder().url(url).get().build();
                try (Response response = http.newCall(request).execute()) {
                    if (!response.isSuccessful() || response.body() == null) {
                        monitor.warning("AccessScopeFunction: unexpected response %d for participant %s"
                            .formatted(response.code(), participantId));
                        return false;
                    }
                    JsonNode body = mapper.readTree(response.body().string());
                    return body.path("allowed").asBoolean(false);
                }
            } catch (IOException e) {
                monitor.warning("AccessScopeFunction: attempt %d/%d failed for %s: %s"
                    .formatted(attempt + 1, backoffMs.length + 1, participantId, e.getMessage()));
                if (attempt < backoffMs.length) {
                    try { Thread.sleep(backoffMs[attempt]); } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        return false;
                    }
                }
            }
        }
        return false;
    }

    private static String encode(String value) {
        return java.net.URLEncoder.encode(value, java.nio.charset.StandardCharsets.UTF_8);
    }
}
