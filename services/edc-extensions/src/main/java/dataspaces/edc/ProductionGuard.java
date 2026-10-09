package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * The EDC's counterpart of {@code ds_auth.production.ProductionGuard}.
 *
 * <p>The Python services refuse to start on a dev default unless
 * {@code DS_ENV=dev}; the EDC refused only an <i>empty</i> internal client
 * secret. So a chart deployment booted on {@code svc-edc} as its own secret, on
 * the STS secret {@code insecure-dev-secret} and on an EDR signing key pasted
 * from {@code services/connector/config/*-vault.properties} — committed dev
 * fixtures whose private halves anyone with this repository holds, so every EDR
 * that EDC signs would be forgeable.
 *
 * <p>Same rules as the Python guard: <b>only {@code DS_ENV=dev} relaxes</b>
 * (unset, empty or any other value is production); every violation is collected
 * and reported at once; in dev each is a warning. <b>No value is ever
 * printed</b> — a violation names the setting or the vault alias. {@code DS_ENV}
 * reaches EDC as {@code ds.env} through its ENVIRONMENT_NOTATION mapping, which
 * the charts set to {@code production} on every container.
 */
final class ProductionGuard {

    /** {@code DS_ENV}, as EDC's environment mapping names it. */
    static final String DS_ENV = "ds.env";

    private static final String DEV = "dev";

    /**
     * The same list as {@code ds_auth.production.UNIVERSAL_WEAK_VALUES},
     * compared in {@link #weakForm}.
     */
    private static final Set<String> WEAK = Set.of(
        "", "admin", "changeme", "password", "postgres", "secret", "test");

    /** Dev literals the compose stacks and the vault fixtures ship. */
    private static final Set<String> DEV_LITERALS = Set.of(
        "insecure-dev-secret", "insecure-dev-callback-key", "insecure-dev-control-key", "insecure-dev-key");

    /**
     * The public {@code x} coordinate of every committed dev EDR signing key. A
     * public coordinate identifies the key without being secret, so it can sit
     * here; a test reads the fixtures and fails when this list stops matching
     * them.
     */
    static final Set<String> DEV_EDR_KEY_X = Set.of(
        "aG5tWWbDs57eXTu9DSBFUepQnw7XV8xuwjOQW5z3WK8",
        "K-yAEzC24eWqvsZ8fgNIhOszsM0pRNcKwr8AkEp8x5M",
        "VRSMmFb0n5vlOQsElSmUsdbRfS-7d3_lV2UfFKcsYfA");

    private static final ObjectMapper JSON = new ObjectMapper();

    private final String component;
    private final boolean production;
    private final List<String> violations = new ArrayList<>();

    ProductionGuard(String component, String dsEnv) {
        this.component = component;
        this.production = isProduction(dsEnv);
    }

    /** True unless {@code dsEnv} is exactly {@code dev} after trim and lowercase. */
    static boolean isProduction(String dsEnv) {
        return !DEV.equals(dsEnv == null ? "" : dsEnv.trim().toLowerCase(Locale.ROOT));
    }

    /** Case, surrounding space, {@code _} and {@code -} ignored, as {@code ds_auth.production.weak_form}. */
    static String weakForm(String value) {
        return value.trim().toLowerCase(Locale.ROOT).replace("_", "").replace("-", "");
    }

    static boolean isWeak(String value) {
        return value != null && WEAK.contains(weakForm(value));
    }

    List<String> violations() {
        return List.copyOf(violations);
    }

    private void add(String what, String reason) {
        violations.add(what + ": " + reason);
    }

    /** A client secret that is its client id, a placeholder or a weak word. */
    void checkClientSecret(String setting, String clientId, String secret) {
        if (secret == null || secret.isBlank()) {
            return; // absence is refused where the value is read
        }
        if (clientId != null && secret.trim().equals(clientId.trim())) {
            add(setting, "is still equal to its client id — the dev default");
        } else {
            checkSecret(setting, secret);
        }
    }

    /** A secret that is a known dev literal, a placeholder or a weak word. */
    void checkSecret(String setting, String value) {
        if (value == null || value.isBlank()) {
            return;
        }
        if (DEV_LITERALS.contains(value.trim())) {
            add(setting, "is a committed dev default");
        } else if (isWeak(value)) {
            add(setting, "is a placeholder or trivially weak value");
        }
    }

    /**
     * One vault seed entry: a dev literal or placeholder, or a JWK whose public
     * coordinate is a committed fixture's.
     */
    void checkVaultSeed(String alias, String value) {
        if (value == null) {
            return;
        }
        String text = value.trim();
        if (text.startsWith("{")) {
            JsonNode jwk;
            try {
                jwk = JSON.readTree(text);
            } catch (Exception e) {
                return; // not a JWK; EDC reports an unparseable key where it uses it
            }
            JsonNode x = jwk.get("x");
            if (x != null && DEV_EDR_KEY_X.contains(x.asText())) {
                add("vault alias " + alias, "is a committed dev fixture key — its private half is public");
            } else if (jwk.has("d") && isWeak(jwk.get("d").asText())) {
                add("vault alias " + alias, "carries a placeholder private key");
            }
            return;
        }
        checkSecret("vault alias " + alias, text);
    }

    /** Throw with every violation under production; warn under {@code DS_ENV=dev}. */
    void enforce(Monitor monitor) {
        if (violations.isEmpty()) {
            return;
        }
        String detail = String.join("\n  - ", violations);
        if (production) {
            throw new EdcException(
                "%s: refusing to start — %d insecure default(s) with DS_ENV not 'dev' (only DS_ENV=dev relaxes this guard):\n  - %s"
                    .formatted(component, violations.size(), detail));
        }
        monitor.warning("%s: %d insecure development default(s) in use (acceptable only because DS_ENV=dev):\n  - %s"
            .formatted(component, violations.size(), detail));
    }
}
