package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.ws.rs.container.ContainerRequestContext;
import jakarta.ws.rs.container.ContainerRequestFilter;
import jakarta.ws.rs.core.HttpHeaders;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import org.eclipse.edc.spi.monitor.Monitor;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Requires the management audience in the bearer token of every management call.
 *
 * <p>EDC 0.18.0's management OAuth2 filter ({@code ManagementApiOauth2AuthenticationExtension})
 * validates a fixed rule list — issuer, not-before, expiry — and then the
 * {@code sub} and {@code scope} the authorization extension reads. It has no
 * audience rule and no setting for one. This filter adds it: a call whose token
 * does not name {@code ds.management.audience} in {@code aud} is refused
 * {@code 401}.
 *
 * <p>The audience comes from the optional scope {@code edc.management}
 * ({@code services/keycloak/clients.yaml}), which an organisation's connector
 * requests together with its management-API scopes only for its EDC calls
 * ({@code ds_auth.EDC_TOKEN_SCOPE}). Every other token the organisation's client
 * mints carries neither, so each token is good only where it is sent.
 *
 * <p>The claims are read here without verifying the signature, on purpose: EDC's
 * filter on the same context verifies it, and a request has to pass both. This
 * one never admits anything on its own — it can only refuse.
 */
public class ManagementAudienceFilter implements ContainerRequestFilter {

    private static final ObjectMapper JSON = new ObjectMapper();

    private final String audience;
    private final Monitor monitor;

    public ManagementAudienceFilter(String audience, Monitor monitor) {
        if (audience == null || audience.isBlank()) {
            throw new IllegalArgumentException("the management audience is required");
        }
        this.audience = audience;
        this.monitor = monitor;
    }

    @Override
    public void filter(ContainerRequestContext request) {
        String reason = refusal(request.getHeaderString(HttpHeaders.AUTHORIZATION), audience);
        if (reason != null) {
            monitor.warning("Management API call refused: %s".formatted(reason));
            request.abortWith(Response.status(Response.Status.UNAUTHORIZED)
                .type(MediaType.APPLICATION_JSON_TYPE)
                .entity("[{\"message\":\"token not issued for the management API\",\"type\":\"AuthenticationFailed\"}]")
                .build());
        }
    }

    /**
     * Why the call must be refused, or {@code null} when the token names
     * {@code audience}. A missing or unreadable bearer is refused too: EDC's own
     * filter would refuse it as well, and this one must not be the weaker of two.
     */
    static String refusal(String authorization, String audience) {
        if (authorization == null || !authorization.regionMatches(true, 0, "Bearer ", 0, 7)) {
            return "no bearer token";
        }
        String[] parts = authorization.substring(7).trim().split("\\.");
        if (parts.length != 3) {
            return "not a JWT";
        }
        JsonNode aud;
        try {
            byte[] payload = Base64.getUrlDecoder().decode(parts[1]);
            aud = JSON.readTree(new String(payload, StandardCharsets.UTF_8)).get("aud");
        } catch (Exception e) {
            return "unreadable token claims";
        }
        if (aud == null || aud.isNull()) {
            return "token carries no audience";
        }
        if (aud.isTextual() && audience.equals(aud.asText())) {
            return null;
        }
        if (aud.isArray()) {
            for (JsonNode entry : aud) {
                if (entry.isTextual() && audience.equals(entry.asText())) {
                    return null;
                }
            }
        }
        return "token audience does not include " + audience;
    }
}
