package dataspaces.edc.connector;

import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.HashSet;
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
 */
final class PackagedRuntime {

    private final Map<String, Set<String>> stringsByClass = new HashMap<>();

    private PackagedRuntime() {
    }

    static PackagedRuntime read(Path jar) throws IOException {
        var runtime = new PackagedRuntime();
        try (var zip = new ZipFile(jar.toFile())) {
            var entries = zip.entries();
            while (entries.hasMoreElements()) {
                ZipEntry entry = entries.nextElement();
                if (entry.isDirectory() || !entry.getName().endsWith(".class")) {
                    continue;
                }
                try (InputStream in = zip.getInputStream(entry)) {
                    runtime.stringsByClass.put(entry.getName(), constantPoolStrings(in));
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
     * CONSTANT_Utf8 entries of a class file.
     *
     * <p>Only the constant pool is walked; everything after it is irrelevant here and is
     * not read. Tag sizes are from JVMS §4.4 — Long and Double take two pool slots, which
     * is the one rule a naive parser gets wrong and then silently mis-reads the rest.
     */
    private static Set<String> constantPoolStrings(InputStream raw) throws IOException {
        var in = new DataInputStream(raw);
        int magic = in.readInt();
        if (magic != 0xCAFEBABE) {
            throw new IllegalStateException("not a class file");
        }
        in.readUnsignedShort(); // minor
        in.readUnsignedShort(); // major
        int count = in.readUnsignedShort();
        var strings = new HashSet<String>();
        for (int i = 1; i < count; i++) {
            int tag = in.readUnsignedByte();
            switch (tag) {
                case 1 -> { // Utf8
                    int length = in.readUnsignedShort();
                    var bytes = new byte[length];
                    in.readFully(bytes);
                    strings.add(new String(bytes, StandardCharsets.UTF_8));
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
        return strings;
    }
}
