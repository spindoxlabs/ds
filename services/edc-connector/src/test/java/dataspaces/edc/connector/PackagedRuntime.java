package dataspaces.edc.connector;

import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/**
 * The string constants of every class packaged in {@code connector.jar}.
 *
 * <p>EDC declares a setting by its literal key — {@code @Setting("edc.hostname")} — and
 * names a web context by an {@code ApiContext} constant, which javac inlines into the
 * constant pool of whatever references it. So "does this runtime read this setting" and
 * "does anything register on this context" are both answerable from the artifact, without
 * starting it and without a list maintained by hand.
 *
 * <p>The constant pool is parsed rather than grepped. A substring search over class bytes
 * finds {@code public} inside {@code PublicEndpointGeneratorService} and inside
 * {@code edc.dataplane.api.public.baseurl}, which is exactly the false positive that would
 * make the context test pass while a context sits there with nothing behind it.
 *
 * <p>Field annotations are parsed too, for one reason: {@code @Configuration(context = ...)}
 * is how EDC 0.18.0 declares a <em>config group</em>, and a group's keys never appear as a
 * literal anywhere. Until 0.17 the declaration was itself a string constant — {@code
 * edc.datasource.<name>} — and scanning the pool for a {@code <} found every group. 0.18.0
 * moved every one of them to the annotation and dropped the placeholder strings, so that
 * scan now finds two leftovers and misses the datasource, trusted-issuer and DCP-scope
 * groups entirely. The consequence is not a weaker check but a false alarm: every grouped
 * key ds sets reports as unread. Reading the annotation is what restores the distinction.
 */
final class PackagedRuntime {

    /**
     * How EDC decides what to load. The shadow JAR merges every module's copy into this one
     * file, so it is the only honest answer to "which extensions does this runtime have" —
     * a class being present says nothing, since an unregistered extension is inert.
     */
    private static final String SERVICE_EXTENSION_REGISTRATIONS =
            "META-INF/services/org.eclipse.edc.spi.system.ServiceExtension";

    private static final String CONFIGURATION_ANNOTATION =
            "Lorg/eclipse/edc/runtime/metamodel/annotation/Configuration;";

    private final Map<String, Set<String>> stringsByClass = new HashMap<>();
    private final List<GroupDeclaration> groupDeclarations = new ArrayList<>();
    private final Set<String> serviceExtensions = new HashSet<>();

    private PackagedRuntime() {
    }

    /**
     * A config group EDC declares, and the class that declares it.
     *
     * @param prefix     the context, always with a trailing dot: {@code edc.datasource.}
     * @param instanced  true when the annotated field is a {@code Map}, i.e. the key carries
     *                   an instance segment ({@code default}, {@code 0}, {@code membership})
     *                   between the prefix and the setting suffix. A non-Map field is a
     *                   plain nested settings object, where the suffix follows directly.
     * @param declaredBy the class file that carries the annotation
     * @param settingsClass the class file of the field's declared type when that type models
     *                   the group's settings, else {@code null}. EDC declares a group's
     *                   suffixes on the extension, on a record nested inside it, or — as
     *                   {@code PolicyMonitorExtension} does for {@code edc.policy.monitor} —
     *                   on a **separate top-level record**. The first two are reachable from
     *                   {@code declaredBy}; the third is only reachable by following the
     *                   field's type, which is what this holds.
     */
    record GroupDeclaration(String prefix, boolean instanced, String declaredBy, String settingsClass) {
    }

