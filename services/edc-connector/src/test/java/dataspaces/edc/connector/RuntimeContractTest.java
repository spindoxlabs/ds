package dataspaces.edc.connector;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * What the participant properties files ask for, against what connector.jar can answer.
 *
 * <p>This unit has no source of its own, so its only real risk is a mismatch between the
 * assembled runtime and the configuration handed to it — and that mismatch is silent in
 * both directions. A setting nothing reads is ignored without a warning. A web context
 * nothing registers on binds a port that answers 404 to everything, so the topology
 * around it — a compose port mapping, a Service port, an Ingress path, an EDR base URL —
 * looks wired up and routes to nothing.
 *
 * <p>Both had happened. `web.http.public.*` and `web.http.version.*` were configured,
 * published by compose, given container and Service ports by the chart, and `/public` was
 * an Ingress path; no packaged module registers a resource on either. `ds.edr.endpoint.
 * public.baseurl` was then pointed at `https://<host>/public` under Helm, so every EDR
 * the provider issued named an endpoint with no listener. Four settings —
 * `edc.dataplane.api.public.baseurl`, `edc.credential.service.url`,
 * `edc.vault.hashicorp.enabled` and `edc.api.key` — were read by no class at all.
 *
 * <p>Nothing in the stack fails when that is true, which is why it is asserted here.
 */
@DisplayName("connector.jar answers what the participant configs ask of it")
class RuntimeContractTest {

    /** Every participant config mounted into an EDC container. */
    private static final List<String> PARTICIPANTS = List.of("rec", "third-party", "grid-operator");

    private static final String API_CONTEXT = "org/eclipse/edc/web/spi/configuration/ApiContext";

    private static PackagedRuntime runtime;
    private static Path repoRoot;

    @BeforeAll
    static void loadArtifact() throws IOException {
        repoRoot = Path.of(requiredProperty("ds.repo.root"));
        Path jar = Path.of(requiredProperty("ds.connector.jar"));
        assertTrue(Files.isRegularFile(jar), () -> jar + " does not exist — the test needs the shadow JAR");
        runtime = PackagedRuntime.read(jar);
        assertTrue(runtime.classCount() > 1000,
                () -> "only " + runtime.classCount() + " classes in the JAR — that is not a full EDC runtime");
    }

    // ── Contexts ────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("every configured web context has a class that registers a resource on it")
    void everyConfiguredWebContextHasARegistrant() throws IOException {
        var declared = runtime.stringsIn(API_CONTEXT + ".class");
        assertTrue(declared.contains("management") && declared.contains("protocol"),
                () -> "ApiContext no longer declares the contexts this test reasons about: " + declared);

        var unbacked = new TreeMap<String, Set<String>>();
        for (var entry : configuredContexts().entrySet()) {
            String context = entry.getKey();
            // The default context (`web.http.port` / `web.http.path`) has no name, and
            // resources land on it through the no-context overload of registerResource.
            // There is nothing to look up, so it is not checked here.
            if (context.isEmpty()) {
                continue;
            }
            if (runtime.classDeclaringAll(API_CONTEXT, "registerResource", context) == null) {
                unbacked.put(context, entry.getValue());
            }
        }

        if (!unbacked.isEmpty()) {
            var report = new StringBuilder("web contexts are configured that no packaged module registers a resource on.\n"
                    + "EDC will bind the port and answer 404 to everything on it, so anything routing to it — a compose\n"
                    + "port mapping, a Service port, an Ingress path, an EDR base URL — points at nothing.\n"
                    + "Either package a module that mounts a resource there, or delete the context and everything routing to it.\n");
            unbacked.forEach((context, keys) ->
                    report.append("  web.http.").append(context).append(".*  set by: ").append(keys).append('\n'));
            fail(report.toString());
        }
    }

