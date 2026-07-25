package dataspaces.edc;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

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
    @DisplayName("the fork changes only the right-operand rendering")
    void forkDivergesOnlyWhereIntended() throws IOException {
        var upstream = readResource(UPSTREAM_COPY);

        // The defect: the right operand routed through a JsonObject-typed visitor,
        // which forces toString() on a multi-valued literal.
        assertTrue(
                upstream.contains("atomicConstraint.getRightExpression().accept(this)"),
                "the pristine upstream copy no longer contains the defect — re-check the fork");
        assertFalse(
                upstream.contains("ds-fork-multivalued-right-operand"),
                "the pristine copy must be upstream's, not our patched version");
    }

    private String readResource(String name) throws IOException {
        try (InputStream in = getClass().getResourceAsStream(name)) {
            assertNotNull(in, "missing test resource " + name);
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
