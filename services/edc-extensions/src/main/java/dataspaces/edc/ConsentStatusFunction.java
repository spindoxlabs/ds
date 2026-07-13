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

/**
 * Evaluates {@code {namespace}ConsentStatus eq "active"} by querying the
 * ds-connector internal consent check endpoint.
 *
 * <p>The consumer participant ID is taken from the verified {@code ParticipantAgent}.
 * Subject and dataset IDs are taken from {@code ParticipantAgent} attributes
 * ({@code ds.subject_id}, {@code ds.dataset_id}) when present. For dataset-level
 * negotiations without a subject attribute, the function accepts the negotiation
 * when at least one subject has granted consent for the consumer+dataset pair.
 * Fails closed when the dataset attribute is absent.
 *
 * <p>Retries up to 3 times with exponential backoff (100 ms → 500 ms → 2 s).
 */
public class ConsentStatusFunction implements AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext> {

    private static final int[] BACKOFF_MS = {100, 500, 2000};

    private final String connectorBaseUrl;
    private final OkHttpClient http;
    private final ObjectMapper mapper;
    private final Monitor monitor;

    public ConsentStatusFunction(String connectorBaseUrl, Monitor monitor) {
        this.connectorBaseUrl = connectorBaseUrl.replaceAll("/+$", "");
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
        String expectedStatus = rightValue.toString();
        if (!"active".equals(expectedStatus) && !"granted".equals(expectedStatus)) return false;

        ParticipantAgent agent = context.participantAgent();
        if (agent == null) return false;

        String consumerId = agent.getIdentity();
        String subjectId = agent.getAttributes().getOrDefault("ds.subject_id", "");
        String datasetId = agent.getAttributes().getOrDefault("ds.dataset_id", "");

        if (datasetId.isEmpty()) {
            monitor.warning("ConsentStatusFunction: ds.dataset_id missing from participant attributes — failing closed");
            return false;
        }

        return checkConsent(subjectId, datasetId, consumerId != null ? consumerId : "");
    }

    private boolean checkConsent(String subjectId, String datasetId, String consumerId) {
        String url = consentCheckUrl(subjectId, datasetId, consumerId);
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
                    if (!subjectId.isEmpty()) {
                        return body.path("consent_active").asBoolean(false);
                    }
                    return body.path("subject_ids").isArray() && !body.path("subject_ids").isEmpty();
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

    private String consentCheckUrl(String subjectId, String datasetId, String consumerId) {
        StringBuilder url = new StringBuilder(String.format(
            "%s/internal/consent/check?dataset_id=%s&consumer_id=%s",
            connectorBaseUrl,
            encode(datasetId),
            encode(consumerId)
        ));
        if (!subjectId.isEmpty()) {
            url.append("&subject_id=").append(encode(subjectId));
        }
        return url.toString();
    }

    private static String encode(String value) {
        return java.net.URLEncoder.encode(value, java.nio.charset.StandardCharsets.UTF_8);
    }
}
