package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.ContractNegotiationPolicyContext;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.model.Action;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The two constraint functions that run at negotiation and decide the least.
 *
 * <p>{@link ConsentStatusFunction} cannot see a dataset and therefore cannot
 * decide consent; {@link PurposeFunction} reports what the provider offers the
 * dataset for and is not itself an access decision. Both exist because their
 * operands must stay <em>bound</em> — an unbound operand is removed from the
 * policy by EDC's {@code ScopeFilter}, and a permission stripped of its only
 * constraint becomes unconditional — and a bound operand with no function fails
 * evaluation outright.
 *
 * <p>So both are, deliberately, pass-throughs with a narrow job. These tests pin
 * that job, and in particular the difference between "true because it is not
 * mine to refuse" and "true because I could not read the question".
 */
class NegotiationScopeFunctionsTest {

    private static class NoopMonitor implements Monitor {
    }

    private static ContractNegotiationPolicyContext context(Map<String, String> attributes) {
        return new ContractNegotiationPolicyContext(
            new ParticipantAgent("did:web:third-party.dataspaces.localhost", Map.of(), attributes));
    }

    private static Permission gatedPermission() {
        return Permission.Builder.newInstance()
            .action(Action.Builder.newInstance().type("odrl:use").build())
            .constraint(AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression("odrl:purpose"))
                .operator(Operator.IS_ANY_OF)
                .rightExpression(new LiteralExpression(
                    List.of("https://w3id.org/dsp/policy/purpose/FlexibilityResearch")))
                .build())
            .build();
    }

    private static ConsentStatusFunction<ContractNegotiationPolicyContext> consent(
        AtomicInteger calls, String answer
    ) {
        var connector = new ConnectorClient("http://ds-connector:30001", b -> true, new NoopMonitor()) {
            @Override
            public JsonNode getJson(String path, Map<String, String> query) {
                calls.incrementAndGet();
                try {
                    return answer == null ? null : new ObjectMapper().readTree(answer);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }
        };
        return new ConsentStatusFunction<>(new ConsentApi(connector), new NoopMonitor());
    }

    // ── ConsentStatusFunction ────────────────────────────────────────────────

    @Tag("rule:A-11")
    @Test
    void withNoDatasetItDefersInsteadOfDeciding() {
        // The ordinary case, and it is every negotiation: nothing sets
        // `ds.dataset_id` and nothing can, because participant attributes come
        // from the verified claim token and are identity-scoped while the
        // dataset is request-scoped. Returning false here would deny every
        // negotiation before NegotiationConsentValidator — the post-validator
        // that *does* have the dataset — could run.
        var calls = new AtomicInteger();
        assertTrue(consent(calls, null).evaluate(
            Operator.EQ, "active", gatedPermission(), context(Map.of())));
        assertEquals(0, calls.get(), "with no dataset there is no question to ask");
    }

    @Test
    void withADatasetSuppliedItActuallyChecks() {
        // A deployment that does contribute both attributes gets a real check,
        // and it is authoritative for that negotiation.
        var calls = new AtomicInteger();
        var attributes = Map.of("ds.dataset_id", "datasets.silver.meters_15m", "ds.subject_id", "s-1");

        assertTrue(consent(calls, "{\"consent_active\": true, \"subject_ids\": [\"s-1\"]}")
            .evaluate(Operator.EQ, "active", gatedPermission(), context(attributes)));
        assertFalse(consent(calls, "{\"consent_active\": false, \"subject_ids\": []}")
            .evaluate(Operator.EQ, "active", gatedPermission(), context(attributes)));
        assertFalse(consent(calls, null)
            .evaluate(Operator.EQ, "active", gatedPermission(), context(attributes)),
            "an unanswerable check is not a licence to proceed");
    }

    @Tag("rule:A-11")
    @Test
    void anUnreadableStatusOperandDeniesRatherThanDeferring() {
        // The distinction this file is about. Deferring is right when the
        // question belongs to the validator; it is wrong when the operand itself
        // could not be read, because then nothing knows what was asked.
        var calls = new AtomicInteger();
        assertFalse(consent(calls, null).evaluate(
            Operator.EQ, List.of("active", "granted"), gatedPermission(), context(Map.of())));
    }

    @Test
    void anExpandedStatusOperandIsUnwrapped() {
        // toString() on {"@value": "active"} yields an object dump, which matches
        // neither "active" nor "granted" — so the function denied on precisely
        // the policies that took the expanded path.
        var calls = new AtomicInteger();
        assertTrue(consent(calls, null).evaluate(
            Operator.EQ, Map.of("@value", "active"), gatedPermission(), context(Map.of())));
    }

    @Tag("rule:A-11")
    @Test
    void aStatusItDoesNotUnderstandDenies() {
        var calls = new AtomicInteger();
        assertFalse(consent(calls, null).evaluate(
            Operator.EQ, "revoked", gatedPermission(), context(Map.of())));
    }

    @Tag("rule:A-11")
    @Test
    void anOperatorOtherThanEqualsDenies() {
        var calls = new AtomicInteger();
        assertFalse(consent(calls, null).evaluate(
            Operator.NEQ, "active", gatedPermission(), context(Map.of())));
    }

    // ── PurposeFunction ──────────────────────────────────────────────────────

    @Test
    void purposeAcceptsTheThreeShapesAProfileCanDeclare() {
        var function = new PurposeFunction<ContractNegotiationPolicyContext>(new NoopMonitor());
        for (Operator operator : List.of(Operator.IS_A, Operator.IS_ANY_OF, Operator.EQ)) {
            assertTrue(function.evaluate(operator, "FlexibilityResearch", gatedPermission(), context(Map.of())),
                operator + " should be accepted");
        }
    }

    @Tag("rule:A-11")
    @Test
    void purposeDeniesAnOperatorItCannotInterpret() {
        var function = new PurposeFunction<ContractNegotiationPolicyContext>(new NoopMonitor());
        assertFalse(function.evaluate(
            Operator.GT, "FlexibilityResearch", gatedPermission(), context(Map.of())));
    }

    @Tag("rule:A-11")
    @Test
    void purposeDeniesWhenTheConstraintNamesNothing() {
        // An empty purpose is not "any purpose": the connector denies a
        // consent-gated dataset whose caller never said why.
        var function = new PurposeFunction<ContractNegotiationPolicyContext>(new NoopMonitor());
        assertFalse(function.evaluate(Operator.IS_ANY_OF, null, gatedPermission(), context(Map.of())));
    }
}
