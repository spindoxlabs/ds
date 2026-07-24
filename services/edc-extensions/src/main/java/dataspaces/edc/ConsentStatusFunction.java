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
 * <p>The consumer participant ID is taken from the verified
 * {@link ParticipantAgent} — a DCP-verified credential presentation, not a
 * self-asserted header. Subject and dataset IDs are taken from participant
 * attributes ({@code ds.subject_id}, {@code ds.dataset_id}) when present. For a
 * dataset-level negotiation without a subject attribute, the negotiation is
 * accepted when at least one subject has granted consent for the
 * consumer+dataset pair.
 *
 * <p><b>Purpose.</b> The negotiated purposes are read from the
 * {@code odrl:purpose} constraint on the very permission being evaluated — that
 * is what the provider is offering this dataset for — and passed to the consent
 * check. A subject who consented to a different purpose is not counted, so a
 * negotiation for a purpose nobody agreed to finds an empty subject pool and is
 * denied.
 *
 * <p>The counterpart for an <em>ongoing</em> transfer is
 * {@link AgreementConsentFunction}, bound to the {@code policy.monitor} scope:
 * this function decides whether access may start, that one decides whether it
 * may continue.
 */
public class ConsentStatusFunction implements AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext> {

    private final ConsentApi consent;
    private final Monitor monitor;

    public ConsentStatusFunction(ConsentApi consent, Monitor monitor) {
        this.consent = consent;
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, ParticipantAgentPolicyContext context) {
        if (operator != Operator.EQ) return false;
        String expectedStatus = rightValue.toString();
        if (!"active".equals(expectedStatus) && !"granted".equals(expectedStatus)) return false;

        ParticipantAgent agent = context.participantAgent();
        if (agent == null) return false;

        String consumerId = agent.getIdentity();
        String subjectId = agent.getAttributes().getOrDefault("ds.subject_id", "");
        String datasetId = agent.getAttributes().getOrDefault("ds.dataset_id", "");

        if (datasetId.isEmpty()) {
            monitor.info("ConsentStatusFunction: ds.dataset_id not in participant attributes — accepting (membership already validated)");
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
