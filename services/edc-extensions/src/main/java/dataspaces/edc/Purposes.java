package dataspaces.edc;

import jakarta.json.JsonObject;
import jakarta.json.JsonString;
import jakarta.json.JsonValue;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.Constraint;
import org.eclipse.edc.policy.model.Expression;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Permission;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Reads the {@code odrl:purpose} constraint off a permission.
 *
 * <p>EDC evaluates each atomic constraint separately but hands every function
 * the whole rule, so a consent function can read the purpose the provider
 * offers this dataset for without threading state between two independent
 * constraint functions.
 *
 * <h2>Why the value needs unwrapping</h2>
 *
 * <p>The connector sends the right operand as plain strings, but a policy that
 * has been through EDC's JSON-LD expansion comes back wrapped: a multi-purpose
 * {@code odrl:isAnyOf} arrives as a <em>list of {@code {"@value": …}} objects</em>,
 * not a list of strings. Calling {@code toString()} on those yields
 * {@code {@value={chars=https://…, string=https://…, valueType=STRING}}}, which
 * the connector rightly rejects as an unknown purpose (422).
 *
 * <p>That failure mode is worth remembering: it was invisible for as long as the
 * only caller was the negotiation-scope check, which short-circuits before
 * reading purposes whenever {@code ds.dataset_id} is absent from the participant
 * attributes — which is always. The policy-monitor binding is the first code
 * path that actually uses this, and it surfaced immediately as terminated
 * transfers.
 *
 * <p>Both the compact form and the form ODRL's context expands it to are
 * matched, since whether the context was applied depends on how the policy
 * reached the store.
 */
public final class Purposes {

    static final String COMPACT = "odrl:purpose";
    static final String EXPANDED = "http://www.w3.org/ns/odrl/2/purpose";

    private static final List<String> OPERANDS = List.of(COMPACT, EXPANDED);

    /**
     * Keys a wrapped literal can hide behind, most specific first.
     *
     * <p>{@code @value} and {@code @id} are the JSON-LD wrappers. {@code string}
     * and {@code chars} are the two bean properties of a
     * {@code jakarta.json.JsonString}: when a policy is serialised by Jackson
     * and read back, that object arrives as a plain
     * {@code Map{chars=…, string=…, valueType=STRING}} rather than as a
     * {@code JsonString}, so the IRI is one level deeper than the JSON-LD shape
     * suggests. A multi-purpose operand nests both:
     * {@code [ {@value={chars=…, string=…, valueType=STRING}}, … ]}.
     */
    private static final List<String> VALUE_KEYS = List.of("@value", "@id", "string", "chars");

    private Purposes() {
    }

    /**
     * The purposes declared on {@code rule}, or an empty list when it carries no
     * purpose constraint — an open dataset has no data subject, so there is
     * nothing to scope.
     *
     * <p>An empty result is <em>not</em> the same as "any purpose": the
     * connector denies a consent-required dataset when no purpose is declared.
     */
    public static List<String> of(Permission rule) {
        List<String> purposes = new ArrayList<>();
        if (rule == null || rule.getConstraints() == null) {
            return purposes;
        }
        for (Constraint constraint : rule.getConstraints()) {
            if (!(constraint instanceof AtomicConstraint atomic)) {
                continue;
            }
            if (!OPERANDS.contains(literal(atomic.getLeftExpression()))) {
                continue;
            }
            collect(atomic.getRightExpression(), purposes);
        }
        return purposes;
    }

    private static void collect(Expression expression, List<String> into) {
        if (expression instanceof LiteralExpression literal) {
            unwrap(literal.getValue(), into, 0);
        }
    }

    /**
     * Flatten whatever the policy store handed back into purpose strings.
     *
     * <p>{@code depth} bounds the recursion: the shapes below are all shallow,
     * and a cyclic or pathological value must not take the policy engine down
     * with a stack overflow.
     */
    private static void unwrap(Object value, List<String> into, int depth) {
        if (value == null || depth > 4) {
            return;
        }
        if (value instanceof JsonString jsonString) {
            add(jsonString.getString(), into);
            return;
        }
        if (value instanceof JsonObject jsonObject) {
            for (String key : VALUE_KEYS) {
                JsonValue nested = jsonObject.get(key);
                if (nested != null) {
                    unwrap(nested, into, depth + 1);
                    return;
                }
            }
            return;
        }
        if (value instanceof Map<?, ?> map) {
            for (String key : VALUE_KEYS) {
                Object nested = map.get(key);
                if (nested != null) {
                    unwrap(nested, into, depth + 1);
                    return;
                }
            }
            return;
        }
        if (value instanceof Iterable<?> items) {
            for (Object item : items) {
                unwrap(item, into, depth + 1);
            }
            return;
        }
        add(value.toString(), into);
    }

    /**
     * Accept a purpose only if it still looks like one.
     *
     * <p>A value that survived unwrapping as an object dump — anything carrying
     * {@code =} or a brace — is dropped rather than forwarded. Sending it on
     * would make the connector answer 422, and a 422 on this path terminates a
     * running transfer; an empty purpose list produces a clean, explicable
     * denial instead of a corrupt question.
     */
    private static void add(String text, List<String> into) {
        if (text == null) {
            return;
        }
        String trimmed = text.trim();
        if (trimmed.isEmpty() || trimmed.contains("=") || trimmed.contains("{") || trimmed.contains("}")) {
            return;
        }
        if (!into.contains(trimmed)) {
            into.add(trimmed);
        }
    }

    /**
     * The raw purpose operands, with their Java types, for diagnostics.
     *
     * <p>A consent-gated offer that yields no readable purpose is a silent
     * failure — the connector treats "no purpose declared" as a denial, so the
     * symptom is a refused or parked negotiation with nothing explaining it.
     * This is what the callers log in that case, and it is deliberately about
     * the <em>shape</em>, because the shape is what varies: the same policy
     * arrives as plain strings, as {@code @value} objects or as
     * {@code jakarta.json} values depending on how it reached the store.
     */
    public static String describe(Permission rule) {
        if (rule == null || rule.getConstraints() == null) {
            return "<no constraints>";
        }
        StringBuilder out = new StringBuilder();
        for (Constraint constraint : rule.getConstraints()) {
            if (!(constraint instanceof AtomicConstraint atomic)) {
                continue;
            }
            if (!OPERANDS.contains(literal(atomic.getLeftExpression()))) {
                continue;
            }
            Object value = atomic.getRightExpression() instanceof LiteralExpression literal
                ? literal.getValue() : atomic.getRightExpression();
            out.append(value == null ? "null" : value.getClass().getName())
               .append(" = ").append(value).append("; ");
        }
        return out.isEmpty() ? "<no purpose constraint>" : out.toString();
    }

    private static String literal(Expression expression) {
        if (expression instanceof LiteralExpression literal && literal.getValue() != null) {
            return literal.getValue().toString();
        }
        return "";
    }
}
