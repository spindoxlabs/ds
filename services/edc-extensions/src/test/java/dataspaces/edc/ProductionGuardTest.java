package dataspaces.edc;

import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.result.Result;
import org.eclipse.edc.spi.security.Vault;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * G5 — the EDC's own production guard.
 *
 * <p>The Python services refuse to start on a dev default under any {@code DS_ENV}
 * but {@code dev}; the EDC refused only an <i>empty</i> internal client secret.
 * So it booted on {@code svc-edc} as its own secret, on the STS secret
 * {@code insecure-dev-secret}, and on an EDR signing key copied from the
 * committed fixtures — whose private half anyone with this repository holds.
 * These tests pair each refusal with the configuration that must pass, and
 * check that no value is ever printed.
 */
class ProductionGuardTest {

    /** The committed dev vault fixtures, from this module's directory. */
    private static final Path FIXTURES = Path.of("../connector/config");

    private static final String FRESH_JWK =
        "{\"kty\":\"EC\",\"crv\":\"P-256\",\"x\":\"f83OJ3D2xF1Bg8vub9tLe1gHMzV76e8Tus9uPHvRVEU\","
            + "\"y\":\"x_FEzRu9m36HLN_tue659LNpXW6pCyStikYjKIWI5a0\",\"d\":\"jpsQnnGQmL-YBIffH1136cspYG6-0iY7X1fCE9-E9LI\"}";

    // ── DS_ENV: only `dev` relaxes, as in ds_auth ────────────────────────────

    @ParameterizedTest
    @ValueSource(strings = {"", "production", "prod", "staging", " Production "})
    void everyValueButDevIsProduction(String value) {
        assertTrue(ProductionGuard.isProduction(value));
    }

    @Test
    void unsetIsProduction() {
        assertTrue(ProductionGuard.isProduction(null));
    }

    @ParameterizedTest
    @ValueSource(strings = {"dev", " DEV ", "Dev"})
    void onlyDevRelaxes(String value) {
        assertFalse(ProductionGuard.isProduction(value));
    }

    // ── the internal client ──────────────────────────────────────────────────

