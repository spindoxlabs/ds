package dataspaces.edc;

import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;

/**
 * Evaluates {@code ds:contractRequired eq true}.
 *
 * <p>During contract negotiation, this constraint is always satisfied —
 * the negotiation itself constitutes acceptance of the contract terms.
 * The constraint exists to make the policy intent explicit and readable.
 * Post-DCP, this could verify that a signed bilateral agreement exists.
 */
public class ContractRequiredFunction implements AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext> {

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, ParticipantAgentPolicyContext context) {
        if (operator != Operator.EQ) {
            return false;
        }
        return "true".equalsIgnoreCase(rightValue.toString());
    }
}
