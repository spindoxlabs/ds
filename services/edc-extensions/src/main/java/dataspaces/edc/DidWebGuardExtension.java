package dataspaces.edc;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.failsafe.RetryPolicy;
import okhttp3.Dns;
import okhttp3.OkHttpClient;
import okhttp3.Response;
import org.eclipse.edc.http.client.EdcHttpClientImpl;
import org.eclipse.edc.iam.did.spi.resolution.DidResolver;
import org.eclipse.edc.iam.did.spi.resolution.DidResolverRegistry;
import org.eclipse.edc.iam.did.web.resolution.WebDidResolver;
import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.runtime.metamodel.annotation.Setting;
import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.spi.types.TypeManager;

import java.util.function.Consumer;
import java.util.function.Function;

/**
 * The EDC's did:web documents are fetched behind ds's address guard (ADR-0029).
 *
 * <p>EDC 0.18.0's {@code WebDidExtension} registers {@code WebDidResolver} over the
 * runtime's shared {@code EdcHttpClient} in {@code initialize}, with no address
 * check: a counterparty that presents a DID whose host resolves into the cluster
 * (or to the metadata endpoint) has the EDC fetch it. This extension registers the
 * <b>same upstream resolver class</b> for the method {@code web}, over an
 * {@code EdcHttpClientImpl} built from a copy of the runtime's {@code OkHttpClient}
 * (its timeouts, interceptors and listener) whose {@code Dns} is
 * {@link DidWebAddressGuard.GuardedDns}. Every other outbound call keeps the shared
 * client untouched: only did:web documents are guarded.
 *
 * <p><b>Why {@code prepare}.</b> {@code DidResolverRegistryImpl} keeps one resolver
 * per method and the last {@code register} wins, silently. Every extension's
 * {@code initialize} runs before any {@code prepare} ({@code ExtensionLifecycleManager}),
 * so registering here replaces EDC's whatever the extension order.
 *
 * <p>Settings: {@code ds.env} (from {@code DS_ENV}: only {@code dev} admits private
 * and loopback addresses), {@code ds.did.web.internal.hosts} /
 * {@code ds.did.web.internal.networks} (the allowance, both or neither, refused at
 * start when unsound), and EDC's own {@code edc.iam.did.web.use.https}.
 * {@code edc.webdid.doh.url} is refused: this resolver replaces EDC's, and with it
 * DNS over HTTPS, which would otherwise be dropped without a word.
 */
@Extension(DidWebGuardExtension.NAME)
public class DidWebGuardExtension implements ServiceExtension {

    public static final String NAME = "ds did:web address guard";

    @Setting(description = "Host suffixes of the dataspace's own did:web hosts that may resolve to a private "
        + "address in ds.did.web.internal.networks (ADR-0029). Comma-separated; empty: public addresses only.",
        required = false)
    static final String INTERNAL_HOSTS = "ds.did.web.internal.hosts";

    @Setting(description = "The private networks (CIDR) those hosts may resolve to. Required together with "
        + "ds.did.web.internal.hosts.", required = false)
    static final String INTERNAL_NETWORKS = "ds.did.web.internal.networks";

    static final String USE_HTTPS = "edc.iam.did.web.use.https";
    static final String DNS_OVER_HTTPS = "edc.webdid.doh.url";

    @Inject
    private DidResolverRegistry registry;
    @Inject
    private OkHttpClient okHttpClient;
    @Inject
    private RetryPolicy<Response> retryPolicy;
    @Inject
    private TypeManager typeManager;

    private DidResolver resolver;
    private Consumer<DidResolver> register;

    @Override
    public String name() {
        return NAME;
    }

    @Override
    public void initialize(ServiceExtensionContext context) {
        configure(key -> context.getSetting(key, null), context.getMonitor(), okHttpClient, retryPolicy,
            typeManager.getMapper(), registry::register);
    }

    /** Validate the settings and build the resolver; registering waits for {@link #prepare()}. */
    void configure(Function<String, String> setting, Monitor monitor, OkHttpClient base,
                   RetryPolicy<Response> retry, ObjectMapper mapper, Consumer<DidResolver> register) {
        var doh = setting.apply(DNS_OVER_HTTPS);
        if (doh != null && !doh.isBlank()) {
            throw new EdcException(DNS_OVER_HTTPS + " is set, but ds's did:web address guard replaces EDC's "
                + "did:web resolver and does not resolve over DNS-over-HTTPS. Unset it.");
        }
        DidWebAddressGuard.Allowance allowance;
        try {
            allowance = DidWebAddressGuard.Allowance.parse(setting.apply(INTERNAL_HOSTS),
                setting.apply(INTERNAL_NETWORKS));
        } catch (IllegalArgumentException e) {
            throw new EdcException(e.getMessage() + " (" + INTERNAL_HOSTS + ", " + INTERNAL_NETWORKS + ")", e);
        }
        var dev = !ProductionGuard.isProduction(setting.apply(ProductionGuard.DS_ENV));
        var useHttps = !"false".equalsIgnoreCase(String.valueOf(setting.apply(USE_HTTPS)).trim());
        this.resolver = guardedResolver(base, retry, mapper, monitor, useHttps, dev, allowance);
        this.register = register;
        monitor.info(() -> "did:web address guard: " + (dev
            ? "DS_ENV=dev, private and loopback addresses admitted"
            : "only public addresses"));
        if (allowance.active()) {
            monitor.warning(() -> "did:web internal allowance active: " + allowance.describe());
        }
    }

    @Override
    public void prepare() {
        register.accept(resolver);
    }

    static DidResolver guardedResolver(OkHttpClient base, RetryPolicy<Response> retry, ObjectMapper mapper,
                                       Monitor monitor, boolean useHttps, boolean dev,
                                       DidWebAddressGuard.Allowance allowance) {
        var client = base.newBuilder().dns(new DidWebAddressGuard.GuardedDns(Dns.SYSTEM, dev, allowance)).build();
        return new WebDidResolver(new EdcHttpClientImpl(client, retry, monitor), useHttps, mapper, monitor);
    }
}
