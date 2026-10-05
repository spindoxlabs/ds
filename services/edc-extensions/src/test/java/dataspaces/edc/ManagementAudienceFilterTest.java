package dataspaces.edc;

import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The management context requires {@code ds.management.audience} in the token's
 * {@code aud} — the audience only the connector's EDC token carries.
 */
class ManagementAudienceFilterTest {

    private static final String AUDIENCE = "svc-ds-edc";

    private static String bearer(String payloadJson) {
        Base64.Encoder enc = Base64.getUrlEncoder().withoutPadding();
        String header = enc.encodeToString("{\"alg\":\"RS256\"}".getBytes(StandardCharsets.UTF_8));
        String payload = enc.encodeToString(payloadJson.getBytes(StandardCharsets.UTF_8));
        return "Bearer " + header + "." + payload + ".c2lnbmF0dXJl";
    }

    @Test
    void anEdcTokenIsAdmitted() {
        assertNull(ManagementAudienceFilter.refusal(
            bearer("{\"aud\":[\"svc-ds-identity-registry\",\"svc-ds-edc\"],\"sub\":\"did:web:a\"}"), AUDIENCE));
        assertNull(ManagementAudienceFilter.refusal(bearer("{\"aud\":\"svc-ds-edc\"}"), AUDIENCE));
    }

    @Test
    void aTokenForOtherServicesIsRefused() {
        // The organisation client's ordinary token: ds services' audiences, not EDC's.
        String reason = ManagementAudienceFilter.refusal(bearer(
            "{\"aud\":[\"svc-ds-identity-registry\",\"svc-ds-provenance\",\"svc-ds-connector\"]}"), AUDIENCE);
        assertNotNull(reason);
        assertTrue(reason.contains(AUDIENCE));
    }

    @Test
    void noAudienceIsRefused() {
        assertNotNull(ManagementAudienceFilter.refusal(bearer("{\"sub\":\"did:web:a\"}"), AUDIENCE));
        assertNotNull(ManagementAudienceFilter.refusal(bearer("{\"aud\":null}"), AUDIENCE));
    }

    @Test
    void aMissingOrMalformedBearerIsRefused() {
        assertNotNull(ManagementAudienceFilter.refusal(null, AUDIENCE));
        assertNotNull(ManagementAudienceFilter.refusal("Basic Zm9vOmJhcg==", AUDIENCE));
        assertNotNull(ManagementAudienceFilter.refusal("Bearer not-a-jwt", AUDIENCE));
        assertNotNull(ManagementAudienceFilter.refusal("Bearer a.!!!.c", AUDIENCE));
    }

    @Test
    void anAudienceThatOnlyContainsTheValueIsRefused() {
        assertNotNull(ManagementAudienceFilter.refusal(bearer("{\"aud\":\"svc-ds-edc-other\"}"), AUDIENCE));
        assertNotNull(ManagementAudienceFilter.refusal(bearer("{\"aud\":[\"x svc-ds-edc\"]}"), AUDIENCE));
    }

    @Test
    void theFilterRefusesToExistWithoutAnAudience() {
        Monitor monitor = new Monitor() { };
        assertThrows(IllegalArgumentException.class, () -> new ManagementAudienceFilter("", monitor));
        assertThrows(IllegalArgumentException.class, () -> new ManagementAudienceFilter(null, monitor));
    }

    @Test
    void theRuntimeRefusesToBootWithoutTheSetting() {
        assertThrows(EdcException.class,
            () -> DataspacesExtension.managementAudience(context(Map.of())));
        // An unresolved placeholder in the properties file counts as absent.
        assertThrows(EdcException.class,
            () -> DataspacesExtension.managementAudience(
                context(Map.of("ds.management.audience", "${DS_MANAGEMENT_AUDIENCE}"))));
        assertEquals(AUDIENCE, DataspacesExtension.managementAudience(
            context(Map.of("ds.management.audience", AUDIENCE))));
    }

    private static ServiceExtensionContext context(Map<String, String> settings) {
        return (ServiceExtensionContext) Proxy.newProxyInstance(
            ServiceExtensionContext.class.getClassLoader(),
            new Class<?>[]{ServiceExtensionContext.class},
            (proxy, method, args) -> {
                if (method.getName().equals("getSetting") && args != null && args.length == 2) {
                    return settings.getOrDefault((String) args[0], (String) args[1]);
                }
                throw new UnsupportedOperationException(method.getName());
            });
    }
}
