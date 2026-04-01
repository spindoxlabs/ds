package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintFunction;
import org.eclipse.edc.policy.engine.spi.PolicyContext;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.io.IOException;
import java.time.Duration;
import java.util.Optional;

/**
 * Evaluates {@code ds:consentStatus eq "active"} by querying the
 * ds-connector internal consent check endpoint.
 *
 * <p>Retries up to 3 times with exponential backoff (100 ms → 500 ms → 2 s).
 * Fails closed: returns {@code false} if the connector is unreachable after all
 * attempts — access is never granted on error.
 */
public class ConsentStatusFunction implements AtomicConstraintFunction<Permission> {

    private static final int[] BACKOFF_MS = {100, 500, 2000};

    private final String connectorBaseUrl;
    private final OkHttpClient http;
    private final ObjectMapper mapper;
    private final Monitor monitor;

    public ConsentStatusFunction(String connectorBaseUrl, Monitor monitor) {
        this.connectorBaseUrl = connectorBaseUrl.stripTrailing("/");
        this.http = new OkHttpClient.Builder()
            .connectTimeout(Duration.ofSeconds(5))
            .readTimeout(Duration.ofSeconds(5))
            .build();
        this.mapper = new ObjectMapper();
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, PolicyContext context) {
        if (operator != Operator.EQ) return false;
        if (!"active".equals(rightValue.toString())) return false;

        String participantId = context.getContextData(ParticipantAgent.class)
            .map(ParticipantAgent::getIdentity)
            .orElse(null);
        String assetId = context.getContextData(String.class);
        String subjectId = Optional.ofNullable(context.getContextData(String.class)).orElse("");

        if (subjectId.isEmpty() || assetId == null) {
            // Cannot evaluate without subject/asset context — fail closed
            return false;
        }

        return checkConsent(subjectId, assetId, participantId != null ? participantId : "");
    }

    private boolean checkConsent(String subjectId, String datasetId, String consumerId) {
        String url = String.format(
            "%s/internal/consent/check?subject_id=%s&dataset_id=%s&consumer_id=%s",
            connectorBaseUrl,
            encode(subjectId),
            encode(datasetId),
            encode(consumerId)
        );
        for (int attempt = 0; attempt <= BACKOFF_MS.length; attempt++) {
            try {
                Request request = new Request.Builder().url(url).get().build();
                try (Response response = http.newCall(request).execute()) {
                    if (!response.isSuccessful() || response.body() == null) {
                        monitor.warning("ConsentStatusFunction: HTTP %d for subject %s"
                            .formatted(response.code(), subjectId));
                        return false;
                    }
                    JsonNode body = mapper.readTree(response.body().string());
                    return body.path("consent_active").asBoolean(false);
                }
            } catch (IOException e) {
                monitor.warning("ConsentStatusFunction: attempt %d/%d failed: %s"
                    .formatted(attempt + 1, BACKOFF_MS.length + 1, e.getMessage()));
                if (attempt < BACKOFF_MS.length) {
                    try { Thread.sleep(BACKOFF_MS[attempt]); } catch (InterruptedException ie) {
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
