package dataspaces.edc;

import okhttp3.Request;

/**
 * How the EDC JVM authenticates to ds-connector's {@code /internal/*} API.
 *
 * <p>Kept as a single seam so the credential lives in one place rather than in
 * every constraint function. The only implementation is
 * {@link Oauth2InternalAuth}: a Keycloak {@code client_credentials} token
 * identifying this connector as {@code svc-edc}.
 *
 * <p>It used to be a static {@code X-Api-Key} equal to {@code EDC_API_KEY} —
 * which is also EDC's Management API key, so one leaked value yielded contract
 * administration, the data-plane signing keys behind {@code /internal/edr-jwks}
 * and the subject pools behind {@code /internal/consent/check} together, with no
 * audit trail distinguishing this caller from the dataset-api.
 */
@FunctionalInterface
public interface InternalAuth {

    /**
     * Add this connector's credential to an outgoing request.
     *
     * @return {@code false} when no credential could be obtained, in which case
     *         the caller must <b>not</b> send the request. It used to be
     *         {@code void}, and the implementation returned normally having
     *         added no header — so a Keycloak outage sent an anonymous request
     *         and the connector answered 401, which is indistinguishable from a
     *         permission problem and which
     *         {@link AgreementConsentFunction} read as "cannot answer".
     */
    boolean authorize(Request.Builder builder);
}
