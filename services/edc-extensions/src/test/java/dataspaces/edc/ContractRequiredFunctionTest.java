package dataspaces.edc;

import jakarta.json.Json;
import jakarta.json.JsonValue;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.ContractNegotiationPolicyContext;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * {@code ds:contractRequired}, which used to be {@code (op, rv, duty, ctx) -> true}.
 *
 * <p>The verdict was not the problem — a contract is being formed at negotiation
 * scope, so {@code eq true} is genuinely satisfied. The problem was that nothing
 * looked: every operator and every right operand produced the same answer, so a
 * constraint that could never fail was indistinguishable from one that was
 * carefully written. These tests are about the inputs it now rejects.
 */
class ContractRequiredFunctionTest {

    private static class NoopMonitor implements Monitor {
    }

    private final ContractRequiredFunction<ContractNegotiationPolicyContext> function =
        new ContractRequiredFunction<>(new NoopMonitor());

    private final ContractNegotiationPolicyContext context =
        new ContractNegotiationPolicyContext(new ParticipantAgent("consumer", Map.of(), Map.of()));

    private final Permission permission = Permission.Builder.newInstance().build();

    private boolean evaluate(Operator operator, Object rightValue) {
        return function.evaluate(operator, rightValue, permission, context);
    }

    // ── what it should accept ────────────────────────────────────────────────

    @Test
    void contractRequiredIsSatisfiedAtNegotiation() {
        assertTrue(evaluate(Operator.EQ, "true"));
    }

    @Test
    void contractNotRequiredIsTriviallySatisfied() {
        // "no contract required" is not a reason to refuse a negotiation.
        assertTrue(evaluate(Operator.NEQ, "false"));
    }

    @Test
    void readsTheExpandedJsonLdShape() {
        // A policy that reached the store through EDC's JSON-LD expansion carries
        // JsonString, whose toString() includes the quotes — so a bare
        // toString().equals("true") fails on exactly those policies, and fails by
        // denying with no explanation. Same trap Purposes documents.
        assertTrue(evaluate(Operator.EQ, Json.createValue("true")));
    }

    @Test
    void readsTheWrappedValueObject() {
        JsonValue wrapped = Json.createObjectBuilder().add("@value", "true").build();
        assertTrue(evaluate(Operator.EQ, wrapped));
    }

    @Test
    void readsASingletonList() {
        assertTrue(evaluate(Operator.EQ, List.of("true")));
    }

    @Test
    void isCaseInsensitive() {
        assertTrue(evaluate(Operator.EQ, "TRUE"));
    }

    // ── what it must now refuse ──────────────────────────────────────────────

    @Test
    void denyingOperandsAreNotSilentlySatisfied() {
        // `contractRequired neq true` says a contract must NOT be required. At
        // negotiation scope one is being formed, so it is not satisfied — and it
        // used to be.
        assertFalse(evaluate(Operator.NEQ, "true"));
    }

    @Test
    void anOperatorThatIsNotMeaningfulOverABooleanDenies() {
        for (Operator operator : List.of(Operator.GT, Operator.LT, Operator.IN, Operator.IS_ANY_OF)) {
            assertFalse(evaluate(operator, "true"), operator + " must not satisfy a boolean constraint");
        }
    }

    @Test
    void anUnparseableOperandDenies() {
        // A policy author's typo. It used to pass, which is the worst outcome:
        // the constraint looks enforced and cannot fail.
        for (Object value : List.of("yes", "1", "", "granted", "TRUEISH")) {
            assertFalse(evaluate(Operator.EQ, value), value + " must not parse as a boolean");
        }
    }

    @Test
    void aNullOperandDenies() {
        assertFalse(evaluate(Operator.EQ, null));
    }

    @Test
    void anAmbiguousCollectionDenies() {
        // Two values do not reduce to one boolean, so there is nothing to compare.
        assertFalse(evaluate(Operator.EQ, List.of("true", "false")));
    }
}
