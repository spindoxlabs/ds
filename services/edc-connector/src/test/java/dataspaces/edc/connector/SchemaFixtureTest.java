package dataspaces.edc.connector;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;
import java.util.zip.ZipFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The schema the migration suite tests against is the schema this jar creates.
 *
 * <p>{@code services/edc-extensions/tests/integration} upgrades older EDC schemas and
 * requires the result to equal "the pinned schema": the store schema files committed under
 * {@code edc-schema/v<edcVersion>/}. That is only worth something if those files are the
 * ones {@code connector.jar} runs. This test holds them to it, byte for byte and file for
 * file, so the suite cannot go on passing against a copy of an older EDC's DDL.
 *
 * <p><b>It is also the tripwire for an EDC bump.</b> After {@code edcVersion} moves there
 * is no fixture directory for it, and this fails until one is added. Adding it means
 * reading the DDL diff, and every column it adds needs a migration under
 * {@code ds-edc-schema/}, because autocreate will not add it to an existing table
 * ({@code docs/decisions/ADR-0018}).
 */
@DisplayName("connector.jar creates the schema the migration suite tests against")
class SchemaFixtureTest {

    private static final String FIXTURES = "services/edc-extensions/tests/integration/edc-schema";
    private static final String MIGRATIONS = "services/edc-extensions/src/main/resources/";
    private static final String MIGRATION_ROOT = "ds-edc-schema/";

    private static Path repoRoot;
    private static Path jar;

    @BeforeAll
    static void locate() {
        repoRoot = Path.of(required("ds.repo.root"));
        jar = Path.of(required("ds.connector.jar"));
    }

    @Test
    @DisplayName("the fixtures for the pinned EDC are the jar's store schema files, byte for byte")
    void theFixturesAreTheJarsSchemaFiles() throws IOException {
        Path fixtures = repoRoot.resolve(FIXTURES).resolve("v" + edcVersion());
        assertTrue(Files.isDirectory(fixtures), () -> ("no schema fixtures for the pinned EDC at %s. EDC was bumped: "
                + "copy the new jar's *-schema.sql there, read the diff against the previous version, and add a "
                + "migration under %s for every column it adds.").formatted(fixtures, MIGRATIONS + MIGRATION_ROOT));

        var inJar = new TreeMap<String, String>();
        try (var zip = new ZipFile(jar.toFile())) {
            var entries = zip.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement();
                if (!entry.isDirectory() && !entry.getName().contains("/") && entry.getName().endsWith("-schema.sql")) {
                    try (var in = zip.getInputStream(entry)) {
                        inJar.put(entry.getName(), new String(in.readAllBytes()));
                    }
                }
            }
        }
        var committed = new TreeMap<String, String>();
        try (Stream<Path> files = Files.list(fixtures)) {
            for (var file : files.filter(f -> f.toString().endsWith(".sql")).toList()) {
                committed.put(file.getFileName().toString(), Files.readString(file));
            }
        }

        assertFalse(inJar.isEmpty(), "connector.jar holds no *-schema.sql at its root: has the packaging changed?");
        assertEquals(inJar.keySet(), committed.keySet(), "the stores the jar packages and the fixtures disagree");
        inJar.forEach((name, sql) -> assertEquals(sql, committed.get(name), name + " differs from the jar's copy"));
    }

    @Test
    @DisplayName("ds's schema migrations are packaged, and the extension that queues them is registered")
    void theMigrationsArePackaged() throws IOException {
        Map<String, byte[]> sources = new TreeMap<>();
        Path root = repoRoot.resolve(MIGRATIONS);
        try (Stream<Path> files = Files.walk(root.resolve(MIGRATION_ROOT))) {
            for (var file : files.filter(Files::isRegularFile).toList()) {
                sources.put(root.relativize(file).toString().replace('\\', '/'), Files.readAllBytes(file));
            }
        }
        assertFalse(sources.isEmpty(), "no migrations under " + root.resolve(MIGRATION_ROOT));

        try (var zip = new ZipFile(jar.toFile())) {
            for (var source : sources.entrySet()) {
                var entry = zip.getEntry(source.getKey());
                assertTrue(entry != null, source.getKey() + " is not in connector.jar");
                try (var in = zip.getInputStream(entry)) {
                    assertTrue(Arrays.equals(source.getValue(), in.readAllBytes()),
                            source.getKey() + " in connector.jar differs from the source: rebuild the jar");
                }
            }
            var registrations = zip.getEntry("META-INF/services/org.eclipse.edc.spi.system.ServiceExtension");
            try (var in = zip.getInputStream(registrations)) {
                assertTrue(new String(in.readAllBytes()).lines().anyMatch("dataspaces.edc.EdcSchemaMigrationExtension"::equals),
                        "EdcSchemaMigrationExtension is not registered in connector.jar, so no migration runs");
            }
        }
    }

    private static String edcVersion() throws IOException {
        return Files.readAllLines(repoRoot.resolve("gradle.properties")).stream()
                .filter(l -> l.startsWith("edcVersion="))
                .map(l -> l.substring("edcVersion=".length()).strip())
                .findFirst()
                .orElseThrow(() -> new AssertionError("gradle.properties declares no edcVersion"));
    }

    private static String required(String name) {
        String value = System.getProperty(name);
        assertTrue(value != null && !value.isBlank(),
                () -> "-D" + name + " is not set — see the test block in services/edc-connector/build.gradle.kts");
        return value;
    }
}
