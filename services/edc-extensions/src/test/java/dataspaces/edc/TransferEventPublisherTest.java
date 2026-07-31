package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.transfer.spi.event.TransferProcessCompleted;
import org.eclipse.edc.connector.controlplane.transfer.spi.event.TransferProcessStarted;
import org.eclipse.edc.connector.controlplane.transfer.spi.event.TransferProcessTerminated;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * The wire type the connector matches on.
 *
 * <p>{@code POST /webhooks/transfer-process} branches on the state word inside
 * {@code type} ("STARTED", "COMPLETED"), so the mapping from EDC's dotted event
 * name to the upper-snake wire name is load-bearing: get it wrong and a provider
 * silently emits no {@code DataTransferCompleted}, which is exactly the gap this
 * publisher was written to close. There was no producer to get it wrong before.
 */
class TransferEventPublisherTest {

    @Test
    void completed_becomes_the_name_the_connector_matches() {
        var event = TransferProcessCompleted.Builder.newInstance()
            .transferProcessId("tp-1")
            .build();
        assertEquals("TRANSFER_PROCESS_COMPLETED", TransferEventPublisher.wireType(event));
    }

    @Test
    void started_is_a_distinct_wire_type() {
        var event = TransferProcessStarted.Builder.newInstance()
            .transferProcessId("tp-1")
            .build();
        var wireType = TransferEventPublisher.wireType(event);
        assertEquals("TRANSFER_PROCESS_STARTED", wireType);
        // A transfer that has started has moved no data yet. The connector emits
        // TransferStarted for this and DataTransferCompleted for the other, so
        // the two must not collapse onto one name.
        assertEquals(
            false,
            wireType.equals(TransferEventPublisher.wireType(
                TransferProcessCompleted.Builder.newInstance()
                    .transferProcessId("tp-1")
                    .build()))
        );
    }

    @Test
    void terminated_carries_the_state_word_too() {
        var event = TransferProcessTerminated.Builder.newInstance()
            .transferProcessId("tp-1")
            .reason("consent revoked")
            .build();
        // Neither STARTED nor COMPLETED — the connector logs and drops it rather
        // than settling a record it has no event for.
        assertEquals("TRANSFER_PROCESS_TERMINATED", TransferEventPublisher.wireType(event));
    }
}
