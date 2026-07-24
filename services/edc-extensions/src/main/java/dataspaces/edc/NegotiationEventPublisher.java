package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.event.contractnegotiation.ContractNegotiationEvent;
import org.eclipse.edc.connector.controlplane.contract.spi.event.contractnegotiation.ContractNegotiationFinalized;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.spi.event.EventEnvelope;
import org.eclipse.edc.spi.event.EventSubscriber;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.types.TypeManager;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Forwards contract-negotiation lifecycle events to ds-connector's
 * {@code POST /webhooks/contract-negotiation}.
 *
 * <p>DSP has no representation of a natural person, so nothing in the protocol
 * tells the connector that a negotiation was terminated or finalized — but EDC
 * publishes both on its internal event router, and the connector needs them to
 * keep its own agreement and access-request records true.
 *
 * <p><b>Why not {@code edc.callback.*}.</b> EDC's static-callback extension can
 * post these over HTTP, but it authenticates with a fixed header value read
 * from the vault — a fourth static shared secret, in a codebase whose stated
 * posture is that a static secret spanning two trust boundaries is the defect
 * being removed. Publishing from inside the extension reuses
 * {@link InternalAuth}, so the EDC presents the same client-credentials
 * identity here as it does on {@code /internal/*} and the connector can tell
 * from the token who called.
 *
 * <p>Registered asynchronously: a connector that is down must not stall EDC's
 * state machine. Delivery is therefore best-effort — the connector's records
 * are a projection of EDC's state, never the source of truth for it.
 *
 * <h2>Wire contract</h2>
 * <pre>
 * {"id": "...", "type": "CONTRACT_NEGOTIATION_FINALIZED", "payload": {...}}
 * </pre>
 * {@code type} is {@link ContractNegotiationEvent#name()} upper-snake-cased, so
 * {@code contract.negotiation.terminated} becomes
 * {@code CONTRACT_NEGOTIATION_TERMINATED}. The connector matches on the state
 * word within it.
 */
public class NegotiationEventPublisher implements EventSubscriber {

    private static final String PATH = "/webhooks/contract-negotiation";

    private final ConnectorClient client;
    private final TypeManager typeManager;
    private final Monitor monitor;

    public NegotiationEventPublisher(ConnectorClient client, TypeManager typeManager, Monitor monitor) {
        this.client = client;
        this.typeManager = typeManager;
        this.monitor = monitor;
    }

    @Override
    public <E extends org.eclipse.edc.spi.event.Event> void on(EventEnvelope<E> envelope) {
        if (!(envelope.getPayload() instanceof ContractNegotiationEvent event)) {
            return;
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("contractNegotiationId", event.getContractNegotiationId());
        payload.put("counterPartyId", event.getCounterPartyId());
        payload.put("counterPartyAddress", event.getCounterPartyAddress());
        payload.put("protocol", event.getProtocol());

        if (event instanceof ContractNegotiationFinalized finalized) {
            ContractAgreement agreement = finalized.getContractAgreement();
            if (agreement != null) {
                payload.put("contractAgreementId", agreement.getId());
                payload.put("assetId", agreement.getAssetId());
                payload.put("consumerId", agreement.getConsumerId());
                payload.put("providerId", agreement.getProviderId());
                payload.put("policy", policySnapshot(agreement));
            }
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", envelope.getId());
        body.put("at", envelope.getAt());
        body.put("type", wireType(event));
        body.put("payload", payload);

        if (!client.postJson(PATH, body)) {
            monitor.warning("NegotiationEventPublisher: %s for negotiation %s was not delivered"
                .formatted(wireType(event), event.getContractNegotiationId()));
        }
    }

    /** {@code contract.negotiation.finalized} → {@code CONTRACT_NEGOTIATION_FINALIZED}. */
    private static String wireType(ContractNegotiationEvent event) {
        return event.name().replace('.', '_').toUpperCase(Locale.ROOT);
    }

    /**
     * The agreement's ODRL policy, as the connector stores it for audit. EDC's
     * own {@link TypeManager} does the conversion so the snapshot matches what
     * the Management API would return; an unserialisable policy yields an empty
     * object rather than dropping the whole event.
     */
    private Map<String, Object> policySnapshot(ContractAgreement agreement) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> policy = typeManager.getMapper()
                .convertValue(agreement.getPolicy(), Map.class);
            return policy;
        } catch (IllegalArgumentException e) {
            monitor.warning("NegotiationEventPublisher: could not serialise policy for agreement %s: %s"
                .formatted(agreement.getId(), e.getMessage()));
            return Map.of();
        }
    }
}
