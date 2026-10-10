package dataspaces.edc;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.failsafe.RetryPolicy;
import okhttp3.OkHttpClient;
import okhttp3.Response;
import org.eclipse.edc.iam.did.spi.resolution.DidResolver;
import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The EDC resolves did:web through ds's guarded resolver, which replaces EDC's
 * {@code WebDidResolver} registration for the method {@code web} (ADR-0029).
 *
 * <p>EDC 0.18.0's {@code DidResolverRegistryImpl} keeps one resolver per method
 * and the last {@code register} wins; {@code WebDidExtension} registers in
 * {@code initialize}, so ds registers in {@code prepare}, which runs after every
 * extension's {@code initialize}. The shared {@code OkHttpClient} is left alone:
 * only did:web documents go through the guarded {@code Dns}.
 *
 * <p>{@code localhost} resolves to loopback on every test machine: refused under
 * production before any connection, admitted under dev (then refused by the
 * closed port, a different failure).
 */
class DidWebGuardExtensionTest {

    private static final RetryPolicy<Response> NO_RETRY = RetryPolicy.<Response>builder().withMaxRetries(0).build();

    private static DidResolver resolver(boolean dev, DidWebAddressGuard.Allowance allowance) {
        return DidWebGuardExtension.guardedResolver(new OkHttpClient(), NO_RETRY, new ObjectMapper(),
            new NullMonitor(), false, dev, allowance);
    }

    @Test
    void theResolverIsForTheWebMethod() {
        assertEquals("web", resolver(false, DidWebAddressGuard.Allowance.NONE).getMethod());
    }

    @Test
    void underProductionALoopbackDidHostIsRefusedBeforeAnyConnection() {
        var result = resolver(false, DidWebAddressGuard.Allowance.NONE).resolve("did:web:localhost%3A1");
        assertTrue(result.failed());
        assertTrue(result.getFailureDetail().contains("non-public"), result.getFailureDetail());
    }

    @Test
    void underDevTheLocalTopologyIsDialled() {
        var result = resolver(true, DidWebAddressGuard.Allowance.NONE).resolve("did:web:localhost%3A1");
        assertTrue(result.failed());
        assertFalse(result.getFailureDetail().contains("non-public"), result.getFailureDetail());
    }

    @Test
    void prepareRegistersTheGuardedResolverAfterEveryInitialize() {
        var registered = new ArrayList<DidResolver>();
        var extension = new DidWebGuardExtension();
        extension.configure(Map.of("ds.env", "production")::get, new NullMonitor(), new OkHttpClient(), NO_RETRY,
            new ObjectMapper(), registered::add);
        assertTrue(registered.isEmpty(), "initialize must not register: WebDidExtension's would replace it");
        extension.prepare();
        assertEquals(1, registered.size());
        assertEquals("web", registered.get(0).getMethod());
        assertTrue(registered.get(0).resolve("did:web:localhost%3A1").getFailureDetail().contains("non-public"));
    }

    @Test
    void theAllowanceIsReadAndLogged() {
        var monitor = new NullMonitor();
        var registered = new ArrayList<DidResolver>();
        var extension = new DidWebGuardExtension();
        extension.configure(Map.of("ds.env", "production",
                DidWebGuardExtension.INTERNAL_HOSTS, ".ds.example.org",
                DidWebGuardExtension.INTERNAL_NETWORKS, "192.168.1.10/32")::get,
            monitor, new OkHttpClient(), NO_RETRY, new ObjectMapper(), registered::add);
        assertTrue(monitor.warnings.stream().anyMatch(w -> w.contains(
            "did:web internal allowance active: hosts under .ds.example.org may resolve to 192.168.1.10/32")),
            monitor.warnings.toString());
    }

    @Test
    void anUnsoundAllowanceRefusesToStart() {
        var extension = new DidWebGuardExtension();
        var refused = assertThrows(EdcException.class, () -> extension.configure(
            Map.of(DidWebGuardExtension.INTERNAL_HOSTS, ".ds.example.org")::get, new NullMonitor(),
            new OkHttpClient(), NO_RETRY, new ObjectMapper(), r -> { }));
        assertTrue(refused.getMessage().contains("did:web internal allowance"), refused.getMessage());
    }

    @Test
    void dnsOverHttpsIsRefusedRatherThanSilentlyBypassed() {
        // The guard replaces EDC's resolver, and with it `edc.webdid.doh.url`.
        var extension = new DidWebGuardExtension();
        var refused = assertThrows(EdcException.class, () -> extension.configure(
            Map.of("edc.webdid.doh.url", "https://doh.example.org/dns-query")::get, new NullMonitor(),
            new OkHttpClient(), NO_RETRY, new ObjectMapper(), r -> { }));
        assertTrue(refused.getMessage().contains("edc.webdid.doh.url"), refused.getMessage());
    }

    static class NullMonitor implements Monitor {
        final List<String> warnings = new ArrayList<>();

        @Override
        public void warning(Supplier<String> supplier, Throwable... errors) {
            warnings.add(supplier.get());
        }

        @Override
        public void info(Supplier<String> supplier, Throwable... errors) {
        }

        @Override
        public void severe(Supplier<String> supplier, Throwable... errors) {
        }

        @Override
        public void debug(Supplier<String> supplier, Throwable... errors) {
        }
    }
}
