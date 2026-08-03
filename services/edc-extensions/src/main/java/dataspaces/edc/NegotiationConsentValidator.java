package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.policy.ContractNegotiationPolicyContext;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.engine.spi.PolicyValidatorRule;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.policy.model.Policy;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;

/**
 * Enforces {@code ds:consentStatus} at <b>negotiation</b> time — the check
 * {@link ConsentStatusFunction} cannot make.
 *
 * <h2>Why this is not a constraint function</h2>
 *
 * <p>A consent decision needs the dataset. An
 * {@code AtomicConstraintRuleFunction} is handed the {@link Permission}, and
 * {@code Rule} carries no target at EDC 0.16.0; the negotiation context carries
 * only the participant agent:
 *
 * <pre>{@code
 * ContractNegotiationPolicyContext(ParticipantAgent)
 *   participantAgent(), scope()
 * }</pre>
 *
 * <p>So {@link ConsentStatusFunction} read {@code ds.dataset_id} from the
 * agent's attributes — which nothing in the platform sets, and nothing
 * <em>can</em> set, because participant attributes are derived from the verified
 * claim token and are therefore identity-scoped, while the dataset being
 * negotiated is request-scoped. The dataset was always absent, so the function
 * always took its "accept" branch and consent was enforced at negotiation by
 * nothing at all.
 *
 * <p>The dataset <em>is</em> available — on the policy, not on the agent.
 * {@code ContractValidationServiceImpl} targets the policy at the asset before
 * evaluating it, at both of its negotiation call sites:
 *
 * <pre>{@code
 * var contractPolicy = consumerOffer.getTargetedContractPolicy();  // withTarget(offerId.assetIdPart())
 * policyEngine.evaluate(contractPolicy, new ContractNegotiationPolicyContext(agent));
 * }</pre>
 *
 * <p>A {@link PolicyValidatorRule} is {@code BiFunction<Policy, C, Boolean>}, so
 * it receives the whole policy and can read {@link Policy#getTarget()}.
 * {@code ScopeFilter.applyScope} copies the target through, so scope filtering
 * does not lose it.
 *
 * <h2>Why negotiation and not only the data plane</h2>
 *
 * <p>{@code DSSC-AUP-06} — <i>all policies must be enforced during the contract
 * negotiation</i> — is a <b>must</b>, alongside {@code AUP-07} for the sharing
 * itself. Per-query row filtering at the data-plane PEP is {@code AUP-07} and
 * does not discharge {@code AUP-06}: an agreement is a standing, time-bound
 * grant, and one signed for a dataset nobody consented to should never have been
 * signed, whatever the data plane later refuses to serve.
 *
 * <h2>Ordering</h2>
 *
 * <p>Registered as a <b>post</b>-validator, so it runs only after the
 * constraint functions have passed. Membership and purpose are cheaper and
 * answer locally; there is no reason to ask the connector about consent for a
 * consumer who is not a member.
 */
public class NegotiationConsentValidator implements PolicyValidatorRule<ContractNegotiationPolicyContext> {

    private final ConsentApi consent;
    private final Monitor monitor;

    public NegotiationConsentValidator(ConsentApi consent, Monitor monitor) {
        this.consent = consent;
        this.monitor = monitor;
    }

    @Override
    public Boolean apply(Policy policy, ContractNegotiationPolicyContext context) {
        Permission permission = ConsentConstraints.gatedPermission(policy);
        if (permission == null) {
            // Not consent-gated. Nothing to enforce, and saying so is not an
            // exception to the rule — the rule is about policies that carry the
            // constraint.
            return true;
        }

        String datasetId = policy.getTarget();
        if (datasetId == null || datasetId.isBlank()) {
            // Deny. The policy says this dataset is consent-gated and the
            // evaluation cannot say which dataset it is, so there is no question
            // that could be asked, let alone answered. This is the branch whose
            // predecessor accepted.
            monitor.warning(
                "NegotiationConsentValidator: consent-gated policy carries no target — denying. "
                    + "EDC targets the contract policy at the asset before evaluating it, so an "
                    + "absent target means the policy did not arrive through contract validation.");
            return false;
        }

        ParticipantAgent agent = context.participantAgent();
        if (agent == null) {
            monitor.warning("NegotiationConsentValidator: no participant agent for %s — denying".formatted(datasetId));
            return false;
        }

        String consumerId = agent.getIdentity() != null ? agent.getIdentity() : "";
        // Optional: a negotiation naming one data subject rather than asking
        // whether anybody at all consents. Absent is the ordinary case.
        String subjectId = agent.getAttributes().getOrDefault("ds.subject_id", "");
        List<String> purposes = Purposes.of(permission);

        ConsentApi.Decision decision = consent.check(subjectId, datasetId, consumerId, purposes);
        if (decision == null) {
            // `ConsentApi.check` documents this: null means denied. Failing
            // closed here costs a retry — unlike the policy monitor, refusing a
            // negotiation destroys nothing, because there is no agreement yet.
            monitor.warning(
                "NegotiationConsentValidator: consent check unavailable for %s / %s — denying the negotiation"
                    .formatted(datasetId, consumerId));
            return false;
        }

        boolean satisfied = decision.satisfied(!subjectId.isEmpty());
        if (satisfied) {
            // Logged on the *allow* path too, and at info rather than debug.
            // `DSSC-AUP-06` is a requirement to enforce at negotiation, and an
            // enforcement point that is silent when it permits leaves no way to
            // tell "checked and allowed" from "never ran" — which is precisely
            // the state this validator was written to end. It is also the line
            // that shows the check is wired at all, since a green end-to-end run
            // proves nothing on its own.
            monitor.info(
                "NegotiationConsentValidator: consent verified for %s / %s (purposes=%s) — negotiation may proceed"
                    .formatted(datasetId, consumerId, purposes));
        } else {
            monitor.info(
                "NegotiationConsentValidator: no consent covers %s for %s (purposes=%s) — negotiation denied"
                    .formatted(datasetId, consumerId, purposes));
        }
        return satisfied;
    }

    @Override
    public String name() {
        return "ds:consentStatus (negotiation)";
    }
}
