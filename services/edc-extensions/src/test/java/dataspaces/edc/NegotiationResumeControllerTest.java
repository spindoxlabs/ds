package dataspaces.edc;

import jakarta.ws.rs.core.SecurityContext;
import org.eclipse.edc.api.auth.spi.AuthorizationService;
import org.eclipse.edc.api.auth.spi.RequiredScope;
import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.store.ContractNegotiationStore;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiation;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiationStates;
import org.eclipse.edc.participantcontext.single.spi.SingleParticipantContextSupplier;
import org.eclipse.edc.participantcontext.spi.types.ParticipantContext;
import org.eclipse.edc.participantcontext.spi.types.ParticipantResource;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.query.Criterion;
import org.eclipse.edc.spi.query.QuerySpec;
import org.eclipse.edc.spi.result.ServiceResult;
import org.eclipse.edc.spi.result.StoreResult;
import org.eclipse.edc.transaction.spi.TransactionContext;
import org.eclipse.edc.web.spi.exception.NotAuthorizedException;
import org.eclipse.edc.web.spi.exception.ObjectNotFoundException;
import org.junit.jupiter.api.Test;

import java.security.Principal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.BiFunction;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
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
 *
 * <p>And who may ask: the route requires {@code management-api:negotiations:write}
 * and EDC's ownership check for this runtime's one participant context, both
 * before the store is read.
 */
class NegotiationResumeControllerTest {

    private static final String ID = "negotiation-1";
    private static final String CONTEXT = "did:web:rec.dataspaces.localhost";

    /** Whatever the OAuth2 filter set; the controller only passes it on. */
    private static final SecurityContext CALLER = new SecurityContext() {
        @Override
        public Principal getUserPrincipal() {
            return () -> CONTEXT;
        }

        @Override
        public boolean isUserInRole(String role) {
            return false;
        }

        @Override
        public boolean isSecure() {
            return false;
        }

        @Override
        public String getAuthenticationScheme() {
            return null;
        }
    };

    private static final SingleParticipantContextSupplier THIS_RUNTIME = () -> ServiceResult.success(
        ParticipantContext.Builder.newInstance()
            .participantContextId(CONTEXT)
            .identity(CONTEXT)
            .build()
    );

    /** Answers with a fixed result and records every question it was asked. */
    private static class RecordingAuthorization implements AuthorizationService {
        final List<Object[]> calls = new ArrayList<>();
        private final ServiceResult<Void> answer;

        RecordingAuthorization(ServiceResult<Void> answer) {
            this.answer = answer;
        }

        @Override
        public ServiceResult<Void> authorize(
            SecurityContext securityContext, String resourceOwnerId, String resourceId,
            Class<? extends ParticipantResource> resourceClass
        ) {
            calls.add(new Object[] {securityContext, resourceOwnerId, resourceId, resourceClass});
            return answer;
        }

        @Override
        public void addLookupFunction(Class<?> resourceClass, BiFunction<String, String, ParticipantResource> f) {
        }
    }

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

        // Added to `StateEntityStore` in EDC 0.18.0. The controller under test
        // never calls it — it takes a lease with `findByIdAndLease` and releases
        // it by saving — so this is here to satisfy the interface, and says so
        // rather than pretending to model a lease.
        @Override
        public StoreResult<Void> breakLease(ContractNegotiation entity) {
            return StoreResult.success();
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
        return resume(store, new RecordingAuthorization(ServiceResult.success()), THIS_RUNTIME);
    }

    private static Map<String, Object> resume(
        SingleNegotiationStore store, AuthorizationService authorization,
        SingleParticipantContextSupplier runtime
    ) {
        return new NegotiationResumeController(store, INLINE, authorization, runtime, new NoopMonitor())
            .resume(ID, CALLER);
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

    // ── Who may resume ──────────────────────────────────────────────────────

    @Test
    void theRouteRequiresTheNegotiationWriteScope() throws Exception {
        // Without it the v5 filters admit any token whose `sub` names a context:
        // the scope filter only runs on methods that carry the annotation.
        var method = NegotiationResumeController.class.getMethod("resume", String.class, SecurityContext.class);
        var annotation = method.getAnnotation(RequiredScope.class);
        assertNotNull(annotation, "resume must declare @RequiredScope");
        assertEquals("management-api:negotiations:write", annotation.value());
    }

    @Test
    void ownershipIsAskedForThisRuntimesContextAndThisNegotiation() {
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, true), false);
        var authorization = new RecordingAuthorization(ServiceResult.success());

        resume(store, authorization, THIS_RUNTIME);

        assertEquals(1, authorization.calls.size());
        var call = authorization.calls.get(0);
        assertEquals(CALLER, call[0]);
        assertEquals(CONTEXT, call[1]);
        assertEquals(ID, call[2]);
        assertEquals(ContractNegotiation.class, call[3]);
    }

    @Test
    void anotherParticipantsTokenIsRefusedBeforeTheStoreIsTouched() {
        // A token whose `sub` is not this runtime's context, or a negotiation
        // owned by another: EDC answers `unauthorized`, and nothing is resumed.
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, true), false);
        var refusing = new RecordingAuthorization(ServiceResult.unauthorized("not the owner"));

        assertThrows(NotAuthorizedException.class, () -> resume(store, refusing, THIS_RUNTIME));
        assertEquals(0, store.saves);
        assertTrue(store.findById(ID).isPending(), "a refused call must leave the negotiation parked");
    }

    @Test
    void aNegotiationTheOwnerDoesNotHoldIs404FromTheOwnershipCheck() {
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, true), false);
        var notFound = new RecordingAuthorization(ServiceResult.notFound("no such negotiation for this owner"));

        assertThrows(ObjectNotFoundException.class, () -> resume(store, notFound, THIS_RUNTIME));
        assertEquals(0, store.saves);
    }

    @Test
    void noParticipantContextMeansNoResume() {
        var store = new SingleNegotiationStore(negotiation(ContractNegotiationStates.REQUESTED, true), false);
        var authorization = new RecordingAuthorization(ServiceResult.success());
        SingleParticipantContextSupplier none = () -> ServiceResult.notFound("no context");

        assertThrows(ObjectNotFoundException.class, () -> resume(store, authorization, none));
        assertTrue(authorization.calls.isEmpty());
        assertEquals(0, store.saves);
    }
}
