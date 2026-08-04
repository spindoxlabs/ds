package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import okhttp3.Request;
import org.eclipse.edc.iam.oauth2.spi.client.Oauth2Client;
import org.eclipse.edc.iam.oauth2.spi.client.Oauth2CredentialsRequest;
import org.eclipse.edc.spi.iam.TokenRepresentation;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.result.Result;
import org.junit.jupiter.api.Test;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The transport, and the credential it will not send without.
 *
 * <p>Both were the first two links in the chain {@link FailClosedTest} describes.
 * The contract worth pinning is narrow and load-bearing: {@code null} means
 * denied, a transport failure is retried, a non-2xx answer is not, and a request
 * that cannot be signed is never sent.
 */
class ConnectorClientTest {

    private static class NoopMonitor implements Monitor {
    }

    // ── the retry schedule ───────────────────────────────────────────────────

    @Test
    void aTransportFailureIsRetriedAndThenGivesUp() {
        // Port 1 refuses immediately, so this exercises the whole schedule
        // without a server. Four attempts: the initial one plus BACKOFF_MS.
        var attempts = new AtomicInteger();
        var client = new ConnectorClient("http://127.0.0.1:1", b -> {
            attempts.incrementAndGet();
            return true;
        }, new NoopMonitor());

        assertNull(client.getJson("/internal/consent/check", Map.of()),
            "an unreachable connector must read as denied, never as unknown-so-allow");
        assertEquals(4, attempts.get(), "one attempt plus the three backoff steps");
    }

    @Test
    void aRequestThatCannotBeSignedIsNotSent() {
        // The first link in the chain. Sending it bare earns a 401, and a 401 is
        // indistinguishable from a permission decision one layer up.
        var attempts = new AtomicInteger();
        var client = new ConnectorClient("http://127.0.0.1:1", b -> {
            attempts.incrementAndGet();
            return false;
        }, new NoopMonitor());

        assertNull(client.getJson("/internal/consent/check", Map.of()));
        // Retried like any transient — a brief Keycloak outage is what the
        // backoff exists for — and then given up on rather than sent unsigned.
        assertEquals(4, attempts.get());
    }

    @Test
    void postingAlsoRefusesToSendUnsigned() {
        var client = new ConnectorClient("http://127.0.0.1:1", b -> false, new NoopMonitor());
        assertNull(client.postJsonForResult("/internal/consent/asks", Map.of("a", 1)));
        assertFalse(client.postJson("/internal/consent/asks", Map.of("a", 1)));
    }

    @Test
    void aBodyThatCannotBeSerialisedFails() {
        var client = new ConnectorClient("http://127.0.0.1:1", b -> true, new NoopMonitor());
        assertNull(client.postJsonForResult("/internal/consent/asks", new Object() {
            @SuppressWarnings("unused")
            public Object getSelf() {
                throw new UnsupportedOperationException("not serialisable");
            }
        }));
    }

    // ── the credential ───────────────────────────────────────────────────────

    /** An Oauth2Client whose answer is scripted, counting refreshes. */
    private static class ScriptedOauth2Client implements Oauth2Client {
        private final boolean succeeds;
        private final long expiresIn;
        final AtomicInteger requests = new AtomicInteger();

        ScriptedOauth2Client(boolean succeeds, long expiresIn) {
            this.succeeds = succeeds;
            this.expiresIn = expiresIn;
        }

        @Override
        public Result<TokenRepresentation> requestToken(Oauth2CredentialsRequest request) {
            int n = requests.incrementAndGet();
            if (!succeeds) {
                return Result.failure("keycloak is down");
            }
            return Result.success(TokenRepresentation.Builder.newInstance()
                .token("token-" + n)
                .expiresIn(expiresIn)
                .build());
        }
    }

    private static Oauth2InternalAuth auth(Oauth2Client client) {
        return new Oauth2InternalAuth(
            client, "http://172.17.0.1:9080/token", "svc-edc", "svc-edc", new NoopMonitor());
    }

    @Test
    void aFailedTokenRequestRefusesRatherThanSendingBare() {
        var client = new ScriptedOauth2Client(false, 300L);
        var builder = new Request.Builder().url("http://ds-connector:30001/internal/consent/check");

        assertFalse(auth(client).authorize(builder));
        assertNull(builder.build().header("Authorization"),
            "no header may be added when the token could not be obtained");
    }

    @Test
    void aTokenIsAttachedAsABearer() {
        var builder = new Request.Builder().url("http://ds-connector:30001/internal/consent/check");

        assertTrue(auth(new ScriptedOauth2Client(true, 300L)).authorize(builder));
        assertEquals("Bearer token-1", builder.build().header("Authorization"));
    }

    @Test
    void aLiveTokenIsReusedRatherThanRefetched() {
        var client = new ScriptedOauth2Client(true, 300L);
        var auth = auth(client);

        auth.authorize(new Request.Builder().url("http://ds/x"));
        auth.authorize(new Request.Builder().url("http://ds/x"));
        auth.authorize(new Request.Builder().url("http://ds/x"));

        assertEquals(1, client.requests.get(), "the token is cached until 30 s before expiry");
    }

    @Test
    void aTokenInsideTheExpirySkewIsRefreshed() {
        // 30 s of skew, so anything expiring sooner than that is already stale.
        // Getting this backwards means presenting a token that expires in flight,
        // which reads as a permission failure at the other end.
        var client = new ScriptedOauth2Client(true, 10L);
        var auth = auth(client);

        var first = new Request.Builder().url("http://ds/x");
        var second = new Request.Builder().url("http://ds/x");
        auth.authorize(first);
        auth.authorize(second);

        assertEquals(2, client.requests.get());
        assertEquals("Bearer token-2", second.build().header("Authorization"));
    }

    // ── the fail-closed contract, stated once ────────────────────────────────

    @Test
    void consentApiTurnsAnUnanswerableCallIntoNull() {
        // ConsentApi.check documents that null means denied. Every caller keys
        // off that, so it is worth an assertion of its own rather than being
        // implied by the functions above it.
        var client = new ConnectorClient("http://127.0.0.1:1", b -> true, new NoopMonitor());
        JsonNode nothing = client.getJson("/internal/consent/check", Map.of());
        assertNull(nothing);
        assertNull(new ConsentApi(client).check("", "d", "c", java.util.List.of()));
    }
}
