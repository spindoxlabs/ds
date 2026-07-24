package dataspaces.edc;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.store.ContractNegotiationStore;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiation;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiationStates;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.transaction.spi.TransactionContext;
import org.eclipse.edc.web.spi.exception.ObjectNotFoundException;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Resumes a contract negotiation parked by {@link ConsentPendingGuard}.
 *
 * <p>This is the one piece of DSP-adjacent surface this design adds, and it
 * exists because of a gap that was checked rather than assumed: EDC's Management
 * API can <em>terminate</em> a negotiation, but at v0.16.0 it has no way to
 * clear {@code pending}. So refusal and TTL expiry reuse the existing
 * {@code terminateNegotiation} endpoint and only the grant path needs code.
 *
 * <p>It is <b>not</b> a DSP message. It is a local control-plane operation on
 * this connector's own store, invoked by this participant's own connector when
 * a data subject decides — the counterparty neither calls it nor knows it
 * exists. Registered on the management context, so it inherits EDC's Management
 * API authentication: resuming a negotiation is contract administration, which
 * is exactly the boundary that key is for.
 *
 * <h2>Idempotency and races</h2>
 *
 * <p>The connector retries, and a decision can arrive after the negotiation has
 * already moved on, so every outcome is a 200 describing the current state
 * rather than an error:
 *
 * <ul>
 *   <li><b>Parked</b> → clear {@code pending}, save. The state machine picks it
 *       up on the next pass and carries it to {@code AGREEING}.</li>
 *   <li><b>Not pending</b> → no-op. A duplicate call, or the subject answered
 *       twice.</li>
 *   <li><b>Terminal</b> → no-op, and say so. A grant arriving after the TTL
 *       expired must not resurrect a terminated negotiation: DSP treats terminal
 *       states as final, and a consumer that already received a termination has
 *       moved on. Returning the state lets the caller record the race instead of
 *       silently disagreeing with the counterparty about what happened.</li>
 * </ul>
 *
 * <p>The read takes the entity's lease and the write releases it, so a
 * concurrent state-machine pass cannot interleave with the update.
 */
@Path("/dataspaces/negotiations")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public class NegotiationResumeController {

    private final ContractNegotiationStore store;
    private final TransactionContext transactionContext;
    private final Monitor monitor;

    public NegotiationResumeController(
        ContractNegotiationStore store, TransactionContext transactionContext, Monitor monitor
    ) {
        this.store = store;
        this.transactionContext = transactionContext;
        this.monitor = monitor;
    }

    @POST
    @Path("/{id}/resume")
    public Map<String, Object> resume(@PathParam("id") String id) {
        return transactionContext.execute(() -> {
            var lease = store.findByIdAndLease(id);
            if (lease.failed()) {
                ContractNegotiation existing = store.findById(id);
                if (existing == null) {
                    throw new ObjectNotFoundException(ContractNegotiation.class, id);
                }
                // Leased by the state machine right now: it is being processed,
                // which is what we wanted anyway. Report and let the caller retry.
                return response(existing, false, "leased");
            }

            ContractNegotiation negotiation = lease.getContent();
            String state = ContractNegotiationStates.from(negotiation.getState()).name();

            if (isTerminal(negotiation)) {
                store.save(negotiation);
                monitor.info("Negotiation %s is %s — resume ignored".formatted(id, state));
                return response(negotiation, false, "terminal");
            }
            if (!negotiation.isPending()) {
                store.save(negotiation);
                return response(negotiation, false, "not_pending");
            }

            negotiation.setPending(false);
            store.save(negotiation);
            monitor.info("Negotiation %s resumed from %s — consent decided".formatted(id, state));
            return response(negotiation, true, "resumed");
        });
    }

    private static boolean isTerminal(ContractNegotiation negotiation) {
        return negotiation.getState() == ContractNegotiationStates.TERMINATED.code();
    }

    private static Map<String, Object> response(
        ContractNegotiation negotiation, boolean resumed, String outcome
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", negotiation.getId());
        body.put("state", ContractNegotiationStates.from(negotiation.getState()).name());
        body.put("pending", negotiation.isPending());
        body.put("resumed", resumed);
        body.put("outcome", outcome);
        return body;
    }
}
