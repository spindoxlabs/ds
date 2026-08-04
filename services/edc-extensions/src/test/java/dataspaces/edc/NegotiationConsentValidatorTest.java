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
import org.eclipse.edc.policy.model.Policy;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Consent, enforced at negotiation — {@code DSSC-AUP-06}.
 *
 * <p>Before this validator existed, every test here would have passed against
 * {@link ConsentStatusFunction} returning {@code true}, because that is what it
 * returned for every input. That is the point of asserting the *denials*: the
 * defect was not a wrong answer, it was the absence of a question.
 */
class NegotiationConsentValidatorTest {

    private static final String DATASET = "datasets.silver.meters_15m";
    private static final String CONSUMER = "did:web:third-party.dataspaces.localhost";

    private final ObjectMapper mapper = new ObjectMapper();

    // ── doubles ──────────────────────────────────────────────────────────────

    /** A connector whose answer to `/internal/consent/check` is whatever we say. */
    private static class FakeConnector extends ConnectorClient {
        private final String json;
        private String lastPath;
        private Map<String, String> lastQuery;

        FakeConnector(String json) {
            super("http://ds-connector:30001", builder -> true, new NoopMonitor());
            this.json = json;
        }

        @Override
        public JsonNode getJson(String path, Map<String, String> query) {
            this.lastPath = path;
            this.lastQuery = query;
            if (json == null) {
                return null;
            }
            try {
                return new ObjectMapper().readTree(json);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }
    }

    private static class NoopMonitor implements Monitor {
    }

