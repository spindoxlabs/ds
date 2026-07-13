package dataspaces.edc;

import org.eclipse.edc.connector.dataplane.spi.Endpoint;
import org.eclipse.edc.connector.dataplane.spi.iam.PublicEndpointGeneratorService;
import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.spi.types.domain.DataAddress;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.StringJoiner;

/**
 * Registers the demo HttpData endpoint generator used by consumer-pull EDRs.
 */
@Extension("Dataspaces HttpData EDR Endpoint")
public class HttpDataEndpointExtension implements ServiceExtension {

    @Inject
    private PublicEndpointGeneratorService endpointGenerator;

    private String publicBaseUrl;

    @Override
    public void initialize(ServiceExtensionContext context) {
        publicBaseUrl = context.getSetting("ds.edr.endpoint.public.baseurl", "");
        endpointGenerator.addGeneratorFunction("HttpData", this::endpointFor);
        context.getMonitor().info("Dataspaces HttpData EDR endpoint generator registered");
    }

    private Endpoint endpointFor(DataAddress sourceAddress) {
        String endpoint = rewriteBaseUrl(sourceAddress.getStringProperty("baseUrl"));
        StringJoiner query = new StringJoiner("&");
        for (Map.Entry<String, Object> entry : sourceAddress.getProperties().entrySet()) {
            if (entry.getKey().startsWith("queryParam:") && entry.getValue() != null) {
                query.add(encode(entry.getKey().substring("queryParam:".length())) + "=" + encode(entry.getValue().toString()));
            }
        }
        String queryString = query.toString();
        if (!queryString.isBlank()) {
            endpoint = endpoint + (endpoint.contains("?") ? "&" : "?") + queryString;
        }
        return Endpoint.url(endpoint);
    }

    private String rewriteBaseUrl(String baseUrl) {
        if (publicBaseUrl == null || publicBaseUrl.isBlank()) {
            return baseUrl;
        }
        URI source = URI.create(baseUrl);
        String path = source.getRawPath() == null ? "" : source.getRawPath();
        String query = source.getRawQuery() == null ? "" : "?" + source.getRawQuery();
        return publicBaseUrl.replaceAll("/+$", "") + path + query;
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }
}
