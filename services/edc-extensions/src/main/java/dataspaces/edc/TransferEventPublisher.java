package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.transfer.spi.event.TransferProcessEvent;
import org.eclipse.edc.connector.controlplane.transfer.spi.event.TransferProcessTerminated;
import org.eclipse.edc.spi.event.EventEnvelope;
import org.eclipse.edc.spi.event.EventSubscriber;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Forwards transfer-process lifecycle events to ds-connector's
 * {@code POST /webhooks/transfer-process}.
 *
 * <p>The sibling of {@link NegotiationEventPublisher}, and it exists for the same
 * reason: DSP carries no signal the connector could use to learn that a transfer
 * started or completed, and EDC's internal event router does.
 *
 * <p><b>Why this had to be built rather than the route deleted.</b> The route
 * had no producer in any deployment — the connector's own audit found it
 * unreachable — but it is the <em>only</em> place a provider emits
 * {@code DataTransferCompleted}, which rulebook {@code L-1} makes mandatory for
 * every participant. The consumer emits it from {@code consumer_service.run_flow},
 * the {@code /consumer/flow} convenience path; a provider emits it nowhere else.
 * Deleting the route would have removed a required event to tidy away an unused
 * one.
 *
 * <p><b>Why not {@code edc.callback.*}.</b> Unchanged from
 * {@link NegotiationEventPublisher}: EDC's static-callback extension
 * authenticates with a fixed header value read from the vault, which is a fourth
 * static shared secret in a codebase whose stated posture is that such a secret
 * spanning two trust boundaries is the defect being removed. Publishing from
 * inside the extension reuses {@link InternalAuth}, so the EDC presents the same
 * client-credentials identity here as it does on {@code /internal/*}.
 *
 * <p>Registered asynchronously: a connector that is down must not stall EDC's
 * state machine. Delivery is best-effort — the connector's records are a
 * projection of EDC's state, never the source of truth for it.
 *
 * <h2>Wire contract</h2>
 * <pre>
 * {"id": "...", "at": 1234, "type": "TRANSFER_PROCESS_COMPLETED", "payload": {
 *    "transferProcessId": "...", "assetId": "...", "contractId": "...",
 *    "role": "PROVIDER", "protocol": "dataspace-protocol-http"}}
 * </pre>
 * {@code type} is {@link TransferProcessEvent#name()} upper-snake-cased, matching
 * the negotiation publisher's convention, and {@code payload} uses EDC's own key
 * names so the connector's {@code TransferProcessEvent} model reads them
 * directly.
 *
 * <p><b>{@code role} is what the connector needs and cannot infer.</b> One
 * codebase runs on both sides of an exchange, and the same event reaches both.
 * Without it the connector recorded a literal {@code consumer_id="consumer"}
 * against every completed transfer.
 */
public class TransferEventPublisher implements EventSubscriber {

    private static final String PATH = "/webhooks/transfer-process";

    private final ConnectorClient client;
    private final Monitor monitor;

    public TransferEventPublisher(ConnectorClient client, Monitor monitor) {
        this.client = client;
        this.monitor = monitor;
    }

    @Override
    public <E extends org.eclipse.edc.spi.event.Event> void on(EventEnvelope<E> envelope) {
        if (!(envelope.getPayload() instanceof TransferProcessEvent event)) {
            return;
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("transferProcessId", event.getTransferProcessId());
        payload.put("assetId", event.getAssetId());
        // The contract agreement this transfer runs under. It is the id both
        // participants can name — the connector resolves the counterparties from
        // its own agreement record rather than trusting anything here to say who
        // they are.
        payload.put("contractId", event.getContractId());
        // CONSUMER or PROVIDER — which side of the exchange this runtime is on.
        payload.put("role", event.getType());
        payload.put("protocol", event.getProtocol());

        if (event instanceof TransferProcessTerminated terminated) {
            payload.put("reason", terminated.getReason());
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", envelope.getId());
        body.put("at", envelope.getAt());
        body.put("type", wireType(event));
        body.put("payload", payload);

        if (!client.postJson(PATH, body)) {
            monitor.warning("TransferEventPublisher: %s for transfer %s was not delivered"
                .formatted(wireType(event), event.getTransferProcessId()));
        }
    }

    /** {@code transfer.process.completed} → {@code TRANSFER_PROCESS_COMPLETED}. */
    static String wireType(TransferProcessEvent event) {
        return event.name().replace('.', '_').toUpperCase(Locale.ROOT);
    }
}
