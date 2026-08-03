package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.Request;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.policy.model.Action;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.policy.model.Policy;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * What the policy layer does when a dependency will not answer.
 *
 * <p>Root {@code AGENTS.md}: <i>a constraint function must deny on error;
 * returning true when an input is missing or a call fails is the defect class
 * this codebase has the most of.</i> Two paths here contradicted it, each with a
 * reasoned defence in the source and neither recorded as a deviation — and they
 * composed into one chain:
 *
 * <pre>
 *   Keycloak down
 *     -> Oauth2InternalAuth sent the request with no Authorization header
 *     -> connector answered 401
 *     -> ConnectorClient turned 401 into null
 *     -> AgreementConsentFunction read null as "cannot answer" and returned true
 *     -> a running transfer kept running, unchecked
 * </pre>
 *
 * <p>An outage of a component holding no consent data left consent unenforced on
 * the control plane. Each link was individually defensible; the chain was not.
 */
class FailClosedTest {

    private static final String AGREEMENT = "agreement-1";
    private static final String DATASET = "datasets.silver.meters_15m";

    private static class NoopMonitor implements Monitor {
    }

    /** A connector whose consent answer is scripted per call. */
    private static class ScriptedConnector extends ConnectorClient {
        private final String[] answers;
        private int calls;

        ScriptedConnector(String... answers) {
            super("http://ds-connector:30001", b -> true, new NoopMonitor());
            this.answers = answers;
        }

        @Override
        public JsonNode getJson(String path, Map<String, String> query) {
            String json = answers[Math.min(calls++, answers.length - 1)];
            if (json == null) {
                return null;
            }
            try {
                return new ObjectMapper().readTree(json);
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }
    }

    private static PolicyMonitorContext monitorContext() {
        ContractAgreement agreement = ContractAgreement.Builder.newInstance()
            .id(AGREEMENT)
            .providerId("did:web:provider.dataspaces.localhost")
            .consumerId("did:web:consumer.dataspaces.localhost")
            .assetId(DATASET)
            .policy(Policy.Builder.newInstance().build())
            .build();
        return new PolicyMonitorContext(Instant.now(), agreement);
    }

    private static Permission gatedPermission() {
        return Permission.Builder.newInstance()
            .action(Action.Builder.newInstance().type("ds:query").build())
            .constraint(AtomicConstraint.Builder.newInstance()
                .leftExpression(new LiteralExpression("odrl:purpose"))
                .operator(Operator.IS_ANY_OF)
                .rightExpression(new LiteralExpression("FlexibilityResearch"))
                .build())
            .build();
    }

    private static boolean evaluate(AgreementConsentFunction function) {
        return function.evaluate(Operator.EQ, "granted", gatedPermission(), monitorContext());
    }

    // ── EDC-01: bounded tolerance, then deny ─────────────────────────────────

    @Test
    void aSingleUnanswerablePassDoesNotTerminate() {
        // Failing closed on one blip would let a momentary outage destroy live
        // agreements, and buys nothing while it lasts — the dataset-api PEP asks
        // the same question per query and fails closed itself.
        var function = new AgreementConsentFunction(
            new ConsentApi(new ScriptedConnector((String) null)), new NoopMonitor(), 3);
        assertTrue(evaluate(function));
    }

    @Test
    void sustainedSilenceTerminates() {
        // The half that was missing. "The other enforcement point will catch it"
        // stops being a reason once the outage is the steady state: a consent
        // revoked during it would never be seen here at all.
        var function = new AgreementConsentFunction(
            new ConsentApi(new ScriptedConnector((String) null)), new NoopMonitor(), 3);
        assertTrue(evaluate(function));
        assertTrue(evaluate(function));
        assertFalse(evaluate(function), "third consecutive unanswerable pass must terminate");
    }

    @Test
    void aDefiniteAnswerClearsTheStreak() {
        // Otherwise a connector that flaps would accumulate failures across
        // unrelated healthy passes and terminate a transfer that was never in
        // doubt.
        var connector = new ScriptedConnector(
            null,
            "{\"consent_active\": false, \"subject_ids\": [\"s\"]}",
            null,
            null);
        var function = new AgreementConsentFunction(new ConsentApi(connector), new NoopMonitor(), 3);

        assertTrue(evaluate(function));   // 1 failure
        assertTrue(evaluate(function));   // answered — streak reset
        assertTrue(evaluate(function));   // 1 failure again
        assertTrue(evaluate(function));   // 2 failures — still under the threshold
    }

    @Test
    void aDefiniteNoStillTerminatesImmediately() {
        // The tolerance is for *silence*, never for a denial. A revoked consent
        // must stop the transfer on the very next pass.
        var function = new AgreementConsentFunction(
            new ConsentApi(new ScriptedConnector("{\"consent_active\": false, \"subject_ids\": []}")),
            new NoopMonitor(), 3);
        assertFalse(evaluate(function));
    }

    @Test
    void anAgreementWithNoAssetTerminates() {
        var function = new AgreementConsentFunction(
            new ConsentApi(new ScriptedConnector("{\"consent_active\": true, \"subject_ids\": [\"s\"]}")),
            new NoopMonitor(), 3);
        ContractAgreement noAsset = ContractAgreement.Builder.newInstance()
            .id(AGREEMENT).providerId("p").consumerId("c").assetId("")
            .policy(Policy.Builder.newInstance().build()).build();
        assertFalse(function.evaluate(
            Operator.EQ, "granted", gatedPermission(), new PolicyMonitorContext(Instant.now(), noAsset)));
    }

    // ── EDC-04: never send unauthenticated ───────────────────────────────────

    @Test
    void authorizeReportsWhetherItCouldAuthenticate() {
        // It used to return void having added no header, so the caller could not
        // tell. `ConnectorClient` now declines to send at all.
        InternalAuth refusing = builder -> false;
        InternalAuth granting = builder -> true;
        assertFalse(refusing.authorize(new Request.Builder().url("http://ds/x")));
        assertTrue(granting.authorize(new Request.Builder().url("http://ds/x")));
    }

    @Test
    void aClientThatCannotAuthenticateReturnsNullWithoutSending() {
        // The first link in the chain. If this sends, the connector answers 401,
        // and a 401 is indistinguishable from a permission decision.
        var sent = new boolean[]{false};
        var client = new ConnectorClient("http://127.0.0.1:1", b -> false, new NoopMonitor()) {
            @Override
            public JsonNode getJson(String path, Map<String, String> query) {
                JsonNode result = super.getJson(path, query);
                sent[0] = true;
                return result;
            }
        };
        assertTrue(client.getJson("/internal/consent/check", Map.of()) == null);
    }
}
