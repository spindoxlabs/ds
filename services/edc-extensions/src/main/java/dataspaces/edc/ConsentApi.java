package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * The connector's single consent decision, as seen from Java.
 *
 * <p>{@code GET /internal/consent/check} is the one place consent is decided —
 * for the negotiation, for the ongoing-transfer policy monitor, and for the
 * dataset-api's row filter. They differ only in which projection of the same
 * answer they read, so this wrapper carries the whole answer and lets each
 * caller pick.
 */
public final class ConsentApi {

    private static final String PATH = "/internal/consent/check";

    /**
     * @param consentActive    the named subject has consent covering this consumer, purpose and role
     * @param subjectIds       every subject whose consent covers it — the row filter
     * @param shouldAsk        whether an absent consent is a question to put to a person, or a
     *                         disclosure to a party the offer already covers as a processor (§6.3)
     * @param pendingRequestId an ask already recorded for this tuple, so a re-negotiation
     *                         reattaches instead of duplicating
     */
    public record Decision(
        boolean consentActive,
        List<String> subjectIds,
        boolean shouldAsk,
        String pendingRequestId
    ) {
        /** Consent covers this request — for a named subject, or for at least one of a pool. */
        public boolean satisfied(boolean subjectNamed) {
            return subjectNamed ? consentActive : !subjectIds.isEmpty();
        }
    }

    private final ConnectorClient client;

    public ConsentApi(ConnectorClient client) {
        this.client = client;
    }

    /**
     * Ask the connector about one (subject?, dataset, consumer, purpose) tuple.
     *
     * @return the decision, or {@code null} when the connector could not answer.
     *         {@code null} means denied — an unanswerable consent question is
     *         not a licence to proceed.
     */
    public Decision check(String subjectId, String datasetId, String consumerId, List<String> purposes) {
        Map<String, String> query = new LinkedHashMap<>();
        query.put("dataset_id", datasetId);
        query.put("consumer_id", consumerId);
        query.put("subject_id", subjectId);
        query.put("purpose", purposes == null || purposes.isEmpty() ? null : String.join(",", purposes));

        JsonNode body = client.getJson(PATH, query);
        if (body == null) {
            return null;
        }
        return new Decision(
            body.path("consent_active").asBoolean(false),
            subjectIds(body),
            // Absent on a connector that predates §6.7: an unanswered `should_ask`
            // means "ask", which is the recoverable direction — a redundant
            // question can be withdrawn, a skipped one cannot be un-skipped.
            body.path("should_ask").asBoolean(true),
            body.path("pending_request_id").isTextual() ? body.path("pending_request_id").asText() : null
        );
    }

    private static List<String> subjectIds(JsonNode body) {
        JsonNode node = body.path("subject_ids");
        if (!node.isArray()) {
            return List.of();
        }
        List<String> ids = new ArrayList<>(node.size());
        for (JsonNode item : node) {
            if (item.isTextual()) {
                ids.add(item.asText());
            }
        }
        return List.copyOf(ids);
    }
}
