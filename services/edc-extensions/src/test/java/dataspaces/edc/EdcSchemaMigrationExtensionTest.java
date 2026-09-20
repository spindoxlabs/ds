package dataspaces.edc;

import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.sql.bootstrapper.SqlSchemaBootstrapper;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * What the schema-migration extension queues, and on which datasource.
 *
 * <p>Whether the SQL is right is proven against PostgreSQL, from an old schema, by
 * {@code tests/integration/test_schema_migration.py} in this unit. This covers what that
 * suite cannot see: that every file under {@code ds-edc-schema/} is actually queued, and
 * queued on the datasource EDC gives its store. A file nobody queues is a migration that
 * never runs, and every suite would still pass.
 */
class EdcSchemaMigrationExtensionTest {

    private static final Path RESOURCES = Path.of("src/main/resources");

    private static final Pattern FILE_NAME = Pattern.compile("V\\d+_\\d+_\\d+__[a-z0-9_]+\\.sql");

    @Test
    void everyMigrationFileIsQueuedAndEveryQueuedFileExists() throws IOException {
        Path root = RESOURCES.resolve(EdcSchemaMigrationExtension.RESOURCE_ROOT);
        TreeSet<String> onDisk;
        try (Stream<Path> files = Files.walk(root)) {
            onDisk = files.filter(Files::isRegularFile)
                    .map(p -> RESOURCES.relativize(p).toString().replace('\\', '/'))
                    .collect(Collectors.toCollection(TreeSet::new));
        }
        var registered = EdcSchemaMigrationExtension.MIGRATIONS.values().stream()
                .flatMap(List::stream)
                .collect(Collectors.toCollection(TreeSet::new));

        assertFalse(onDisk.isEmpty(), "no migration files found under " + root.toAbsolutePath());
        assertEquals(onDisk, registered,
                "the files under ds-edc-schema/ and EdcSchemaMigrationExtension.MIGRATIONS must agree");
    }

    @Test
    void eachFileSitsUnderItsStoreAndTheStoresAreInVersionOrder() {
        EdcSchemaMigrationExtension.MIGRATIONS.forEach((store, resources) -> {
            var prefix = EdcSchemaMigrationExtension.RESOURCE_ROOT + "/" + store + "/";
            for (var resource : resources) {
                assertTrue(resource.startsWith(prefix), resource + " is not under " + prefix);
                var name = resource.substring(prefix.length());
                assertTrue(FILE_NAME.matcher(name).matches(), name + " is not V<major>_<minor>_<patch>__<what>.sql");
            }
            assertEquals(resources.stream().sorted().toList(), resources,
                    store + ": migrations must be listed oldest first");
        });
    }

    @Test
    void everyStatementIsAGuardedAdditionAndEndsWithASemicolon() throws IOException {
        // The bootstrapper joins a datasource's queued files with "" and runs them as one
        // string, so a file that does not end in `;` breaks the statement after it. And its
        // contract says statements must not depend on the queue order, which only a
        // twice-guarded addition satisfies.
        var guarded = Pattern.compile(
                "ALTER TABLE IF EXISTS \\w+ ADD COLUMN IF NOT EXISTS \\w+ [^;]+;");
        for (var resource : allResources()) {
            var sql = Files.readString(RESOURCES.resolve(resource), StandardCharsets.UTF_8);
            assertTrue(sql.strip().endsWith(";"), resource + " must end with ';'");
            var statements = sql.lines()
                    .filter(l -> !l.isBlank() && !l.stripLeading().startsWith("--"))
                    .toList();
            assertFalse(statements.isEmpty(), resource + " holds no statement");
            for (var statement : statements) {
                assertTrue(guarded.matcher(statement.strip()).matches(),
                        resource + ": not a guarded ADD COLUMN: " + statement);
            }
        }
    }

    @Test
    void eachFileIsQueuedOnTheDatasourceItsStoreIsConfiguredWith() throws Exception {
        var bootstrapper = new RecordingBootstrapper();
        var monitor = new RecordingMonitor();

        initialize(bootstrapper, monitor, Map.of(
                "edc.sql.schema.autocreate", "true",
                "edc.sql.store.transferprocess.datasource", "transfers"));

        for (var resource : EdcSchemaMigrationExtension.MIGRATIONS.get("contractnegotiation")) {
            assertEquals("default", bootstrapper.datasourceOf(resource), resource);
        }
        for (var resource : EdcSchemaMigrationExtension.MIGRATIONS.get("transferprocess")) {
            assertEquals("transfers", bootstrapper.datasourceOf(resource), resource);
        }
        assertEquals(allResources().size(), bootstrapper.queued.size());
        assertTrue(monitor.warnings.isEmpty(), "autocreate on is the normal case: " + monitor.warnings);
    }

    @Test
    void theQueuedResourcesResolveOnTheClassLoaderTheyAreQueuedWith() throws Exception {
        // `addStatementFromResource(ds, name)` without a class loader resolves on the
        // bootstrapper's own loader. In the fat jar that is the same one, but the extension
        // passes its own explicitly, and that loader must find every file.
        var bootstrapper = new RecordingBootstrapper();
        initialize(bootstrapper, new RecordingMonitor(), Map.of("edc.sql.schema.autocreate", "true"));

        for (var entry : bootstrapper.queued) {
            assertNotNull(entry.loader().getResource(entry.resource()), entry.resource() + " is not on the class path");
        }
    }

    @Test
    void withAutocreateOffItWarnsAndNamesTheFiles() throws Exception {
        // Nothing runs then, the store schemas included. The operator owns the DDL, and the
        // store files alone do not upgrade an old database.
        var monitor = new RecordingMonitor();

        initialize(new RecordingBootstrapper(), monitor, Map.of());

        assertEquals(1, monitor.warnings.size(), monitor.warnings.toString());
        for (var resource : allResources()) {
            assertTrue(monitor.warnings.get(0).contains(resource), "the warning must name " + resource);
        }
    }

    // ── harness ─────────────────────────────────────────────────────────────

    private static List<String> allResources() {
        return EdcSchemaMigrationExtension.MIGRATIONS.values().stream().flatMap(List::stream).toList();
    }

    private static void initialize(SqlSchemaBootstrapper bootstrapper, Monitor monitor, Map<String, String> settings)
            throws Exception {
        var extension = new EdcSchemaMigrationExtension();
        Field field = EdcSchemaMigrationExtension.class.getDeclaredField("bootstrapper");
        field.setAccessible(true);
        field.set(extension, bootstrapper);
        extension.initialize(new StubContext(settings, monitor));
    }

    private record Queued(String datasource, String resource, ClassLoader loader) {
    }

    private static class RecordingBootstrapper implements SqlSchemaBootstrapper {
        private final List<Queued> queued = new ArrayList<>();

        @Override
        public void addStatementFromResource(String datasourceName, String resourceName, ClassLoader classLoader) {
            queued.add(new Queued(datasourceName, resourceName, classLoader));
        }

        @Override
        public Map<String, List<String>> getStatements() {
            return Map.of();
        }

        String datasourceOf(String resource) {
            return queued.stream().filter(q -> q.resource().equals(resource)).findFirst()
                    .map(Queued::datasource).orElse(null);
        }
    }

    private static class RecordingMonitor implements Monitor {
        private final List<String> warnings = new ArrayList<>();

        @Override
        public void warning(String message, Throwable... errors) {
            warnings.add(message);
        }
    }

    /** The methods the extension touches; see FilesystemVaultSeederExtensionTest. */
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
