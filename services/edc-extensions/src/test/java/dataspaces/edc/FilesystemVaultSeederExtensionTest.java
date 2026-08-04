package dataspaces.edc;

import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.result.Result;
import org.eclipse.edc.spi.security.Vault;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The vault seeder, and the setting key it stopped squatting on.
 *
 * <p>The seeder used to read {@code edc.vault.fs.file} — the key EDC's own
 * {@code vault-filesystem} module reads. Nothing collides on this runtime today
 * because that module is not packaged, which is exactly what makes the problem
 * worth a test: the collision is latent, and if it ever arrives it is silent,
 * with extension load order deciding which seed wins.
 *
 * <p>The other half is the empty-vault path. The only {@link Vault} on the
 * classpath is EDC's in-memory default, so a seeder that returns quietly leaves
 * every alias unresolvable — the EDR signing key and the STS client secret
 * included — and the connector reports missing secrets rather than a missing
 * file.
 */
class FilesystemVaultSeederExtensionTest {

    @Test
    void theSeedFileIsReadFromTheDsNamespacedKey(@TempDir Path dir) throws Exception {
        Path seed = write(dir, "participant-private-key=abc\nsts-client-secret=def\n");
        var vault = new RecordingVault();

        seed(vault, Map.of(FilesystemVaultSeederExtension.SEED_FILE, seed.toString()));

        assertEquals(Map.of("participant-private-key", "abc", "sts-client-secret", "def"), vault.stored);
    }

    @Test
    void theLegacyEdcKeyStillWorksAndSaysItIsDeprecated(@TempDir Path dir) throws Exception {
        // Dropping it outright would start the connector with an empty vault on
        // any deployment not yet updated — the silent failure this rename exists
        // to prevent, caused by the fix for it.
        Path seed = write(dir, "participant-private-key=abc\n");
        var vault = new RecordingVault();

        var monitor = seed(vault, Map.of(FilesystemVaultSeederExtension.LEGACY_SEED_FILE, seed.toString()));

        assertEquals(Map.of("participant-private-key", "abc"), vault.stored);
        assertTrue(
            monitor.warnings.stream().anyMatch(w -> w.contains(FilesystemVaultSeederExtension.SEED_FILE)),
            "the deprecation warning must name the key to move to, got: " + monitor.warnings);
    }

    @Test
    void theDsKeyWinsWhenBothAreSet(@TempDir Path dir) throws Exception {
        Path current = write(dir.resolve("a"), "k=current\n");
        Path legacy = write(dir.resolve("b"), "k=legacy\n");
        var vault = new RecordingVault();

        seed(vault, Map.of(
            FilesystemVaultSeederExtension.SEED_FILE, current.toString(),
            FilesystemVaultSeederExtension.LEGACY_SEED_FILE, legacy.toString()));

        assertEquals(Map.of("k", "current"), vault.stored);
    }

    @Test
    void anUnseededVaultWarnsInsteadOfReturningSilently() throws Exception {
        var vault = new RecordingVault();

        var monitor = seed(vault, Map.of());

        assertTrue(vault.stored.isEmpty());
        assertTrue(
            monitor.warnings.stream().anyMatch(w -> w.contains("in-memory")),
            "an empty vault means every alias fails to resolve — say so, got: " + monitor.warnings);
    }

    // ── harness ─────────────────────────────────────────────────────────────

    private static Path write(Path dir, String contents) throws IOException {
        Files.createDirectories(dir);
        Path file = dir.resolve("vault.properties");
        Files.writeString(file, contents);
        return file;
    }

    private static RecordingMonitor seed(Vault vault, Map<String, String> settings) throws Exception {
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

    /**
     * The two methods the extension touches. Implementing
     * {@link ServiceExtensionContext} in full is not worth it, and a mocking
     * framework is not on the test classpath by choice.
     */
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
        public org.eclipse.edc.spi.system.configuration.Config getConfig(String path) {
            return org.eclipse.edc.spi.system.configuration.ConfigFactory.fromMap(settings);
        }

        @Override
        public void initialize() {
        }
    }
}
