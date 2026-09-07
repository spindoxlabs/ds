package dataspaces.edc.connector;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertFalse;
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

    /** The production render of the same settings — see chartSettingsByKey(). */
    private static final String CHART_CONFIGMAP = "helm/charts/ds-edc/templates/configmap.yaml";

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

    // ── Data-plane signalling ───────────────────────────────────────────────────

    /**
     * The pre-DPS signalling extension, which provides {@code LegacyDataPlaneSignalingFlowController}
     * and — because ds embeds its data plane — an {@code EmbeddedDataPlaneClient}.
     */
    private static final String LEGACY_SIGNALING_EXTENSION =
            "org.eclipse.edc.connector.controlplane.transfer.dataplane.TransferDataPlaneSignalingExtension";

    /** Every extension DPS registers lives under this package. */
    private static final String DPS_PACKAGE = "org.eclipse.edc.signaling.";

    @Test
    @DisplayName("the connector signals its data plane in-process, not over DPS")
    void dataPlaneSignallingStaysPreDps() {
        var extensions = runtime.serviceExtensions();
        assertFalse(extensions.isEmpty(),
                () -> "no ServiceExtension registrations found in the JAR — this guard reads "
                        + "META-INF/services, and if that moved every assertion below is vacuous");

        var dps = extensions.stream().filter(it -> it.startsWith(DPS_PACKAGE)).sorted().toList();

        assertTrue(extensions.contains(LEGACY_SIGNALING_EXTENSION),
                () -> """
                        %s is not packaged, so nothing provides a DataFlowController and every transfer \
                        fails at `prepare data flow`.

                        `services/edc-connector/build.gradle.kts` adds it deliberately: EDC 0.18.0 swapped \
                        controlplane-base-bom onto DPS (`data-protocols:data-plane-signaling`), whose client \
                        sends plain JSON over HTTP, while dataplane-base-bom still serves the pre-DPS JSON-LD \
                        API and EDC ships no DPS data-plane server. If a BOM reshuffle renamed the module, \
                        the `exclude` and the added dependency both need revisiting — together.

                        Registered DPS extensions: %s""".formatted(LEGACY_SIGNALING_EXTENSION, dps));

        assertTrue(dps.isEmpty(),
                () -> """
                        DPS extensions are packaged alongside the pre-DPS one: %s

                        Two DataFlowController providers for a single-valued injection point, and the DPS \
                        client would talk HTTP+plain-JSON to a JSON-LD endpoint — `Failed to expand JsonObject \
                        … missing '@context'`, which reads as a data problem and is not one.

                        Either the `exclude` block in services/edc-connector/build.gradle.kts stopped matching \
                        (coordinates renamed upstream), or DPS was adopted on purpose. Adopting it means a data \
                        plane that speaks it — a capability decision, not a version bump.""".formatted(dps));
    }

    // ── Settings ────────────────────────────────────────────────────────────────

    @Test
    @DisplayName("every non-web setting in the participant configs is read by some packaged class")
    void everySettingIsReadBySomeClass() throws IOException {
        reportUnread(unreadSettings(settingsByKey()));
    }

    @Test
    @DisplayName("every non-web setting in the Helm chart is read by some packaged class")
    void everyChartSettingIsReadBySomeClass() throws IOException {
        // The chart renders the same properties file for production and was covered by
        // nothing, so it could — and did — carry keys the participant configs had already
        // been fixed for. It is the one copy no developer ever starts a runtime against.
        reportUnread(unreadSettings(chartSettingsByKey()));
    }

    /**
     * The configured keys that no packaged class reads.
     *
     * <p>EDC declares a repeated setting as a config group with a placeholder segment —
     * {@code edc.datasource.<name>}, {@code edc.iam.trusted-issuer.<issuerAlias>.}. A key
     * under one of those is read even though its full literal appears nowhere, so a group
     * match has to be allowed.
     *
     * <p>What it must not do is allow the <em>whole</em> key on the strength of its
     * prefix. That is how three connection-pool settings survived: EDC has read
     * {@code pool.connections.max-idle} since well before the pinned version, ds set
     * {@code pool.maxIdleConnections}, and every ds connector ran on library defaults
     * while this test — whose entire purpose is to say so — passed, because the key
     * started with {@code edc.datasource.} and nothing looked further. So under a group,
     * the instance segment is dropped ({@code default}, {@code 0}, {@code membership})
     * and the remainder must be a string constant of a class that declares that group.
     */
    private static Map<String, Set<String>> unreadSettings(Map<String, Set<String>> settings) {
        var groups = configGroups();

        var unread = new TreeMap<String, Set<String>>();
        for (var entry : settings.entrySet()) {
            String key = entry.getKey();
            if (key.startsWith("web.http.")) {
                continue; // covered by the context test above
            }
            if (runtime.anyClassDeclares(key)) {
                continue;
            }
            // Longest match wins: a key can sit under two declared prefixes, and only the
            // longer one names the module that actually owns it.
            String group = groups.keySet().stream()
                    .filter(key::startsWith)
                    .max(Comparator.comparingInt(String::length))
                    .orElse(null);
            if (group == null) {
                unread.put(key, entry.getValue());
                continue;
            }
            var owner = groups.get(group);
            String rest = key.substring(group.length());
            String suffix;
            if (owner.instanced()) {
                int instanceEnd = rest.indexOf('.');
                suffix = instanceEnd < 0 ? null : rest.substring(instanceEnd + 1);
            } else {
                suffix = rest;
            }
            if (suffix == null || !owner.declared().contains(suffix)) {
                unread.put(key, entry.getValue());
            }
        }
        return unread;
    }

    /**
     * A declared config group: whether its keys carry an instance segment, and the string
     * constants of the module that declares it.
     */
    private record ConfigGroup(boolean instanced, Set<String> declared) {
    }

    /**
     * Declared config-group prefix → what the module that declares it accepts under it.
     *
     * <p>EDC has two forms, and the runtime carries both.
     *
     * <p><strong>The annotation.</strong> {@code @Configuration(context = "edc.datasource")}
     * on a field. This is how every group ds configures is declared at 0.18.0 —
     * {@code edc.datasource}, {@code edc.iam.trustedissuer} (and its deprecated spelling),
     * {@code edc.iam.dcp.scopes}. A {@code Map}-typed field means the key carries an
     * instance segment; anything else means the suffix follows the prefix directly.
     *
     * <p><strong>The placeholder literal.</strong> {@code edc.callback.<cbAlias>.} as a
     * string constant. Until 0.17 this was the only form and finding a {@code <} was enough;
     * 0.18.0 moved the groups to the annotation and left two of these behind. Reading only
     * this form against an 0.18.0 JAR reports every grouped key ds sets as unread, which is
     * how this was found.
     *
     * <p>The annotation is authoritative where both name the same prefix.
     */
    /**
     * Every suffix a group accepts: those declared on the annotated class (and its nested
     * records), plus those on the field's own type when the settings record is a separate
     * top-level class.
     *
     * <p>{@code edc.policy.monitor} is the case that forced this. {@code PolicyMonitorExtension}
     * annotates a field of type {@code PolicyMonitorConfiguration}, and that record — not the
     * extension, and not a class nested in it — carries {@code @Setting(key = "period")}. Read
     * from the extension alone, a correctly spelled `edc.policy.monitor.period` is reported as
     * read by nothing, which is indistinguishable from the typo this test exists to catch.
     *
     * <p>Following the declared type is deliberately narrower than matching on the prefix:
     * the suffix still has to be declared somewhere the runtime actually reads it. Widening
     * to "anything under the prefix" is what let `pool.maxIdleConnections` pass for two years.
     */
    private static Set<String> suffixesOf(PackagedRuntime runtime, PackagedRuntime.GroupDeclaration declaration) {
        var suffixes = new HashSet<>(runtime.stringsOfClassAndNested(declaration.declaredBy()));
        if (declaration.settingsClass() != null) {
            suffixes.addAll(runtime.stringsOfClassAndNested(declaration.settingsClass()));
        }
        return suffixes;
    }

    private static Map<String, ConfigGroup> configGroups() {
        var groups = new TreeMap<String, ConfigGroup>();

        for (String declared : runtime.allStrings()) {
            int placeholder = declared.indexOf('<');
            if (placeholder <= 0) {
                continue;
            }
            String prefix = declared.substring(0, placeholder);
            if (prefix.endsWith(".") && prefix.indexOf('.') != prefix.length() - 1) {
                groups.computeIfAbsent(prefix,
                        p -> new ConfigGroup(true, runtime.stringsOfClassesDeclaringGroup(p)));
            }
        }

        for (var declaration : runtime.configGroupDeclarations()) {
            groups.merge(
                    declaration.prefix(),
                    new ConfigGroup(declaration.instanced(),
                            suffixesOf(runtime, declaration)),
                    // Two modules may declare the same context — the trusted-issuer
                    // extension declares its current and deprecated spellings on separate
                    // fields. Union what they accept rather than letting one win.
                    (a, b) -> new ConfigGroup(a.instanced() || b.instanced(), union(a.declared(), b.declared())));
        }

        assertTrue(groups.containsKey("edc.datasource."),
                () -> "no `edc.datasource` config group found in the JAR — the group declarations this test "
                        + "reads have moved again, and every grouped key is about to be reported as unread. "
                        + "Found: " + groups.keySet());
        return groups;
    }

    private static Set<String> union(Set<String> a, Set<String> b) {
        var all = new LinkedHashSet<>(a);
        all.addAll(b);
        return all;
    }

    private static void reportUnread(Map<String, Set<String>> unread) {
        if (unread.isEmpty()) {
            return;
        }
        var report = new StringBuilder("settings are configured that no class in connector.jar reads.\n"
                + "EDC ignores an unknown key silently, so these look like configuration and are not.\n"
                + "Package the module that reads the key, correct the key, or delete the line.\n");
        unread.forEach((key, files) -> report.append("  ").append(key).append("  in: ").append(files).append('\n'));
        fail(report.toString());
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

    /**
     * setting key → the single source that sets it, for the chart's rendered properties.
     *
     * <p>The template is Helm, not properties: the assignments live inside
     * `edc.properties: |`, and the only other lines carrying an `=` are the
     * `{{- $x := ... -}}` assignments at the top. Matching a line that *starts* with a bare
     * key excludes those and every comment, without rendering the chart. The count
     * assertion below is what says the match still finds anything at all.
     */
    private static Map<String, Set<String>> chartSettingsByKey() throws IOException {
        Path template = repoRoot.resolve(CHART_CONFIGMAP);
        assertTrue(Files.isRegularFile(template), () -> template + " does not exist");

        var keys = new TreeMap<String, Set<String>>();
        var assignment = Pattern.compile("^([a-z][a-zA-Z0-9._-]*)=");
        for (var line : Files.readAllLines(template)) {
            var matcher = assignment.matcher(line.trim());
            if (matcher.find()) {
                keys.computeIfAbsent(matcher.group(1), k -> new LinkedHashSet<>()).add(CHART_CONFIGMAP);
            }
        }
        assertTrue(keys.size() > 10,
                () -> "only " + keys.size() + " settings read from " + CHART_CONFIGMAP + " — it did not parse");
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
