package dataspaces.edc.connector;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * The EDC version has to agree everywhere it is written down.
 *
 * <p>It appears in the Gradle build, in two Dockerfiles, in the Taskfile and in two CI
 * workflows, and a bump that reaches only some of them produces the worst kind of build:
 * `ds-edc-base:<old>` carries a dependency cache resolved for one EDC release while the
 * build resolves another, so the image builds, starts, and differs from what the source
 * says it is.
 *
 * <p>{@code gradle.properties} is the source. This asserts the copies follow.
 */
@DisplayName("the EDC version agrees across the build")
class BuildConsistencyTest {

    /**
     * Files that legitimately carry the version as a literal, with the patterns it takes
     * there. Each must yield at least one match — a check that silently stops matching
     * because a line was renamed is worse than no check.
     */
    private static final Map<String, List<Pattern>> LITERALS = new LinkedHashMap<>(Map.of(
            "services/edc-connector/Dockerfile", List.of(Pattern.compile("ds-edc-base:([0-9][^\\s\"']*)")),
            "services/edc-connector/Dockerfile.base", List.of(Pattern.compile("ds-edc-base:([0-9][^\\s\"']*)")),
            "services/edc-extensions/build.gradle.kts", List.of(Pattern.compile("edcVersion\\s*=\\s*\"([^\"]+)\"")),
            ".github/workflows/edc-base.yml", List.of(Pattern.compile("EDC_VERSION:\\s*\"?([0-9][^\\s\"']*)")),
            ".github/workflows/release.yml", List.of(Pattern.compile("ds-edc-base:([0-9][^\\s\"']*)"))));

    private static final Path REPO = Path.of(System.getProperty("ds.repo.root", ""));

    @Test
    @DisplayName("every hardcoded copy matches gradle.properties")
    void everyCopyMatchesTheSource() throws IOException {
        String expected = expectedVersion();

        var wrong = new TreeMap<String, TreeSet<String>>();
        var silent = new TreeSet<String>();

        for (var entry : LITERALS.entrySet()) {
            Path file = REPO.resolve(entry.getKey());
            assertTrue(Files.isRegularFile(file), () -> file + " does not exist — update this test with it");
            String content = Files.readString(file);

            int matches = 0;
            for (Pattern pattern : entry.getValue()) {
                var matcher = pattern.matcher(content);
                while (matcher.find()) {
                    matches++;
                    String found = matcher.group(1);
                    if (!found.equals(expected)) {
                        wrong.computeIfAbsent(entry.getKey(), k -> new TreeSet<>()).add(found);
                    }
                }
            }
            if (matches == 0) {
                silent.add(entry.getKey());
            }
        }

        if (!silent.isEmpty()) {
            fail("no version literal found in " + silent + " — the pattern in this test no longer matches, "
                    + "so these files were not actually checked. Fix the pattern or drop the entry.");
        }
        if (!wrong.isEmpty()) {
            fail("gradle.properties says edcVersion=" + expected + ", but:\n  " + wrong);
        }
    }

    @Test
    @DisplayName("the Taskfile derives the version rather than repeating it")
    void taskfileDoesNotHardcodeTheVersion() throws IOException {
        Path taskfile = REPO.resolve("Taskfile.yml");
        String content = Files.readString(taskfile);
        var matcher = Pattern.compile("ds-edc-base:([0-9][^\\s\"'{}]*)").matcher(content);
        var hardcoded = new TreeSet<String>();
        while (matcher.find()) {
            hardcoded.add(matcher.group(1));
        }
        if (!hardcoded.isEmpty()) {
            fail("Taskfile.yml hardcodes the EDC base image version " + hardcoded
                    + ". It reads gradle.properties into the EDC_VERSION var — use {{.EDC_VERSION}}.");
        }
    }

    @Test
    @DisplayName("both Docker stages copy the file the version now lives in")
    void dockerBuildsCopyGradleProperties() throws IOException {
        // Moving edcVersion into gradle.properties made it a build descriptor, and
        // the two Dockerfiles copy the descriptors individually rather than the
        // whole tree. Omitting it fails the image build with "Cannot get non-null
        // property 'edcVersion'" — several minutes into a rebuild, and only there:
        // `task edc:build` mounts the repo and never notices.
        for (String path : List.of("services/edc-connector/Dockerfile", "services/edc-connector/Dockerfile.base")) {
            Path file = REPO.resolve(path);
            assertTrue(Files.isRegularFile(file), () -> file + " does not exist");
            String content = Files.readString(file);
            assertTrue(Pattern.compile("^COPY\\s[^\\n]*\\bgradle\\.properties\\b", Pattern.MULTILINE)
                            .matcher(content).find(),
                    () -> path + " does not COPY gradle.properties, which carries edcVersion — "
                            + "the Gradle build inside this stage cannot resolve it");
        }
    }

    private static String expectedVersion() throws IOException {
        Path properties = REPO.resolve("gradle.properties");
        assertTrue(Files.isRegularFile(properties), () -> properties + " does not exist");
        for (String line : Files.readAllLines(properties)) {
            String trimmed = line.trim();
            if (trimmed.startsWith("edcVersion=")) {
                return trimmed.substring("edcVersion=".length()).trim();
            }
        }
        return fail("gradle.properties carries no edcVersion");
    }
}
