package dataspaces.edc;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiation;
import org.eclipse.edc.connector.controlplane.contract.spi.types.negotiation.ContractNegotiationStates;
import org.eclipse.edc.connector.controlplane.contract.spi.types.offer.ContractOffer;
import org.eclipse.edc.policy.model.Action;
import org.eclipse.edc.policy.model.AtomicConstraint;
import org.eclipse.edc.policy.model.LiteralExpression;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.policy.model.Policy;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * What parks a negotiation, and — more importantly — what does not.
 *
 * <p>The guard decides nothing about access. Returning {@code true} removes the
 * negotiation from the state machine until something clears {@code pending};
 * returning {@code false} means only that <em>parking would not help</em>, and
 * the denial is {@link NegotiationConsentValidator}'s.
 *
 * <p>Both halves read as safe in isolation, which is how the pair survived with
 * the guard deferring denial to a constraint function that never denied. These
 * tests pin the guard's half so the next reader can see where the boundary is.
 */
class ConsentPendingGuardTest {

    private static final String DATASET = "datasets.silver.meters_15m";
    private static final String CONSUMER = "did:web:third-party.dataspaces.localhost";

    private static class NoopMonitor implements Monitor {
    }

    /** Records what was asked and answers from a script. */
    private static class ScriptedConnector extends ConnectorClient {
        private final String checkAnswer;
        private final String askAnswer;
        final List<String> posted = new ArrayList<>();
        int checks;

        ScriptedConnector(String checkAnswer, String askAnswer) {
            super("http://ds-connector:30001", b -> true, new NoopMonitor());
            this.checkAnswer = checkAnswer;
            this.askAnswer = askAnswer;
        }

        @Override
        public JsonNode getJson(String path, Map<String, String> query) {
            checks++;
            return parse(checkAnswer);
        }

        @Override
        public JsonNode postJsonForResult(String path, Object body) {
            posted.add(path);
            return parse(askAnswer);
        }

