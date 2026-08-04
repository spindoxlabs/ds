package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.store.ContractNegotiationStore;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiation;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiationStates;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.query.Criterion;
import org.eclipse.edc.spi.query.QuerySpec;
import org.eclipse.edc.spi.result.StoreResult;
import org.eclipse.edc.transaction.spi.TransactionContext;
import org.eclipse.edc.web.spi.exception.ObjectNotFoundException;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The one operation EDC's Management API cannot express: clearing {@code pending}.
 *
 * <p>Every outcome is a 200 describing the current state rather than an error,
 * because the connector retries and a decision can arrive after the negotiation
 * has moved on. The property worth pinning is the one a status code would hide:
 * a grant arriving after the TTL expired must <b>not</b> resurrect a negotiation
 * the counterparty has already been told is over.
 */
class NegotiationResumeControllerTest {

    private static final String ID = "negotiation-1";

    private static class NoopMonitor implements Monitor {
    }

    /** Runs the block inline — there is no transaction to model here. */
    private static final TransactionContext INLINE = new TransactionContext() {
        @Override
        public void execute(TransactionBlock block) {
            block.execute();
        }

        @Override
        public <T> T execute(ResultTransactionBlock<T> block) {
            return block.execute();
        }

        @Override
        public void registerSynchronization(TransactionSynchronization sync) {
        }
    };

    /** A store holding exactly one negotiation, with a lease that can be refused. */
    private static class SingleNegotiationStore implements ContractNegotiationStore {
        private ContractNegotiation negotiation;
        private final boolean leaseFails;
        int saves;

        SingleNegotiationStore(ContractNegotiation negotiation, boolean leaseFails) {
            this.negotiation = negotiation;
            this.leaseFails = leaseFails;
        }

        @Override
        public ContractNegotiation findById(String negotiationId) {
            return ID.equals(negotiationId) ? negotiation : null;
        }

        @Override
        public StoreResult<ContractNegotiation> findByIdAndLease(String negotiationId) {
            if (negotiation == null || !ID.equals(negotiationId)) {
                return StoreResult.notFound("not found");
            }
            if (leaseFails) {
                return StoreResult.alreadyLeased("leased");
            }
            return StoreResult.success(negotiation);
        }

        @Override
        public StoreResult<Void> save(ContractNegotiation entity) {
            saves++;
            negotiation = entity;
            return StoreResult.success();
        }

        @Override
        public ContractAgreement findContractAgreement(String contractId) {
            return null;
        }

        @Override
        public StoreResult<Void> deleteById(String negotiationId) {
            return StoreResult.success();
        }

        @Override
        public Stream<ContractNegotiation> queryNegotiations(QuerySpec querySpec) {
            return Stream.empty();
        }

        @Override
        public Stream<ContractAgreement> queryAgreements(QuerySpec querySpec) {
            return Stream.empty();
        }

        @Override
        public List<ContractNegotiation> nextNotLeased(int max, Criterion... criteria) {
            return List.of();
        }
    }

    private static ContractNegotiation negotiation(ContractNegotiationStates state, boolean pending) {
        var negotiation = ContractNegotiation.Builder.newInstance()
            .id(ID)
            .counterPartyId("did:web:third-party.dataspaces.localhost")
            .counterPartyAddress("https://third-party.dataspaces.localhost/api/dsp")
            .protocol("dataspace-protocol-http")
            .type(ContractNegotiation.Type.PROVIDER)
            .state(state.code())
            .build();
        negotiation.setPending(pending);
        return negotiation;
    }

    private static Map<String, Object> resume(SingleNegotiationStore store) {
        return new NegotiationResumeController(store, INLINE, new NoopMonitor()).resume(ID);
    }

    @Test
    void aParkedNegotiationIsResumed() {
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, true), false);

        var response = resume(store);

        assertEquals("resumed", response.get("outcome"));
        assertEquals(true, response.get("resumed"));
        assertEquals(false, response.get("pending"));
        assertFalse(store.findById(ID).isPending(), "pending must be cleared in the store, not only in the response");
    }

    @Test
    void resumingTwiceIsANoOp() {
        // The connector retries; a subject can answer twice. Neither is an error.
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, false), false);

        var response = resume(store);

        assertEquals("not_pending", response.get("outcome"));
        assertEquals(false, response.get("resumed"));
    }

    @Test
    void aTerminatedNegotiationIsNotResurrected() {
        // The race this endpoint exists to lose safely: a grant arriving after the
        // TTL expired. DSP treats terminal states as final and the consumer has
        // already been told; disagreeing with the counterparty about what
        // happened is worse than dropping the grant.
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.TERMINATED, true), false);

        var response = resume(store);

        assertEquals("terminal", response.get("outcome"));
        assertEquals(false, response.get("resumed"));
        assertTrue(store.findById(ID).isPending(), "a terminal negotiation must be left exactly as it was");
    }

    @Test
    void aFinalizedNegotiationIsAlsoTerminal() {
        // `isTerminal` compared against TERMINATED alone and missed FINALIZED —
        // the other final state, and one EDC already defines. It now asks
        // upstream rather than keeping a second copy of the list.
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.FINALIZED, true), false);

        assertEquals("terminal", resume(store).get("outcome"));
    }

    @Test
    void aLeasedNegotiationIsReportedRatherThanForced() {
        // The state machine has it right now, which is what we wanted anyway.
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, true), true);

        var response = resume(store);

        assertEquals("leased", response.get("outcome"));
        assertEquals(0, store.saves, "a leased negotiation must not be written");
    }

    @Test
    void anUnknownNegotiationIs404() {
        var store = new SingleNegotiationStore(null, false);
        assertThrows(ObjectNotFoundException.class, () -> resume(store));
    }
}
