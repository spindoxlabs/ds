package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.types.offer.ContractOffer;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.Constraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.policy.model.Policy;

import java.util.List;

/**
 * Finding the {@code ds:consentStatus} constraint in a policy.
 *
 * <p>Extracted from {@link ConsentPendingGuard}, which had the only copy, once
 * {@link NegotiationConsentValidator} needed the same answer from a
 * {@link Policy} rather than a {@link ContractOffer}. Two components deciding
 * "is this dataset consent-gated?" by separate string matching is how one of
 * them ends up gating a dataset the other does not.
 */
final class ConsentConstraints {

    /** Both the compact form and the form ODRL's context expands it to. */
    private static final List<String> OPERAND_SUFFIXES = List.of("consentStatus", "ConsentStatus");

    private ConsentConstraints() {
    }

    /**
     * The permission carrying a {@code ds:consentStatus} constraint, or
     * {@code null} when this policy is not consent-gated.
     *
     * <p>Matched on the local name so the profile namespace stays configurable:
     * the operand is {@code {namespace}ConsentStatus}, and the compact
     * {@code ds:consentStatus} appears when the ODRL context was not applied.
     */
    static Permission gatedPermission(Policy policy) {
        if (policy == null || policy.getPermissions() == null) {
            return null;
        }
        for (Permission permission : policy.getPermissions()) {
            if (permission.getConstraints() == null) {
                continue;
            }
            for (Constraint constraint : permission.getConstraints()) {
                if (constraint instanceof AtomicConstraint atomic && isConsentOperand(atomic)) {
                    return permission;
                }
            }
        }
        return null;
    }

    /** As {@link #gatedPermission(Policy)}, for an offer. */
    static Permission gatedPermission(ContractOffer offer) {
        return offer == null ? null : gatedPermission(offer.getPolicy());
    }

    private static boolean isConsentOperand(AtomicConstraint constraint) {
        if (!(constraint.getLeftExpression() instanceof LiteralExpression literal)) {
            return false;
        }
        Object value = literal.getValue();
        if (value == null) {
            return false;
        }
        String operand = value.toString();
        return OPERAND_SUFFIXES.stream().anyMatch(operand::endsWith);
    }
}
