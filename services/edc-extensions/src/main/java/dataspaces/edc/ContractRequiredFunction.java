package dataspaces.edc;

import org.eclipse.edc.policy.engine.spi.AtomicConstraintFunction;
import org.eclipse.edc.policy.engine.spi.PolicyContext;
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
public class ContractRequiredFunction implements AtomicConstraintFunction<Permission> {

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, PolicyContext context) {
        if (operator != Operator.EQ) {
            return false;
        }
        // Negotiation proceeding means the contract requirement is being satisfied
        // A "true" right-value means the constraint is active and accepted by negotiation
        return "true".equalsIgnoreCase(rightValue.toString());
    }
}
