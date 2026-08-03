package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.policy.ContractNegotiationPolicyContext;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.engine.spi.DynamicAtomicConstraintRuleFunction;
import org.eclipse.edc.policy.engine.spi.PolicyContext;
import org.eclipse.edc.policy.engine.spi.PolicyEngine;
import org.eclipse.edc.policy.engine.spi.PolicyRuleFunction;
import org.eclipse.edc.policy.engine.spi.PolicyValidatorRule;
import org.eclipse.edc.policy.engine.spi.RuleBindingRegistry;
import org.eclipse.edc.policy.model.Policy;
import org.eclipse.edc.policy.model.Rule;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.result.Result;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * What the extension actually binds and registers.
 *
 * <p>EDC's {@code ScopeFilter} <b>removes</b> an operand that is not bound to
 * the scope being evaluated, rather than failing it. So a binding mistake does
 * not raise: it deletes a check, and a permission stripped of its only
 * constraint becomes unconditional. Nothing in this repository could see that
 * surface before {@code registerPolicy} was separable — which is how
 * {@code ds:accessScope} came to be bound with no function, and how the
 * negotiation-scope consent check came to be enforced by nothing.
 *
 * <p>These assertions are cheap and they are the ones that fail loudly when
 * somebody deletes a line that looks redundant.
 */
class PolicyRegistrationTest {

    private static final String NAMESPACE = "https://w3id.org/dsp/policy/";
    private static final String NEGOTIATION = "contract.negotiation";
    private static final String MONITOR = PolicyMonitorContext.POLICY_MONITOR_SCOPE;

    private RecordingEngine engine;
    private RecordingBindings bindings;

    // ── doubles ──────────────────────────────────────────────────────────────

    private record Registration(Class<?> contextType, String key) {
    }

    private static class RecordingEngine implements PolicyEngine {
        final List<Registration> functions = new ArrayList<>();
        final List<Registration> postValidators = new ArrayList<>();
        final List<Registration> preValidators = new ArrayList<>();

        @Override
        public <C extends PolicyContext> Result<Void> evaluate(Policy policy, C context) {
            return Result.success();
        }

        @Override
        public Policy filter(Policy policy, String scope) {
            return policy;
        }

        @Override
        public <C extends PolicyContext> void registerScope(String scope, Class<C> contextType) {
        }

        @Override
        public <R extends Rule, C extends PolicyContext> void registerFunction(
            Class<C> contextType, Class<R> type, String key, AtomicConstraintRuleFunction<R, C> function) {
            functions.add(new Registration(contextType, key));
        }

        @Override
        public <R extends Rule, C extends PolicyContext> void registerFunction(
            Class<C> contextType, Class<R> type, DynamicAtomicConstraintRuleFunction<R, C> function) {
            functions.add(new Registration(contextType, "<dynamic>"));
        }

        @Override
        public <R extends Rule, C extends PolicyContext> void registerFunction(
            Class<C> contextType, Class<R> type, PolicyRuleFunction<R, C> function) {
            functions.add(new Registration(contextType, "<rule>"));
        }

        @Override
        public <C extends PolicyContext> void registerPreValidator(
            Class<C> contextType, PolicyValidatorRule<C> validator) {
            preValidators.add(new Registration(contextType, validator.getClass().getSimpleName()));
        }

        @Override
        public <C extends PolicyContext> void registerPostValidator(
            Class<C> contextType, PolicyValidatorRule<C> validator) {
            postValidators.add(new Registration(contextType, validator.getClass().getSimpleName()));
        }

        @Override
        public Result<Void> validate(Policy policy) {
            return Result.success();
        }

        @Override
        public org.eclipse.edc.policy.engine.spi.plan.PolicyEvaluationPlan createEvaluationPlan(String scope, Policy policy) {
            throw new UnsupportedOperationException("not exercised by this test");
        }

        Set<String> keysFor(Class<?> contextType) {
            Set<String> keys = new LinkedHashSet<>();
            for (Registration r : functions) {
                if (r.contextType().equals(contextType)) {
                    keys.add(r.key());
                }
            }
            return keys;
        }
    }

    private static class RecordingBindings implements RuleBindingRegistry {
        final List<Registration> bound = new ArrayList<>();

        @Override
        public void bind(String ruleType, String scope) {
            bound.add(new Registration(String.class, ruleType + "@" + scope));
        }

        @Override
        public void dynamicBind(java.util.function.Function<String, Set<String>> resolver) {
        }

        @Override
        public boolean isInScope(String ruleType, String scope) {
            return bound.stream().anyMatch(r -> r.key().equals(ruleType + "@" + scope));
        }

        @Override
        public Set<String> bindings(String scope) {
            return operandsIn(scope);
        }

