package dataspaces.edc;

import jakarta.json.Json;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.Constraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.OrConstraint;
import org.eclipse.edc.policy.model.Permission;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The purposes a permission declares must be readable in every shape a policy can
 * arrive in. Reading none is not a harmless miss: the connector treats "no purpose
 * declared" as a denial, and on the {@code policy.monitor} scope that terminates a
 * transfer that is already running.
 */
class PurposesTest {

    private static final String A = "https://w3id.org/dsp/policy/purpose/EnergyCommunityOperation";
    private static final String B = "https://w3id.org/dsp/policy/purpose/IncentiveCalculation";

    private static Permission permissionWith(Constraint... constraints) {
        return Permission.Builder.newInstance().constraints(List.of(constraints)).build();
    }

    private static AtomicConstraint purpose(Operator operator, Object rightValue) {
        return AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression(Purposes.COMPACT))
                .operator(operator)
                .rightExpression(new LiteralExpression(rightValue))
                .build();
    }

    // ── the shape the mapper emits now ───────────────────────────────────────

    @Test
    @DisplayName("or of single-valued isA — the shape that survives EDC serialisation")
    void readsOrOfIsA() {
        var or = OrConstraint.Builder.newInstance()
                .constraints(List.of(purpose(Operator.IS_A, A), purpose(Operator.IS_A, B)))
                .build();

        assertEquals(List.of(A, B), Purposes.of(permissionWith(or)));
    }

    @Test
    @DisplayName("a single purpose still needs no wrapping")
    void readsBareIsA() {
        assertEquals(List.of(A), Purposes.of(permissionWith(purpose(Operator.IS_A, A))));
    }

    // ── the shape frozen into pre-change agreements ──────────────────────────
    //
    // A ContractAgreement stores its own policy, and AgreementConsentFunction
    // evaluates that frozen copy for the life of the transfer. So these shapes
    // outlive the mapper change and must keep working.

    @Test
    @DisplayName("isAnyOf as a plain list — the connector's own wire form")
    void readsIsAnyOfPlainList() {
        assertEquals(List.of(A, B), Purposes.of(permissionWith(purpose(Operator.IS_ANY_OF, List.of(A, B)))));
    }

    @Test
    @DisplayName("isAnyOf after JSON-LD expansion — a JsonArray of @value objects")
    void readsIsAnyOfExpanded() {
        var array = Json.createArrayBuilder()
                .add(Json.createObjectBuilder().add("@value", A))
                .add(Json.createObjectBuilder().add("@value", B))
                .build();

        assertEquals(List.of(A, B), Purposes.of(permissionWith(purpose(Operator.IS_ANY_OF, array))));
    }

    @Test
    @DisplayName("isAnyOf after a Jackson round trip — JsonString arrives as a bare Map")
    void readsIsAnyOfJacksonRoundTrip() {
        // What the SQL store hands back: the JsonString became its bean properties.
        var value = List.of(
                Map.of("@value", Map.of("valueType", "STRING", "chars", A, "string", A)),
                Map.of("@value", Map.of("valueType", "STRING", "chars", B, "string", B)));

        assertEquals(List.of(A, B), Purposes.of(permissionWith(purpose(Operator.IS_ANY_OF, value))));
    }

    // ── refusals ─────────────────────────────────────────────────────────────

    @Test
    @DisplayName("a constraint on another operand contributes nothing")
    void ignoresOtherOperands() {
        var other = AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression("ds:contractRequired"))
                .operator(Operator.EQ)
                .rightExpression(new LiteralExpression("true"))
                .build();

        assertTrue(Purposes.of(permissionWith(other)).isEmpty());
    }

    @Test
    @DisplayName("an object dump is dropped rather than forwarded as a purpose")
    void dropsUnreadableValues() {
        // Forwarding this would make the connector answer 422, and a 422 on the
        // monitor path terminates a live transfer. An empty list denies cleanly.
        var mangled = "[{@value={valueType=STRING, chars=" + A + ", string=" + A + "}}]";

        assertTrue(Purposes.of(permissionWith(purpose(Operator.IS_ANY_OF, mangled))).isEmpty());
    }

    @Test
    @DisplayName("no purpose constraint at all yields an empty list, not an error")
    void handlesAbsentConstraint() {
        assertTrue(Purposes.of(permissionWith()).isEmpty());
        assertTrue(Purposes.of(null).isEmpty());
    }

    @Test
    @DisplayName("duplicates across nested constraints collapse")
    void deduplicates() {
        var or = OrConstraint.Builder.newInstance()
                .constraints(List.of(purpose(Operator.IS_A, A), purpose(Operator.IS_A, A)))
                .build();

        assertEquals(List.of(A), Purposes.of(permissionWith(or)));
    }
}