    private static Policy gatedPolicy(String target) {
        Permission permission = Permission.Builder.newInstance()
            .action(Action.Builder.newInstance().type("ds:query").build())
            .constraint(AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression("ds:consentStatus"))
                .operator(Operator.EQ)
                .rightExpression(new LiteralExpression("granted"))
                .build())
            .constraint(AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression("odrl:purpose"))
                .operator(Operator.IS_ANY_OF)
                .rightExpression(new LiteralExpression("FlexibilityResearch"))
                .build())
            .build();
        Policy policy = Policy.Builder.newInstance().permission(permission).build();
        return target == null ? policy : policy.withTarget(target);
    }

    private static Policy ungatedPolicy(String target) {
        Permission permission = Permission.Builder.newInstance()
            .action(Action.Builder.newInstance().type("ds:query").build())
            .build();
        return Policy.Builder.newInstance().permission(permission).build().withTarget(target);
    }

    private static ContractNegotiationPolicyContext contextFor(Map<String, String> attributes) {
        return new ContractNegotiationPolicyContext(
            new ParticipantAgent(CONSUMER, Map.of(), attributes)
        );
    }

    private static ContractNegotiationPolicyContext context() {
        return contextFor(Map.of());
    }

    private NegotiationConsentValidator validator(String json) {
        return new NegotiationConsentValidator(new ConsentApi(new FakeConnector(json)), new NoopMonitor());
    }

    // ── the defect ───────────────────────────────────────────────────────────

    @Test
    void deniesWhenNobodyConsents() {
        // The negotiation this platform has never once refused: a consent-gated
        // dataset for which no subject has granted anything.
        var validator = validator("{\"consent_active\": false, \"subject_ids\": []}");
        assertFalse(validator.apply(gatedPolicy(DATASET), context()));
    }

    @Test
    void allowsWhenAtLeastOneSubjectConsents() {
        var validator = validator(
            "{\"consent_active\": false, \"subject_ids\": [\"did:web:users.dataspaces.localhost:data-subject\"]}");
        assertTrue(validator.apply(gatedPolicy(DATASET), context()));
    }

    @Test
    void readsTheDatasetFromThePolicyTarget() {
        // The whole reason this is a validator and not a constraint function.
        var connector = new FakeConnector("{\"consent_active\": true, \"subject_ids\": [\"s\"]}");
        var validator = new NegotiationConsentValidator(new ConsentApi(connector), new NoopMonitor());

        validator.apply(gatedPolicy(DATASET), context());

        assertEquals("/internal/consent/check", connector.lastPath);
        assertEquals(DATASET, connector.lastQuery.get("dataset_id"));
        assertEquals(CONSUMER, connector.lastQuery.get("consumer_id"));
    }

    @Test
    void sendsTheNegotiatedPurpose() {
        // A subject who consented to a different purpose must not be counted, so
        // the purpose has to reach the connector at all.
        var connector = new FakeConnector("{\"consent_active\": true, \"subject_ids\": [\"s\"]}");
        new NegotiationConsentValidator(new ConsentApi(connector), new NoopMonitor())
            .apply(gatedPolicy(DATASET), context());

        assertEquals("FlexibilityResearch", connector.lastQuery.get("purpose"));
    }

    // ── failing closed ───────────────────────────────────────────────────────

    @Test
    void deniesWhenTheConnectorCannotAnswer() {
        // `ConsentApi.check` documents null as denied. Unlike the policy
        // monitor, refusing here destroys nothing — there is no agreement yet.
        assertFalse(validator(null).apply(gatedPolicy(DATASET), context()));
    }

    @Test
    void deniesWhenThePolicyCarriesNoTarget() {
        // The branch whose predecessor accepted. A consent-gated policy whose
        // dataset cannot be determined is not a question that can be answered.
        assertFalse(validator("{\"consent_active\": true, \"subject_ids\": [\"s\"]}")
            .apply(gatedPolicy(null), context()));
    }

    // ── not over-reaching ────────────────────────────────────────────────────

    @Test
    void ignoresAPolicyThatIsNotConsentGated() {
        // Every negotiation for an open dataset would otherwise be denied, and
        // a fix that denies everything is not a fix.
        assertTrue(validator(null).apply(ungatedPolicy("datasets.gold.om_weather_features"), context()));
    }

    @Test
    void aNamedSubjectIsAskedAboutDirectly() {
        // With `ds.subject_id` present the question is about that person, so an
        // empty pool is not the criterion — `consent_active` is.
        var validator = validator("{\"consent_active\": true, \"subject_ids\": []}");
        var ctx = contextFor(Map.of("ds.subject_id", "did:web:users.dataspaces.localhost:data-subject"));
        assertTrue(validator.apply(gatedPolicy(DATASET), ctx));
    }

    @Test
    void anUnnamedSubjectIsAskedAboutThePool() {
        // Without a named subject, `consent_active` alone must not satisfy it —
        // that field is about a subject nobody named.
        var validator = validator("{\"consent_active\": true, \"subject_ids\": []}");
        assertFalse(validator.apply(gatedPolicy(DATASET), context()));
    }

    @Test
    void matchesTheExpandedOperandToo() {
        // The namespace is configurable and the ODRL context may or may not have
        // been applied, so the operand arrives in two shapes.
        Permission permission = Permission.Builder.newInstance()
            .action(Action.Builder.newInstance().type("ds:query").build())
            .constraint(AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression("https://w3id.org/dsp/policy/ConsentStatus"))
                .operator(Operator.EQ)
                .rightExpression(new LiteralExpression("granted"))
                .build())
            .build();
        Policy policy = Policy.Builder.newInstance().permission(permission).build().withTarget(DATASET);

        assertFalse(validator("{\"consent_active\": false, \"subject_ids\": []}").apply(policy, context()));
    }

    @Test
    void scopeFilteringPreservesTheTargetItReads() {
        // `ScopeFilter.applyScope` rebuilds the policy and copies `.target(...)`.
        // Pinned because the validator is useless if a filtered policy loses it,
        // and that would show up as "everything denied" in a live stack only.
        Policy filtered = gatedPolicy(DATASET);
        assertEquals(DATASET, filtered.getTarget());
        assertEquals(DATASET, Policy.Builder.newInstance()
            .permissions(filtered.getPermissions())
            .target(filtered.getTarget())
            .build()
            .getTarget());
    }

    @Test
    void purposesAreReadFromTheGatedPermission() {
        assertEquals(List.of("FlexibilityResearch"),
            Purposes.of(ConsentConstraints.gatedPermission(gatedPolicy(DATASET))));
    }
}
