package dataspaces.edc;

import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;

/**
 * Evaluates {@code {namespace}ConsentStatus eq "active"} at <b>negotiation</b>
 * time, by querying ds-connector's consent check.
 *
 * <p><b>This function is not the negotiation-time enforcement point, and it
 * cannot be.</b> A consent decision needs the dataset; a constraint function is
 * handed the {@link Permission}, and {@code Rule} has no target at EDC 0.16.0.
 * It therefore reads {@code ds.dataset_id} from the participant attributes —
 * which nothing sets and nothing can, because participant attributes come from
 * the verified claim token and are identity-scoped, while the dataset being
 * negotiated is request-scoped. That branch is taken on every negotiation.
 *
 * <p>{@link NegotiationConsentValidator} is the enforcement point
 * ({@code DSSC-AUP-06}): a {@code PolicyValidatorRule} receives the whole
 * {@link org.eclipse.edc.policy.model.Policy}, which EDC has targeted at the
 * asset. This function stays registered because the operand must stay
 * <em>bound</em> — EDC's {@code ScopeFilter} removes an unbound operand, and a
 * permission stripped of its only constraint becomes unconditional — and a bound
 * operand with no registered function fails evaluation outright.
 *
 * <p>The consumer participant ID is taken from the verified
 * {@link ParticipantAgent} — a DCP-verified credential presentation, not a
 * self-asserted header. If a deployment ever does supply {@code ds.subject_id}
 * and {@code ds.dataset_id}, the check below runs and is authoritative for that
 * negotiation.
 *
 * <p><b>Purpose.</b> The negotiated purposes are read from the
 * {@code odrl:purpose} constraint on the very permission being evaluated — that
 * is what the provider is offering this dataset for — and passed to the consent
 * check. A subject who consented to a different purpose is not counted, so a
 * negotiation for a purpose nobody agreed to finds an empty subject pool and is
 * denied.
 *
 * <p>The counterpart for a transfer is {@link AgreementConsentFunction}, which
 * reads the signed agreement and is registered in both the {@code
 * transfer.process} scope (may access start?) and {@code policy.monitor} (may it
 * continue?).
 *
 * <p>Generic in the context type: registered on
 * {@code ContractNegotiationPolicyContext} only, because the engine matches a
 * function with {@code contextType().isAssignableFrom(context.getClass())} and
 * the catalogue and transfer contexts also implement
 * {@link ParticipantAgentPolicyContext}. Registering on the interface put this
 * function in the transfer scope too, where it would have shadowed the
 * agreement-backed check by key collision.
 */
public class ConsentStatusFunction<C extends ParticipantAgentPolicyContext>
    implements AtomicConstraintRuleFunction<Permission, C> {

    private final ConsentApi consent;
    private final Monitor monitor;

    public ConsentStatusFunction(ConsentApi consent, Monitor monitor) {
        this.consent = consent;
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, C context) {
        if (operator != Operator.EQ) return false;
        // Not `rightValue.toString()`: an expanded policy yields "\"granted\"",
        // quotes included, so the comparison below failed on precisely the
        // policies that took the expanded path — and failed by denying, with
        // nothing said.
        String expectedStatus = Purposes.unwrapScalar(rightValue);
        if (expectedStatus == null) {
            monitor.warning("ConsentStatusFunction: unreadable consent operand %s — denying"
                .formatted(Purposes.describeValue(rightValue)));
            return false;
        }
        if (!"active".equals(expectedStatus) && !"granted".equals(expectedStatus)) return false;

        ParticipantAgent agent = context.participantAgent();
        if (agent == null) return false;

        String consumerId = agent.getIdentity();
        String subjectId = agent.getAttributes().getOrDefault("ds.subject_id", "");
        String datasetId = agent.getAttributes().getOrDefault("ds.dataset_id", "");

        if (datasetId.isEmpty()) {
            // **Not an accept.** This is the ordinary case — nothing sets
            // `ds.dataset_id`, and nothing can, so this branch is taken on every
            // negotiation. The dataset-aware decision is
            // NegotiationConsentValidator's, registered as a post-validator on
            // the same scope, which reads the dataset off `Policy.getTarget()`.
            // Post-validators run only after the constraint functions pass, so
            // returning true here defers to it; returning false would deny every
            // negotiation before it could run.
            //
            // `PolicyRegistrationTest` asserts that validator is registered,
            // because without it this line *is* the bypass it used to be.
            monitor.debug(() -> "ConsentStatusFunction: no ds.dataset_id — deferring to NegotiationConsentValidator");
            return true;
        }

        List<String> purposes = Purposes.of(rule);
        ConsentApi.Decision decision = consent.check(
            subjectId, datasetId, consumerId != null ? consumerId : "", purposes
        );
        if (decision == null) {
            return false;
        }
        return decision.satisfied(!subjectId.isEmpty());
    }
}