    @Test
    void aClientSecretEqualToItsClientIdIsRefused() {
        var guard = new ProductionGuard("edc", "production");
        guard.checkClientSecret("DS_CONNECTOR_INTERNAL_CLIENT_SECRET", "svc-edc", "svc-edc");
        assertEquals(1, guard.violations().size());
        assertTrue(guard.violations().get(0).contains("DS_CONNECTOR_INTERNAL_CLIENT_SECRET"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"CHANGE_ME", "changeme", "Change-Me", "password", "secret"})
    void aPlaceholderClientSecretIsRefused(String secret) {
        var guard = new ProductionGuard("edc", "production");
        guard.checkClientSecret("DS_CONNECTOR_INTERNAL_CLIENT_SECRET", "svc-edc", secret);
        assertEquals(1, guard.violations().size());
    }

    @Test
    void aRealClientSecretPasses() {
        var guard = new ProductionGuard("edc", "production");
        guard.checkClientSecret("DS_CONNECTOR_INTERNAL_CLIENT_SECRET", "svc-edc", "b3b1f0c2e4d5a7c9");
        assertEquals(List.of(), guard.violations());
    }

    // ── the vault seed ───────────────────────────────────────────────────────

    @ParameterizedTest
    @ValueSource(strings = {"insecure-dev-secret", "insecure-dev-callback-key", "CHANGE_ME"})
    void aDevOrPlaceholderVaultValueIsRefusedByAlias(String value) {
        var guard = new ProductionGuard("edc", "production");
        guard.checkVaultSeed("sts-client-secret", value);
        assertEquals(1, guard.violations().size());
        assertTrue(guard.violations().get(0).contains("sts-client-secret"));
        assertFalse(guard.violations().get(0).contains(value), "the value must never be printed");
    }

    @Test
    void everyCommittedFixtureSigningKeyIsRefused() throws IOException {
        for (String jwk : fixtureJwks()) {
            var guard = new ProductionGuard("edc", "production");
            guard.checkVaultSeed("participant-private-key", jwk);
            assertEquals(1, guard.violations().size(), "a fixture key passed");
            assertTrue(guard.violations().get(0).contains("participant-private-key"));
        }
    }

    @Test
    void aFreshSigningKeyPasses() {
        var guard = new ProductionGuard("edc", "production");
        guard.checkVaultSeed("participant-private-key", FRESH_JWK);
        guard.checkVaultSeed("sts-client-secret", "9c1e0f6a2b7d4e83");
        assertEquals(List.of(), guard.violations());
    }

    @Test
    void theFingerprintListIsTheFixturesPublicCoordinates() throws IOException {
        // Read out of the fixtures rather than trusted: a rotated fixture must
        // not leave the guard checking a key nobody uses any more.
        Set<String> fromFixtures = new TreeSet<>();
        var x = Pattern.compile("\"x\":\"([^\"]+)\"");
        for (String jwk : fixtureJwks()) {
            var m = x.matcher(jwk);
            assertTrue(m.find(), "fixture JWK without x");
            fromFixtures.add(m.group(1));
        }
        assertFalse(fromFixtures.isEmpty(), "no fixture keys found — this test checks nothing");
        assertEquals(fromFixtures, new TreeSet<>(ProductionGuard.DEV_EDR_KEY_X));
    }

    // ── enforcement ──────────────────────────────────────────────────────────

    @Test
    void productionRefusesWithEveryViolationAtOnce() {
        var guard = new ProductionGuard("edc", "production");
        guard.checkClientSecret("A_SECRET", "svc-edc", "svc-edc");
        guard.checkVaultSeed("sts-client-secret", "insecure-dev-secret");
        var error = assertThrows(EdcException.class, () -> guard.enforce(new RecordingMonitor()));
        assertTrue(error.getMessage().contains("A_SECRET"), error.getMessage());
        assertTrue(error.getMessage().contains("sts-client-secret"), error.getMessage());
    }

    @Test
    void devOnlyWarns() {
        var guard = new ProductionGuard("edc", "dev");
        guard.checkVaultSeed("sts-client-secret", "insecure-dev-secret");
        var monitor = new RecordingMonitor();
        guard.enforce(monitor);
        assertEquals(1, monitor.warnings.size());
    }

    // ── wired in: the seeder and the internal client ─────────────────────────

    @Test
    void theSeederRefusesAFixtureKeyUnderProduction(@TempDir Path dir) throws Exception {
        Path seed = dir.resolve("vault.properties");
        Files.writeString(seed, "participant-private-key=" + fixtureJwks().get(0) + "\nsts-client-secret=9c1e0f6a2b7d4e83\n");
        var vault = new RecordingVault();
        var settings = Map.of(FilesystemVaultSeederExtension.SEED_FILE, seed.toString(), ProductionGuard.DS_ENV, "production");

        var error = assertThrows(EdcException.class, () -> seedWith(vault, settings));
        assertTrue(error.getMessage().contains("participant-private-key"), error.getMessage());
        assertTrue(vault.stored.isEmpty(), "nothing is seeded from a refused file");
    }

    @Test
    void theSeederOnlyWarnsUnderDev(@TempDir Path dir) throws Exception {
        Path seed = dir.resolve("vault.properties");
        Files.writeString(seed, "sts-client-secret=insecure-dev-secret\n");
        var vault = new RecordingVault();

        var monitor = seedWith(vault, Map.of(FilesystemVaultSeederExtension.SEED_FILE, seed.toString(), ProductionGuard.DS_ENV, "dev"));
        assertEquals(Map.of("sts-client-secret", "insecure-dev-secret"), vault.stored);
        assertTrue(monitor.warnings.stream().anyMatch(w -> w.contains("sts-client-secret")), monitor.warnings.toString());
    }

    @Test
    void theInternalClientGuardRefusesTheDevSecretAndControlKey() {
        var settings = new HashMap<String, String>();
        settings.put(ProductionGuard.DS_ENV, "production");
        settings.put("ds.connector.internal.client.id", "svc-edc");
        settings.put("ds.connector.internal.client.secret", "svc-edc");
        settings.put("web.http.control.auth.key", "insecure-dev-control-key");
        var error = assertThrows(EdcException.class,
            () -> DataspacesExtension.guardInternalCredentials(new StubContext(settings, new RecordingMonitor())));
        assertTrue(error.getMessage().contains("DS_CONNECTOR_INTERNAL_CLIENT_SECRET"), error.getMessage());
        assertTrue(error.getMessage().contains("WEB_HTTP_CONTROL_AUTH_KEY"), error.getMessage());
        assertFalse(error.getMessage().contains("insecure-dev-control-key"), "the value must never be printed");
    }

    @Test
    void theInternalClientGuardPassesRealValues() {
        var settings = Map.of(
            ProductionGuard.DS_ENV, "production",
            "ds.connector.internal.client.id", "svc-edc",
            "ds.connector.internal.client.secret", "b3b1f0c2e4d5a7c9",
            "web.http.control.auth.key", "1f0e2d3c4b5a6978");
        DataspacesExtension.guardInternalCredentials(new StubContext(settings, new RecordingMonitor()));
    }

    // ── harness ──────────────────────────────────────────────────────────────

    private static List<String> fixtureJwks() throws IOException {
        List<String> keys = new ArrayList<>();
        try (Stream<Path> files = Files.list(FIXTURES)) {
            for (Path file : files.filter(p -> p.getFileName().toString().endsWith("-vault.properties")).sorted().toList()) {
                for (String line : Files.readAllLines(file)) {
                    int eq = line.indexOf('=');
                    if (!line.startsWith("#") && eq > 0 && line.substring(eq + 1).trim().startsWith("{")) {
                        keys.add(line.substring(eq + 1).trim());
                    }
                }
            }
        }
        assertFalse(keys.isEmpty(), "no fixture keys under " + FIXTURES.toAbsolutePath());
        return keys;
    }

    private static RecordingMonitor seedWith(Vault vault, Map<String, String> settings) throws Exception {
        var extension = new FilesystemVaultSeederExtension();
        Field field = FilesystemVaultSeederExtension.class.getDeclaredField("vault");
        field.setAccessible(true);
        field.set(extension, vault);
        var monitor = new RecordingMonitor();
        extension.initialize(new StubContext(settings, monitor));
        return monitor;
    }

    private static class RecordingVault implements Vault {
        private final Map<String, String> stored = new LinkedHashMap<>();

        @Override
        public String resolveSecret(String key) {
            return stored.get(key);
        }

        @Override
        public Result<Void> storeSecret(String key, String value) {
            stored.put(key, value);
            return Result.success();
        }

        @Override
        public Result<Void> deleteSecret(String key) {
            stored.remove(key);
            return Result.success();
        }
    }

    private static class RecordingMonitor implements Monitor {
        private final List<String> warnings = new ArrayList<>();

        @Override
        public void warning(String message, Throwable... errors) {
            warnings.add(message);
        }
    }

    private static class StubContext implements ServiceExtensionContext {
        private final Map<String, String> settings;
        private final Monitor monitor;

        StubContext(Map<String, String> settings, Monitor monitor) {
            this.settings = settings;
            this.monitor = monitor;
        }

        @Override
        public String getSetting(String key, String defaultValue) {
            return settings.getOrDefault(key, defaultValue);
        }

        @Override
        public Monitor getMonitor() {
            return monitor;
        }

        @Override
        public String getRuntimeId() {
            return "test";
        }

        @Override
        public String getComponentId() {
            return "test";
        }

        @Override
        public <T> T getService(Class<T> type) {
            return null;
        }

        @Override
        public <T> boolean hasService(Class<T> type) {
            return false;
        }

        @Override
        public org.eclipse.edc.spi.system.configuration.Config getConfig() {
            return org.eclipse.edc.spi.system.configuration.ConfigFactory.fromMap(settings);
        }

        @Override
        public void initialize() {
        }
    }
}
