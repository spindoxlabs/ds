package dataspaces.edc;

import okhttp3.Request;
import org.eclipse.edc.iam.oauth2.spi.client.Oauth2Client;
import org.eclipse.edc.iam.oauth2.spi.client.SharedSecretOauth2CredentialsRequest;
import org.eclipse.edc.spi.iam.TokenRepresentation;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.result.Result;

import java.time.Duration;
import java.time.Instant;

/**
 * Authenticates the EDC JVM to ds-connector with a Keycloak
 * {@code client_credentials} token, using EDC's own {@link Oauth2Client}.
 *
 * <p>This replaces the {@code X-Api-Key} the extensions used to present. That
 * value was <b>the same secret as EDC's Management API key</b>, so one leak
 * yielded contract administration <em>and</em> the data-plane signing keys
 * {@code /internal/edr-jwks} exposes <em>and</em> the subject pools
 * {@code /internal/consent/check} enumerates. It also defeated attribution:
 * every {@code /internal/*} call arrived as the same anonymous bearer of one
 * secret, so no audit trail could tell the EDC from the dataset-api.
 *
 * <p>A token identifies <em>this</em> client ({@code svc-edc}) and carries only
 * the scopes the realm grants it, so both problems go away at once.
 *
 * <p>Tokens are cached until 30 s before expiry — the same skew
 * {@code ds_auth.ServiceTokenProvider} uses on the Python side. A failed
 * refresh sends the request unauthenticated rather than throwing: the connector
 * answers 401 and the caller's own fail-closed handling applies, which keeps a
 * transient Keycloak outage from turning into an unhandled exception inside a
 * policy evaluation.
 */
public class Oauth2InternalAuth implements InternalAuth {

    private static final Duration EXPIRY_SKEW = Duration.ofSeconds(30);

    private final Oauth2Client client;
    private final String tokenUrl;
    private final String clientId;
    private final String clientSecret;
    private final Monitor monitor;

    private volatile String token;
    private volatile Instant expiresAt = Instant.EPOCH;

    public Oauth2InternalAuth(
        Oauth2Client client,
        String tokenUrl,
        String clientId,
        String clientSecret,
        Monitor monitor
    ) {
        this.client = client;
        this.tokenUrl = tokenUrl;
        this.clientId = clientId;
        this.clientSecret = clientSecret;
        this.monitor = monitor;
    }

    @Override
    public void authorize(Request.Builder builder) {
        String bearer = currentToken();
        if (bearer != null) {
            builder.header("Authorization", "Bearer " + bearer);
        }
    }

    private synchronized String currentToken() {
        if (token != null && Instant.now().isBefore(expiresAt)) {
            return token;
        }
        var request = SharedSecretOauth2CredentialsRequest.Builder.newInstance()
            .url(tokenUrl)
            .grantType("client_credentials")
            .clientId(clientId)
            .clientSecret(clientSecret)
            .build();

        Result<TokenRepresentation> result = client.requestToken(request);
        if (result.failed()) {
            monitor.warning("Oauth2InternalAuth: token request for %s failed: %s"
                .formatted(clientId, result.getFailureDetail()));
            token = null;
            expiresAt = Instant.EPOCH;
            return null;
        }

        TokenRepresentation representation = result.getContent();
        long expiresIn = representation.getExpiresIn() != null ? representation.getExpiresIn() : 300L;
        token = representation.getToken();
        expiresAt = Instant.now().plusSeconds(expiresIn).minus(EXPIRY_SKEW);
        return token;
    }
}