        private static JsonNode parse(String json) {
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

    private static ConsentPendingGuard guard(ScriptedConnector connector) {
        return new ConsentPendingGuard(
            new ConsentApi(connector), new ConsentAskApi(connector), 60L, new NoopMonitor());
    }

    private static ContractNegotiation negotiation(
        ContractNegotiation.Type type, ContractNegotiationStates state, Policy policy
    ) {
        var builder = ContractNegotiation.Builder.newInstance()
            .id("negotiation-1")
            .counterPartyId(CONSUMER)
            .counterPartyAddress("https://third-party.dataspaces.localhost/api/dsp")
            .protocol("dataspace-protocol-http")
            .type(type)
            .state(state.code());
        if (policy != null) {
            builder.contractOffer(ContractOffer.Builder.newInstance()
                .id("offer-1")
                .assetId(DATASET)
                .policy(policy)
                .build());
        }
        return builder.build();
    }

    private static ContractNegotiation gatedProviderRequest() {
        return negotiation(ContractNegotiation.Type.PROVIDER, ContractNegotiationStates.REQUESTED, gatedPolicy());
    }

    private static Policy gatedPolicy() {
        return Policy.Builder.newInstance()
            .permission(Permission.Builder.newInstance()
                .action(Action.Builder.newInstance().type("odrl:use").build())
                .constraint(AtomicConstraint.Builder.newInstance()
                    .leftExpression(new LiteralExpression("https://w3id.org/dsp/policy/ConsentStatus"))
                    .operator(Operator.EQ)
                    .rightExpression(new LiteralExpression("active"))
                    .build())
                .constraint(AtomicConstraint.Builder.newInstance()
                    .leftExpression(new LiteralExpression("odrl:purpose"))
                    .operator(Operator.IS_ANY_OF)
                    .rightExpression(new LiteralExpression(
                        List.of("https://w3id.org/dsp/policy/purpose/FlexibilityResearch")))
                    .build())
                .build())
            .build();
    }

    private static Policy ungatedPolicy() {
        return Policy.Builder.newInstance()
            .permission(Permission.Builder.newInstance()
                .action(Action.Builder.newInstance().type("odrl:use").build())
                .build())
            .build();
    }

    // ── the one case that parks ──────────────────────────────────────────────

    @Test
    void parksWhenNobodyConsentsYetAndSomebodyCanBeAsked() {
        var connector = new ScriptedConnector(
            "{\"consent_active\": false, \"subject_ids\": [], \"should_ask\": true}",
            "{\"asked\": true, \"reason\": \"awaiting_consent\", \"request_ids\": [\"r-1\"]}");

        assertTrue(guard(connector).test(gatedProviderRequest()));
        assertEquals(List.of("/internal/consent/asks"), connector.posted);
    }

    // ── everything that does not ─────────────────────────────────────────────

    @Test
    void doesNotParkWhenConsentAlreadyCovers() {
        var connector = new ScriptedConnector(
            "{\"consent_active\": true, \"subject_ids\": [\"s-1\"], \"should_ask\": true}", null);

        assertFalse(guard(connector).test(gatedProviderRequest()));
        assertTrue(connector.posted.isEmpty(), "nobody should be asked when consent already covers");
    }

    @Test
    void doesNotParkAProcessorTheOfferAlreadyCovers() {
        // `should_ask: false` is a disclosure, not a question. Parking would wait
        // on a decision no one is going to be asked to make.
        var connector = new ScriptedConnector(
            "{\"consent_active\": false, \"subject_ids\": [], \"should_ask\": false}", null);

        assertFalse(guard(connector).test(gatedProviderRequest()));
        assertTrue(connector.posted.isEmpty());
    }

    @Test
    void doesNotParkWhenThereIsNobodyToAsk() {
        var connector = new ScriptedConnector(
            "{\"consent_active\": false, \"subject_ids\": [], \"should_ask\": true}",
            "{\"asked\": false, \"reason\": \"no_subjects\", \"request_ids\": []}");

        assertFalse(guard(connector).test(gatedProviderRequest()));
    }

    @Test
    void doesNotParkOnAnUnanswerableCheck() {
        // Parking would strand the negotiation on an outage rather than on a
        // person. The denial is the validator's, and it fails closed on the same
        // outage.
        var connector = new ScriptedConnector(null, null);
        assertFalse(guard(connector).test(gatedProviderRequest()));
    }

    @Test
    void doesNotParkAConsumerNegotiation() {
        // One guard instance is handed to both managers. Only a provider
        // negotiation can be waiting on a data subject.
        var connector = new ScriptedConnector(
            "{\"consent_active\": false, \"subject_ids\": [], \"should_ask\": true}",
            "{\"asked\": true, \"reason\": \"awaiting_consent\", \"request_ids\": [\"r-1\"]}");

        assertFalse(guard(connector).test(negotiation(
            ContractNegotiation.Type.CONSUMER, ContractNegotiationStates.REQUESTED, gatedPolicy())));
        assertEquals(0, connector.checks, "the connector must not be asked at all");
    }

    @Test
    void doesNotParkANegotiationPastRequested() {
        var connector = new ScriptedConnector(
            "{\"consent_active\": false, \"subject_ids\": [], \"should_ask\": true}", null);

        assertFalse(guard(connector).test(negotiation(
            ContractNegotiation.Type.PROVIDER, ContractNegotiationStates.AGREEING, gatedPolicy())));
        assertEquals(0, connector.checks);
    }

    @Test
    void doesNotParkAnUngatedDataset() {
        // The whole cost argument depends on this: the guard runs on every new
        // provider negotiation, and most datasets are not consent-gated.
        var connector = new ScriptedConnector(
            "{\"consent_active\": false, \"subject_ids\": [], \"should_ask\": true}", null);

        assertFalse(guard(connector).test(negotiation(
            ContractNegotiation.Type.PROVIDER, ContractNegotiationStates.REQUESTED, ungatedPolicy())));
        assertEquals(0, connector.checks, "an ungated policy must not reach the connector");
    }

    @Test
    void doesNotParkANegotiationWithNoOffer() {
        var connector = new ScriptedConnector(null, null);
        assertFalse(guard(connector).test(negotiation(
            ContractNegotiation.Type.PROVIDER, ContractNegotiationStates.REQUESTED, null)));
    }

    // ── the cache ────────────────────────────────────────────────────────────

    @Test
    void repeatedNegotiationsForTheSameTupleAskTheConnectorOnce() {
        // The realistic burst: several consumers negotiating the same dataset and
        // purpose at once. The guard is not re-invoked while a negotiation is
        // parked, so this is the only thing the cache is for.
        var connector = new ScriptedConnector(
            "{\"consent_active\": true, \"subject_ids\": [\"s-1\"], \"should_ask\": true}", null);
        var guard = guard(connector);

        guard.test(gatedProviderRequest());
        guard.test(gatedProviderRequest());
        guard.test(gatedProviderRequest());

        assertEquals(1, connector.checks);
    }
}