    // ── Settings ────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("every non-web setting in the participant configs is read by some packaged class")
    void everySettingIsReadBySomeClass() throws IOException {
        // EDC declares a repeated setting as a config group with a placeholder segment —
        // "edc.datasource.<name>", "edc.iam.trusted-issuer.<issuerAlias>.". A key under
        // one of those is read even though its full literal appears nowhere.
        var groupPrefixes = new TreeSet<String>();
        for (String declared : runtime.allStrings()) {
            int placeholder = declared.indexOf('<');
            if (placeholder <= 0) {
                continue;
            }
            String prefix = declared.substring(0, placeholder);
            if (prefix.endsWith(".") && prefix.indexOf('.') != prefix.length() - 1) {
                groupPrefixes.add(prefix);
            }
        }

        var unread = new TreeMap<String, Set<String>>();
        for (var entry : settingsByKey().entrySet()) {
            String key = entry.getKey();
            if (key.startsWith("web.http.")) {
                continue; // covered by the context test above
            }
            boolean read = runtime.anyClassDeclares(key)
                    || groupPrefixes.stream().anyMatch(key::startsWith);
            if (!read) {
                unread.put(key, entry.getValue());
            }
        }

        if (!unread.isEmpty()) {
            var report = new StringBuilder("settings are configured that no class in connector.jar reads.\n"
                    + "EDC ignores an unknown key silently, so these look like configuration and are not.\n"
                    + "Either package the module that reads the key, or delete the line.\n");
            unread.forEach((key, files) -> report.append("  ").append(key).append("  in: ").append(files).append('\n'));
            fail(report.toString());
        }
    }

    @Test
    @DisplayName("the EDR base URL never points at this connector")
    void edrBaseUrlIsNotAnEdcEndpoint() throws IOException {
        // Consumer-pull traffic goes straight to the dataset API; the connector does not
        // proxy it. HttpDataEndpointExtension rewrites the asset's own base_url origin to
        // this value, so pointing it at an EDC port hands every consumer a dead address —
        // and, because the negotiation and the transfer both still succeed, nothing says so
        // until someone tries to read the data.
        var offenders = new ArrayList<String>();
        for (var entry : settingsByKey().entrySet()) {
            if (!entry.getKey().equals("ds.edr.endpoint.public.baseurl")) {
                continue;
            }
            for (String participant : entry.getValue()) {
                String value = valueOf(participant, "ds.edr.endpoint.public.baseurl");
                if (value.contains("/public") || value.matches(".*:[123]9\\d{3}(/.*)?")) {
                    offenders.add(participant + " → " + value);
                }
                if (value.contains("//localhost")) {
                    offenders.add(participant + " → " + value
                            + "  (raw localhost: an EDR is consumed off-host too — use 172.17.0.1)");
                }
            }
        }
        if (!offenders.isEmpty()) {
            fail("ds.edr.endpoint.public.baseurl must name the dataset API, reachable by the consumer:\n  "
                    + String.join("\n  ", offenders));
        }
    }

    // ── Reading the configs ─────────────────────────────────────────────────────

    /** context name (empty for the default context) → the keys that configured it. */
    private static Map<String, Set<String>> configuredContexts() throws IOException {
        var contexts = new LinkedHashMap<String, Set<String>>();
        settingsByKey().forEach((key, files) -> {
            if (!key.startsWith("web.http.")) {
                return;
            }
            String[] parts = key.split("\\.");
            // web.http.port / web.http.path → the default context, which has no name.
            String context = parts.length <= 3 ? "" : parts[2];
            contexts.computeIfAbsent(context, k -> new LinkedHashSet<>()).add(key);
        });
        return contexts;
    }

    /** setting key → the participant configs that set it. */
    private static Map<String, Set<String>> settingsByKey() throws IOException {
        var keys = new TreeMap<String, Set<String>>();
        for (String participant : PARTICIPANTS) {
            for (var line : Files.readAllLines(configOf(participant))) {
                String trimmed = line.trim();
                if (trimmed.isEmpty() || trimmed.startsWith("#") || !trimmed.contains("=")) {
                    continue;
                }
                String key = trimmed.substring(0, trimmed.indexOf('=')).trim();
                keys.computeIfAbsent(key, k -> new LinkedHashSet<>()).add(participant);
            }
        }
        assertTrue(keys.size() > 10, () -> "only " + keys.size() + " settings read — the configs did not parse");
        return keys;
    }

    private static String valueOf(String participant, String key) throws IOException {
        for (var line : Files.readAllLines(configOf(participant))) {
            String trimmed = line.trim();
            if (trimmed.startsWith(key + "=")) {
                return trimmed.substring(key.length() + 1).trim();
            }
        }
        return "";
    }

    private static Path configOf(String participant) {
        Path config = repoRoot.resolve("services/connector/config").resolve(participant + ".properties");
        assertTrue(Files.isRegularFile(config), () -> config + " does not exist");
        return config;
    }

    private static String requiredProperty(String name) {
        String value = System.getProperty(name);
        assertTrue(value != null && !value.isBlank(),
                () -> "-D" + name + " is not set — see the test block in services/edc-connector/build.gradle.kts");
        return value;
    }
}
