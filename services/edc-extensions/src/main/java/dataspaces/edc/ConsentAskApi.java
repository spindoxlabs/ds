package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Asks ds-connector to put a consent question to the people behind a dataset,
 * on behalf of a negotiation about to be parked.
 *
 * <p>Everything the ask needs is already on the negotiation: EDC has verified
 * who is asking ({@code counterPartyId}, from a DCP credential presentation),
 * and the offer names the asset and the purposes. Nothing is taken from a
 * header.
 *
 * <p>The connector answers every case with 200 and an {@code asked} flag rather
 * than a status code, so the guard never has to interpret an error into policy.
 */
public final class ConsentAskApi {

    private static final String PATH = "/internal/consent/asks";

    /**
     * @param asked      whether a question actually went to at least one person —
     *                   the only case in which parking the negotiation achieves anything
     * @param reason     why, in the connector's vocabulary ({@code awaiting_consent},
     *                   {@code covered_processor}, {@code no_subjects}, …)
     * @param requestIds the consent rows now waiting for a decision
     */
    public record Outcome(boolean asked, String reason, List<String> requestIds) {
    }

    private final ConnectorClient client;

    public ConsentAskApi(ConnectorClient client) {
        this.client = client;
    }

    /**
     * @return the outcome, or {@code null} when the connector could not be
     *         reached — which the guard treats as "do not park", since parking
     *         on an outage would strand the negotiation on infrastructure
     *         rather than on a person.
     */
    public Outcome record(
        String negotiationId,
        String correlationId,
        String datasetId,
        String consumerId,
        List<String> purposes
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("negotiation_id", negotiationId);
        body.put("correlation_id", correlationId);
        body.put("dataset_id", datasetId);
        body.put("consumer_id", consumerId);
        body.put("purpose", purposes == null ? List.of() : purposes);

        JsonNode response = client.postJsonForResult(PATH, body);
        if (response == null) {
            return null;
        }
        List<String> ids = new ArrayList<>();
        JsonNode idsNode = response.path("request_ids");
        if (idsNode.isArray()) {
            for (JsonNode id : idsNode) {
                if (id.isTextual()) {
                    ids.add(id.asText());
                }
            }
        }
        return new Outcome(
            response.path("asked").asBoolean(false),
            response.path("reason").asText("unknown"),
            List.copyOf(ids)
        );
    }
}