    static PackagedRuntime read(Path jar) throws IOException {
        var runtime = new PackagedRuntime();
        try (var zip = new ZipFile(jar.toFile())) {
            var entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory()) {
                    continue;
                }
                if (SERVICE_EXTENSION_REGISTRATIONS.equals(entry.getName())) {
                    try (InputStream in = zip.getInputStream(entry)) {
                        runtime.readServiceExtensions(in);
                    }
                    continue;
                }
                if (!entry.getName().endsWith(".class")) {
                    continue;
                }
                try (InputStream in = zip.getInputStream(entry)) {
                    runtime.readClass(entry.getName(), in);
                } catch (IOException | IllegalStateException e) {
                    // A class this parser cannot read must not silently reduce coverage.
                    throw new IOException("cannot read " + entry.getName() + " from " + jar, e);
                }
            }
        }
        if (runtime.stringsByClass.isEmpty()) {
            throw new IllegalStateException("no classes found in " + jar);
        }
        return runtime;
    }

    int classCount() {
        return stringsByClass.size();
    }

    /** Every {@code ServiceExtension} the packaged runtime will actually load. */
    Set<String> serviceExtensions() {
        return Set.copyOf(serviceExtensions);
    }

    private void readServiceExtensions(InputStream in) throws IOException {
        try (var reader = new java.io.BufferedReader(
                new java.io.InputStreamReader(in, java.nio.charset.StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                // ServiceLoader syntax: a `#` comment and surrounding space are not names.
                int hash = line.indexOf('#');
                String name = (hash < 0 ? line : line.substring(0, hash)).trim();
                if (!name.isEmpty()) {
                    serviceExtensions.add(name);
                }
            }
        }
    }

    /** Every string constant in the class at {@code entryName}, or empty if absent. */
    Set<String> stringsIn(String entryName) {
        return stringsByClass.getOrDefault(entryName, Set.of());
    }

    /** True when some packaged class carries {@code value} as a string constant. */
    boolean anyClassDeclares(String value) {
        return stringsByClass.values().stream().anyMatch(s -> s.contains(value));
    }

    /**
     * The entry name of some class carrying all of {@code required}, or null.
     * Used to ask "is there a class that mentions ApiContext, registerResource and this
     * context name" — the shape of every extension that mounts a resource.
     */
    String classDeclaringAll(String... required) {
        for (var entry : stringsByClass.entrySet()) {
            var strings = entry.getValue();
            boolean all = true;
            for (String value : required) {
                if (!strings.contains(value)) {
                    all = false;
                    break;
                }
            }
            if (all) {
                return entry.getKey();
            }
        }
        return null;
    }

    /**
     * Every string constant in the runtime, flattened. Callers that need to match a
     * setting against EDC's config-group declarations ({@code edc.datasource.<name>})
     * scan this.
     */
    Set<String> allStrings() {
        var all = new HashSet<String>();
        stringsByClass.values().forEach(all::addAll);
        return all;
    }

    /**
     * The string constants of every class that declares the config group {@code prefix} as a
     * placeholder literal — a string like {@code edc.datasource.<name>}.
     *
     * <p>Keys under a group are declared as bare suffixes ({@code pool.connections.max-idle}),
     * so the only way to tell a real one from a typo is to ask the module that owns the
     * group. Asking the whole runtime instead would match {@code url} and {@code user}
     * against any class that happens to carry those words, which is no check at all.
     *
     * <p>This is the pre-0.18 form. Two of it survive in the 0.18.0 runtime
     * ({@code edc.callback.<cbAlias>.}, {@code web.http.<context>.auth.}); everything ds
     * configures now comes through {@link #configGroupDeclarations()}.
     */
    Set<String> stringsOfClassesDeclaringGroup(String prefix) {
        var all = new HashSet<String>();
        for (var strings : stringsByClass.values()) {
            if (strings.stream().anyMatch(s -> s.startsWith(prefix) && s.indexOf('<') == prefix.length())) {
                all.addAll(strings);
            }
        }
        return all;
    }

    /** Every {@code @Configuration(context = ...)} declaration in the packaged runtime. */
    List<GroupDeclaration> configGroupDeclarations() {
        return List.copyOf(groupDeclarations);
    }

    /**
     * The class file a field descriptor names, or {@code null} for anything that is not a
     * plain object type.
     *
     * <p>Deliberately not resolved against the jar here: a type outside the runtime simply
     * contributes no strings, which is the same answer as a type that declares none.
     */
    private static String settingsClassOf(String descriptor) {
        if (descriptor == null || !descriptor.startsWith("L") || !descriptor.endsWith(";")) {
            return null;
        }
        return descriptor.substring(1, descriptor.length() - 1) + ".class";
    }

    /**
     * The string constants of {@code entryName} and of its nested classes.
     *
     * <p>A group's suffixes are declared either on the extension itself — as the
     * {@code public static final String} constants {@code @Setting(key = ...)} refers to —
     * or on the nested record that models the group's settings, which javac emits as
     * {@code Outer$Nested.class}. The datasource group puts them in both; asking for the
     * outer class alone would be right today and silently wrong the first time a module
     * declares them only on the record.
     */
    Set<String> stringsOfClassAndNested(String entryName) {
        var all = new HashSet<String>(stringsByClass.getOrDefault(entryName, Set.of()));
        String nestedPrefix = entryName.substring(0, entryName.length() - ".class".length()) + "$";
        stringsByClass.forEach((name, strings) -> {
            if (name.startsWith(nestedPrefix)) {
                all.addAll(strings);
            }
        });
        return all;
    }

    /**
     * The constant pool and the field annotations of one class file.
     *
     * <p>Tag sizes are from JVMS §4.4 — Long and Double take two pool slots, which is the
     * one rule a naive parser gets wrong and then silently mis-reads the rest. The pool is
     * indexed rather than collected into a set, because an annotation element value is a
     * pool <em>index</em> and has to be resolved.
     *
     * <p>Parsing stops at the end of the field table: {@code @Configuration} is a field
     * annotation in every EDC module, and the method table behind it is large and of no
     * interest here.
     */
    private void readClass(String entryName, InputStream raw) throws IOException {
        var in = new DataInputStream(raw);
        if (in.readInt() != 0xCAFEBABE) {
            throw new IllegalStateException("not a class file");
        }
        in.readUnsignedShort(); // minor
        in.readUnsignedShort(); // major

        int count = in.readUnsignedShort();
        var utf8 = new String[count];
        for (int i = 1; i < count; i++) {
            int tag = in.readUnsignedByte();
            switch (tag) {
                case 1 -> { // Utf8
                    int length = in.readUnsignedShort();
                    var bytes = new byte[length];
                    in.readFully(bytes);
                    utf8[i] = new String(bytes, StandardCharsets.UTF_8);
                }
                case 7, 8, 16, 19, 20 -> in.skipNBytes(2);
                case 15 -> in.skipNBytes(3);
                case 3, 4, 9, 10, 11, 12, 17, 18 -> in.skipNBytes(4);
                case 5, 6 -> { // Long, Double — occupy two pool slots
                    in.skipNBytes(8);
                    i++;
                }
                default -> throw new IllegalStateException("unknown constant pool tag " + tag);
            }
        }

        var strings = new HashSet<String>();
        for (String value : utf8) {
            if (value != null) {
                strings.add(value);
            }
        }
        stringsByClass.put(entryName, strings);

        in.skipNBytes(2); // access_flags
        in.skipNBytes(2); // this_class
        in.skipNBytes(2); // super_class
        in.skipNBytes(2L * in.readUnsignedShort()); // interfaces

        int fields = in.readUnsignedShort();
        for (int f = 0; f < fields; f++) {
            in.skipNBytes(2); // access_flags
            in.skipNBytes(2); // name_index
            String descriptor = utf8[in.readUnsignedShort()];
            int attributes = in.readUnsignedShort();
            for (int a = 0; a < attributes; a++) {
                String name = utf8[in.readUnsignedShort()];
                long length = in.readInt() & 0xFFFFFFFFL;
                if ("RuntimeVisibleAnnotations".equals(name)) {
                    var payload = new byte[(int) length];
                    in.readFully(payload);
                    readFieldAnnotations(entryName, descriptor, utf8, new DataInputStream(
                            new java.io.ByteArrayInputStream(payload)));
                } else {
                    in.skipNBytes(length);
                }
            }
        }
    }

    /**
     * Records every {@code @Configuration(context = "...")} on one field.
     *
     * <p>A {@code Map}-typed field is a group with an instance segment — one datasource,
     * one trusted issuer, one DCP scope per instance. Any other type is a nested settings
     * object whose suffixes follow the prefix directly. Conflating the two would accept
     * {@code edc.negotiation.anything.send.retry.limit} as if the middle segment named an
     * instance, which is exactly the kind of quiet pass this test exists to prevent.
     *
     * <p>A {@code @Configuration} with no {@code context} element is not a group and is
     * ignored.
     */
    private void readFieldAnnotations(String entryName, String descriptor, String[] utf8, DataInputStream in)
            throws IOException {
        int annotations = in.readUnsignedShort();
        for (int i = 0; i < annotations; i++) {
            String type = utf8[in.readUnsignedShort()];
            int pairs = in.readUnsignedShort();
            for (int p = 0; p < pairs; p++) {
                String element = utf8[in.readUnsignedShort()];
                String value = readElementValue(utf8, in);
                if (CONFIGURATION_ANNOTATION.equals(type) && "context".equals(element) && value != null
                        && !value.isBlank()) {
                    String prefix = value.endsWith(".") ? value : value + ".";
                    boolean instanced = "Ljava/util/Map;".equals(descriptor);
                    groupDeclarations.add(new GroupDeclaration(
                            prefix, instanced, entryName, instanced ? null : settingsClassOf(descriptor)));
                }
            }
        }
    }

    /**
     * One {@code element_value} (JVMS §4.7.16.1), returning it when it is a String constant
     * and null otherwise. Every branch consumes its bytes, so an unread value still leaves
     * the stream positioned correctly for the next pair.
     */
    private static String readElementValue(String[] utf8, DataInputStream in) throws IOException {
        int tag = in.readUnsignedByte();
        switch (tag) {
            case 's' -> {
                return utf8[in.readUnsignedShort()];
            }
            case 'B', 'C', 'D', 'F', 'I', 'J', 'S', 'Z', 'c' -> in.skipNBytes(2);
            case 'e' -> in.skipNBytes(4);
            case '@' -> {
                in.skipNBytes(2); // nested annotation type
                int pairs = in.readUnsignedShort();
                for (int p = 0; p < pairs; p++) {
                    in.skipNBytes(2); // element name
                    readElementValue(utf8, in);
                }
            }
            case '[' -> {
                int values = in.readUnsignedShort();
                for (int v = 0; v < values; v++) {
                    readElementValue(utf8, in);
                }
            }
            default -> throw new IllegalStateException("unknown annotation element tag " + (char) tag);
        }
        return null;
    }
}
