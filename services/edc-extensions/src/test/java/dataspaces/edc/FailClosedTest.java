package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.Request;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.TransferProcessPolicyContext;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.model.Action;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.policy.model.Policy;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * What the policy layer does when a dependency will not answer.
 *
 * <p>Rulebook {@code CR-4}: <i>an undecidable constraint — an unreachable
 * evaluation endpoint, a missing attribute, an unbound operand — is a denial,
 * never a permission.</i> Returning true when an input is missing or a call
 * fails is the defect class this codebase has the most of. Two paths here contradicted it, each with a
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

    private static ContractAgreement agreement(String assetId) {
        return ContractAgreement.Builder.newInstance()
            .id(AGREEMENT)
            .providerId("did:web:rec.dataspaces.localhost")
            .consumerId("did:web:third-party.dataspaces.localhost")
            .assetId(assetId)
            .policy(Policy.Builder.newInstance().build())
            .build();
    }

    private static PolicyMonitorContext monitorContext() {
        return new PolicyMonitorContext(Instant.now(), agreement(DATASET));
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

    private static TransferProcessPolicyContext transferContext() {
        return new TransferProcessPolicyContext(
            new ParticipantAgent("did:web:third-party.dataspaces.localhost", Map.of(), Map.of()),
            agreement(DATASET),
            Instant.now());
    }

    private static AgreementConsentFunction<PolicyMonitorContext> inFlight(String... answers) {
        return AgreementConsentFunction.inFlight(
            new ConsentApi(new ScriptedConnector(answers)), new NoopMonitor());
    }

    private static boolean evaluate(AgreementConsentFunction<PolicyMonitorContext> function) {
        return function.evaluate(Operator.EQ, "granted", gatedPermission(), monitorContext());
    }

    // ── EDC-01: bounded tolerance, then deny (policy.monitor) ────────────────

    @Tag("rule:A-11")
    @Test
    void aSingleUnanswerablePassDoesNotTerminate() {
        // Failing closed on one blip would let a momentary outage destroy live
        // agreements, and buys nothing while it lasts — the dataset-api PEP asks
        // the same question per query and fails closed itself.
        assertTrue(evaluate(inFlight((String) null)));
    }

    @Tag("rule:A-11") @Tag("rule:A-12")
    @Test
    void sustainedSilenceTerminates() {
        // The half that was missing. "The other enforcement point will catch it"
        // stops being a reason once the outage is the steady state: a consent
        // revoked during it would never be seen here at all.
        var function = inFlight((String) null);
        assertTrue(evaluate(function));
        assertTrue(evaluate(function));
        assertFalse(evaluate(function), "third consecutive unanswerable pass must terminate");
    }

    @Tag("rule:A-11")
    @Test
    void aDefiniteAnswerClearsTheStreak() {
        // Otherwise a connector that flaps would accumulate failures across
        // unrelated healthy passes and terminate a transfer that was never in
        // doubt.
        var function = inFlight(
            null,
            "{\"consent_active\": false, \"subject_ids\": [\"s\"]}",
            null,
            null);

        assertTrue(evaluate(function));   // 1 failure
        assertTrue(evaluate(function));   // answered — streak reset
        assertTrue(evaluate(function));   // 1 failure again
        assertTrue(evaluate(function));   // 2 failures — still under the threshold
    }

    @Tag("rule:A-11") @Tag("rule:A-12")
    @Test
    void aDefiniteNoStillTerminatesImmediately() {
        // The tolerance is for *silence*, never for a denial. A revoked consent
        // must stop the transfer on the very next pass.
        assertFalse(evaluate(inFlight("{\"consent_active\": false, \"subject_ids\": []}")));
    }

    @Tag("rule:A-11") @Tag("rule:A-12")
    @Test
    void anAgreementWithNoAssetTerminates() {
        var function = inFlight("{\"consent_active\": true, \"subject_ids\": [\"s\"]}");
        ContractAgreement noAsset = ContractAgreement.Builder.newInstance()
            .id(AGREEMENT).providerId("p").consumerId("c").assetId("")
            .policy(Policy.Builder.newInstance().build()).build();
        assertFalse(function.evaluate(
            Operator.EQ, "granted", gatedPermission(), new PolicyMonitorContext(Instant.now(), noAsset)));
    }

    // ── EDC-16: the pre-start gate (transfer.process) ────────────────────────

    @Tag("rule:A-11")
    @Test
    void thePreStartGateDeniesOnTheFirstUnanswerableCheck() {
        // No tolerance here, and the asymmetry is the point: refusing to start a
        // transfer costs the consumer a retry, while terminating a running one
        // destroys an agreement. Nothing is running yet.
        var function = AgreementConsentFunction.<TransferProcessPolicyContext>preStart(
            new ConsentApi(new ScriptedConnector((String) null)), new NoopMonitor());
        assertFalse(function.evaluate(Operator.EQ, "granted", gatedPermission(), transferContext()));
    }

    @Tag("rule:A-12")
    @Test
    void thePreStartGateAllowsWhenAnybodyConsents() {
        var function = AgreementConsentFunction.<TransferProcessPolicyContext>preStart(
            new ConsentApi(new ScriptedConnector("{\"consent_active\": true, \"subject_ids\": [\"s\"]}")),
            new NoopMonitor());
        assertTrue(function.evaluate(Operator.EQ, "granted", gatedPermission(), transferContext()));
    }

    @Tag("rule:A-12")
    @Test
    void thePreStartGateDeniesWhenConsentWasWithdrawnAfterSigning() {
        // The window EDC-16 is about: the agreement is signed and valid, and the
        // subject has since withdrawn. Nothing looked here before, so the EDR was
        // issued and the transfer started; only the first policy-monitor pass —
        // which runs *after* the transfer starts — would have noticed.
        var function = AgreementConsentFunction.<TransferProcessPolicyContext>preStart(
            new ConsentApi(new ScriptedConnector("{\"consent_active\": false, \"subject_ids\": []}")),
            new NoopMonitor());
        assertFalse(function.evaluate(Operator.EQ, "granted", gatedPermission(), transferContext()));
    }

    // ── EDC-08: the operand has to be read before it can be compared ─────────

    @Tag("rule:A-11")
    @Test
    void anExpandedOperandIsUnwrappedRatherThanStringified() {
        // A policy that reached the store through EDC's JSON-LD expansion carries
        // "granted" as {"@value": "granted"}; toString() yielded "\"granted\"",
        // quotes included, so the status comparison failed and the function
        // denied — on precisely the policies that took the expanded path, and
        // with nothing in the log to say why.
        var function = inFlight("{\"consent_active\": true, \"subject_ids\": [\"s\"]}");
        assertTrue(function.evaluate(
            Operator.EQ, Map.of("@value", "granted"), gatedPermission(), monitorContext()));
    }

    @Tag("rule:A-11")
    @Test
    void anUnreadableOperandDenies() {
        var function = inFlight("{\"consent_active\": true, \"subject_ids\": [\"s\"]}");
        assertFalse(function.evaluate(
            Operator.EQ, List.of("granted", "active"), gatedPermission(), monitorContext()),
            "an operand that does not reduce to one scalar cannot be compared — deny");
    }

    // ── EDC-04: never send unauthenticated ───────────────────────────────────

    @Tag("rule:A-11")
    @Test
    void authorizeReportsWhetherItCouldAuthenticate() {
        // It used to return void having added no header, so the caller could not
        // tell. `ConnectorClient` now declines to send at all.
        InternalAuth refusing = builder -> false;
        InternalAuth granting = builder -> true;
        assertFalse(refusing.authorize(new Request.Builder().url("http://ds/x")));
        assertTrue(granting.authorize(new Request.Builder().url("http://ds/x")));
    }

    @Tag("rule:A-11")
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
