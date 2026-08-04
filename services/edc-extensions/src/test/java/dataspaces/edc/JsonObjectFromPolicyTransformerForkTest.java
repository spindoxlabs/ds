package dataspaces.edc;

import jakarta.json.Json;
import jakarta.json.JsonArray;
import jakarta.json.JsonObject;
import jakarta.json.JsonValue;
import org.eclipse.edc.connector.controlplane.transform.odrl.from.JsonObjectFromPolicyTransformer;
import org.eclipse.edc.participant.spi.ParticipantIdMapper;
import org.eclipse.edc.policy.model.Action;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.policy.model.Policy;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the forked {@code JsonObjectFromPolicyTransformer}.
 *
 * <p>We carry a patched copy of an EDC class under its own package so it replaces
 * upstream's on the shadow JAR classpath. That is only safe while it is a copy of
 * the version we actually run against: bump the EDC dependency and the fork
 * silently reverts every *other* change upstream made to that class, while looking
 * perfectly healthy.
 *
 * <p>So this fails the moment the pinned version moves, forcing a human to re-fork
 * or — better — to delete the fork because the fix landed upstream.
 */
class JsonObjectFromPolicyTransformerForkTest {

    /** The EDC release the fork was taken from. */
    private static final String FORKED_FROM = "0.16.0";

    private static final String UPSTREAM_COPY = "/JsonObjectFromPolicyTransformer.v0.16.0.java.txt";

    @Test
    @DisplayName("the fork still matches the EDC version we build against")
    void forkMatchesPinnedEdcVersion() {
        var running = System.getProperty("edc.version");
        assertNotNull(running, "edc.version system property is not set — see build.gradle.kts");
        assertEquals(
                FORKED_FROM,
                running,
                """
                The EDC dependency moved to %s but the forked JsonObjectFromPolicyTransformer \
                was taken from %s.

                Check whether the multi-valued right-operand fix has landed upstream \
                (JsonObjectFromPolicyTransformer.visitAtomicConstraint). If it has, DELETE the \
                fork, the duplicatesStrategy block and the verifyForkedTransformer task. If it \
                has not, re-fork from the new version and update FORKED_FROM.""".formatted(running, FORKED_FROM));
    }

    @Test
    @DisplayName("the pristine upstream copy still carries the defect this fork exists for")
    void upstreamStillHasTheDefect() throws IOException {
        var upstream = readResource(UPSTREAM_COPY);

        // The defect: the right operand routed through a JsonObject-typed visitor,
        // which forces toString() on a multi-valued literal.
        assertTrue(
                upstream.contains("atomicConstraint.getRightExpression().accept(this)"),
                "the pristine upstream copy no longer contains the defect — re-check the fork");
        assertFalse(
                upstream.contains(JsonObjectFromPolicyTransformer.FORK_MARKER),
                "the pristine copy must be upstream's, not our patched version");
    }

    // ── what the fork actually does ──────────────────────────────────────────
    //
    // The two assertions above are both about a *file*. Neither runs the class,
    // so a fork that compiled but no longer fixed anything passed them both —
    // which is the failure this whole arrangement exists to prevent, since a
    // silent revert republishes unreadable policies while every suite stays
    // green. These three drive the transformer.

    @Test
    @DisplayName("a multi-valued right operand publishes as a JSON-LD array, not a toString dump")
    void multiValuedOperandPublishesAsAnArray() {
        var rightOperand = rightOperandOf(transform(policyWithPurposes(List.of(
                Map.of("@id", "https://w3id.org/dsp/policy/purpose/FlexibilityResearch"),
                Map.of("@id", "https://w3id.org/dsp/policy/purpose/IncentiveCalculation")))));

        assertEquals(JsonValue.ValueType.ARRAY, rightOperand.getValueType(),
                "a multi-valued operand must stay an array — upstream collapses it with toString()");
        var values = rightOperand.asJsonArray().stream()
                .map(v -> v.asJsonObject().getString("@id"))
                .toList();
        assertEquals(
                List.of("https://w3id.org/dsp/policy/purpose/FlexibilityResearch",
                        "https://w3id.org/dsp/policy/purpose/IncentiveCalculation"),
                values);
    }

    @Test
    @DisplayName("no rendered operand carries a Java object dump")
    void nothingIsStringified() {
        // The symptom upstream produces, and the one thing a counterparty sees:
        // "[{@value={valueType=STRING, chars=https://…}}, …]". Asserting on the
        // shape above would still pass if the values themselves were dumps.
        var rendered = transform(policyWithPurposes(List.of(
                Map.of("@id", "https://w3id.org/dsp/policy/purpose/FlexibilityResearch"),
                Map.of("@id", "https://w3id.org/dsp/policy/purpose/GridMonitoring")))).toString();

        assertFalse(rendered.contains("valueType="), "a JsonString bean leaked into the output: " + rendered);
        assertFalse(rendered.contains("chars="), "a JsonString bean leaked into the output: " + rendered);
    }

    @Test
    @DisplayName("a single-valued right operand is unaffected")
    void singleValuedOperandIsUnchanged() {
        // The fork must be a narrowing, not a rewrite: every existing policy has
        // scalar operands and they must render exactly as upstream renders them.
        var rightOperand = rightOperandOf(transform(policyWithPurposes("granted")));

        assertEquals(JsonValue.ValueType.OBJECT, rightOperand.getValueType());
        assertEquals("granted", rightOperand.asJsonObject().getString("@value"));
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    /** Identity mapping — this test is about operands, not participant IRIs. */
    private static final ParticipantIdMapper IDENTITY = new ParticipantIdMapper() {
        @Override
        public String toIri(String participantId) {
            return participantId;
        }

        @Override
        public String fromIri(String iriParticipantId) {
            return iriParticipantId;
        }
    };

    private static JsonObject transform(Policy policy) {
        var transformer = new JsonObjectFromPolicyTransformer(
                Json.createBuilderFactory(Map.of()), IDENTITY);
        // `transform` delegates straight to the visitor and never touches the
        // context; passing one would mean implementing eleven methods to observe
        // nothing.
        var result = transformer.transform(policy, null);
        assertNotNull(result, "the transformer returned nothing");
        return result;
    }

    private static Policy policyWithPurposes(Object rightOperand) {
        return Policy.Builder.newInstance()
                .permission(Permission.Builder.newInstance()
                        .action(Action.Builder.newInstance().type("odrl:use").build())
                        .constraint(AtomicConstraint.Builder.newInstance()
                                .leftExpression(new LiteralExpression("odrl:purpose"))
                                .operator(Operator.IS_ANY_OF)
                                .rightExpression(new LiteralExpression(rightOperand))
                                .build())
                        .build())
                .build();
    }

    /** The single rendered `odrl:rightOperand` of the policy's only constraint. */
    private static JsonValue rightOperandOf(JsonObject policy) {
        JsonArray permissions = policy.getJsonArray("http://www.w3.org/ns/odrl/2/permission");
        assertNotNull(permissions, "no permissions in " + policy);
        JsonArray constraints = permissions.getJsonObject(0)
                .getJsonArray("http://www.w3.org/ns/odrl/2/constraint");
        assertNotNull(constraints, "no constraints in " + permissions);
        return constraints.getJsonObject(0).get("http://www.w3.org/ns/odrl/2/rightOperand");
    }

    private String readResource(String name) throws IOException {
        try (InputStream in = getClass().getResourceAsStream(name)) {
            assertNotNull(in, "missing test resource " + name);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
