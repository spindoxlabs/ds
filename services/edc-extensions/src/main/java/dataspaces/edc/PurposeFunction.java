package dataspaces.edc;

import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

/**
 * Evaluates the {@code odrl:purpose} constraint carried by a permission.
 *
 * <p>The constraint declares which purposes the provider offers this dataset
 * for. It is not, on its own, the access decision: a purpose the provider
 * permits still yields no rows for a data subject who did not consent to it.
 * That binding check lives in {@link ConsentStatusFunction}, which reads the
 * same constraint off the permission and passes the purposes to ds-connector.
 *
 * <p>Registering this function is what stops the purpose being decorative.
 * Without it the constraint would be unbound, EDC would evaluate it to false,
 * and every negotiation for a purpose-scoped dataset would be denied.
 */
public class PurposeFunction implements AtomicConstraintRuleFunction<Permission, ParticipantAgentPolicyContext> {

    private final Monitor monitor;

    public PurposeFunction(Monitor monitor) {
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, ParticipantAgentPolicyContext context) {
        if (rightValue == null) {
            monitor.warning("PurposeFunction: purpose constraint has no right operand — denying");
            return false;
        }
        // isA (single purpose) and isAnyOf (a multi-purpose dataset) are the
        // two shapes the governance mapper emits; eq is accepted for profiles
        // that model a single exact purpose.
        return operator == Operator.IS_A
            || operator == Operator.IS_ANY_OF
            || operator == Operator.EQ;
    }
}