        Set<String> operandsIn(String scope) {
            Set<String> keys = new LinkedHashSet<>();
            for (Registration r : bound) {
                if (r.key().endsWith("@" + scope)) {
                    keys.add(r.key().substring(0, r.key().length() - scope.length() - 1));
                }
            }
            return keys;
        }
    }

    private static class NoopMonitor implements Monitor {
    }

    @BeforeEach
    void register() {
        engine = new RecordingEngine();
        bindings = new RecordingBindings();
        ConnectorClient connector = new ConnectorClient("http://ds-connector:30001", b -> true, new NoopMonitor());
        DataspacesExtension.registerPolicy(
            engine, bindings, connector, new ConsentApi(connector), NAMESPACE, 60L, new NoopMonitor()
        );
    }

    // ── the consent bypass ───────────────────────────────────────────────────

    @Test
    void theNegotiationConsentValidatorIsRegistered() {
        // The one registration that makes `ds:consentStatus` mean anything at
        // negotiation. `ConsentStatusFunction` cannot decide — it has no
        // dataset — so without this line the operand is bound, evaluated, and
        // unconditionally satisfied. That was HEAD.
        assertTrue(
            engine.postValidators.stream().anyMatch(r ->
                r.contextType().equals(ContractNegotiationPolicyContext.class)
                    && r.key().equals("NegotiationConsentValidator")),
            "no NegotiationConsentValidator on the negotiation context — consent is not enforced "
                + "at negotiation, which DSSC-AUP-06 requires"
        );
    }

    @Test
    void theValidatorIsScopedToNegotiationOnly() {
        // Not ParticipantAgentPolicyContext: the engine matches validators with
        // `contextType().isAssignableFrom(context.getClass())`, and the catalog
        // and transfer contexts implement that interface too. Registering there
        // would run a consent check during catalog browsing.
        assertFalse(
            engine.postValidators.stream().anyMatch(r ->
                r.contextType().equals(ParticipantAgentPolicyContext.class)),
            "the consent validator must not be registered on the broad participant-agent context"
        );
    }

    // ── binding invariants ───────────────────────────────────────────────────

    @Test
    void consentStaysBoundInBothScopes() {
        // An unbound operand is *removed* by ScopeFilter, and a permission whose
        // only constraint was removed becomes unconditional. So unbinding the
        // operand is strictly worse than a function that returns true.
        for (String scope : List.of(NEGOTIATION, MONITOR)) {
            Set<String> operands = bindings.operandsIn(scope);
            assertTrue(operands.contains("ds:consentStatus"), "ds:consentStatus unbound in " + scope);
            assertTrue(operands.contains(NAMESPACE + "ConsentStatus"),
                "expanded consent operand unbound in " + scope);
        }
    }

    @Test
    void consentHasAFunctionInBothScopes() {
        // A bound operand with no registered function fails evaluation outright,
        // which denies every negotiation rather than the intended ones.
        assertTrue(engine.keysFor(ParticipantAgentPolicyContext.class).contains(NAMESPACE + "ConsentStatus"));
        assertTrue(engine.keysFor(PolicyMonitorContext.class).contains(NAMESPACE + "ConsentStatus"));
        assertTrue(engine.keysFor(PolicyMonitorContext.class).contains("ds:consentStatus"));
    }

    @Test
    void negotiationOnlyOperandsAreNotBoundInTheMonitorScope() {
        // Membership and contractRequired are conditions on *entering* an
        // agreement. Leaving them unbound in policy.monitor is how they are
        // excluded — deliberate, and easy to "fix" by mistake.
        Set<String> monitorOperands = bindings.operandsIn(MONITOR);
        assertFalse(monitorOperands.contains(NAMESPACE + "Membership"));
        assertFalse(monitorOperands.contains("ds:contractRequired"));
    }

    @Test
    void purposeIsBoundInBothScopes() {
        // Not because a purpose can change mid-transfer, but because the consent
        // functions read purposes off the permission they are handed; a filtered
        // purpose constraint leaves them asking an unscoped question.
        for (String scope : List.of(NEGOTIATION, MONITOR)) {
            Set<String> operands = bindings.operandsIn(scope);
            assertTrue(operands.contains(Purposes.COMPACT), "odrl:purpose unbound in " + scope);
            assertTrue(operands.contains(Purposes.EXPANDED), "expanded purpose unbound in " + scope);
        }
    }

    @Test
    void everyBoundActionIsBoundInBothScopes() {
        // An unbound *action* strips the whole permission, consent constraint
        // and all — the quietest way to disable enforcement in this file.
        Set<String> negotiation = bindings.operandsIn(NEGOTIATION);
        Set<String> monitor = bindings.operandsIn(MONITOR);
        for (String action : List.of("ds:query", "odrl:use", "odrl:transfer", "odrl:aggregate")) {
            assertTrue(negotiation.contains(action), action + " unbound in " + NEGOTIATION);
            assertTrue(monitor.contains(action), action + " unbound in " + MONITOR);
        }
    }
}
