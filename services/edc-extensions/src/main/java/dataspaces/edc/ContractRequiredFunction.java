package dataspaces.edc;

import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.engine.spi.PolicyContext;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

/**
 * Evaluates {@code ds:contractRequired}, bound to {@code contract.negotiation}.
 *
 * <p>It replaces the lambda {@code (op, rv, duty, ctx) -> true}, which satisfied
 * the constraint for <b>every</b> operator and <b>every</b> right operand. The
 * problem was not the verdict — a contract is being formed, so
 * {@code contractRequired eq true} is genuinely satisfied at negotiation — it
 * was that nothing looked. {@code ds:contractRequired neq true},
 * {@code ds:contractRequired eq "yes"} and {@code ds:contractRequired gt 5} all
 * passed identically, so a policy author's typo produced a constraint that could
 * never fail and said nothing about it. Rulebook {@code CR-4}: an undecidable
 * constraint is a denial, never a permission.
 *
 * <p>What it now checks:
 *
 * <ul>
 *   <li>the operator is {@link Operator#EQ} or {@link Operator#NEQ} — no other
 *       relation is meaningful over a boolean;</li>
 *   <li>the right operand parses as a boolean, after JSON-LD unwrapping, since a
 *       policy that has been through EDC's expansion carries its operands as
 *       {@code JsonString}/{@code JsonObject} rather than {@code String};</li>
 *   <li>anything else denies, loudly.</li>
 * </ul>
 *
 * <p>This function is bound to the negotiation scope only, where a contract is
 * by definition being formed — so {@code eq true} is satisfied and
 * {@code eq false} ("no contract required") is trivially satisfied too. The
 * value it adds is refusing a constraint nobody can have meant, not a new way to
 * deny.
 */
public class ContractRequiredFunction<C extends PolicyContext>
    implements AtomicConstraintRuleFunction<Permission, C> {

    private final Monitor monitor;

    public ContractRequiredFunction(Monitor monitor) {
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, C context) {
        if (operator != Operator.EQ && operator != Operator.NEQ) {
            monitor.warning(
                "ContractRequiredFunction: operator %s is not meaningful over a boolean — denying"
                    .formatted(operator));
            return false;
        }

        Boolean required = asBoolean(rightValue);
        if (required == null) {
            monitor.warning(
                "ContractRequiredFunction: right operand %s does not parse as a boolean — denying"
                    .formatted(Purposes.describeValue(rightValue)));
            return false;
        }

        // A contract is being formed: that is what this scope *is*. `eq true` is
        // therefore satisfied, and `neq true` — "a contract must not be
        // required" — is not.
        boolean contractIsBeingFormed = true;
        return operator == Operator.EQ
            ? required == contractIsBeingFormed
            : required != contractIsBeingFormed;
    }

    /**
     * {@code rightValue} as a boolean, or {@code null} if it is not one.
     *
     * <p>Unwrapped first: a policy that reached the store through EDC's JSON-LD
     * expansion carries {@code JsonString}/{@code JsonObject}, whose
     * {@code toString()} includes the quotes — so a bare {@code toString()}
     * comparison against {@code "true"} fails on exactly the policies that took
     * the expanded path. Same trap {@link Purposes} documents.
     */
    static Boolean asBoolean(Object rightValue) {
        String text = Purposes.unwrapScalar(rightValue);
        if (text == null) {
            return null;
        }
        text = text.trim();
        if ("true".equalsIgnoreCase(text)) {
            return Boolean.TRUE;
        }
        if ("false".equalsIgnoreCase(text)) {
            return Boolean.FALSE;
        }
        return null;
    }
}
