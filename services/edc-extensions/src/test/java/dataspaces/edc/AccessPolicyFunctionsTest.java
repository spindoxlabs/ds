package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.catalog.spi.policy.CatalogPolicyContext;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.CredentialSubject;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.VerifiableCredential;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.Issuer;
import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * The two functions the ContractDefinition's <b>access</b> policy is made of.
 *
 * <p>Neither makes a call. Membership is the {@code memberOf} claim on the
 * {@code MembershipCredential} EDC has already verified — in validity period,
 * issued by a trusted issuer, and <em>not suspended</em> against the StatusList
 * registers the trust anchor publishes. The recipient restriction is the
 * counterparty's verified identity against the DIDs the dataset's sharing offers
 * name. Both replace an HTTP round trip to a string the trust anchor kept by
 * hand ({@code the-owner-scope-is-a-string-nobody-grants}).
 *
 * <p>Every test here is about denial, because the direction that matters is the
 * one that fails open: a constraint the engine cannot evaluate must deny
 * ({@code CR-4}), and a constraint that denies looks identical to one that
 * works.
 */
class AccessPolicyFunctionsTest {

    private static final String DATASPACE = "https://dataspaces.localhost/dataspace";
    private static final String REC = "did:web:rec.dataspaces.localhost";
    private static final String THIRD_PARTY = "did:web:third-party.dataspaces.localhost";

    private static class NoopMonitor implements Monitor {
    }

    private static VerifiableCredential credential(String type, Map<String, Object> claims) {
        return VerifiableCredential.Builder.newInstance()
            .type(type)
            .issuer(new Issuer("did:web:trust-anchor.dataspaces.localhost", Map.of()))
            .issuanceDate(Instant.now())
            .credentialSubject(CredentialSubject.Builder.newInstance()
                .id(THIRD_PARTY)
                .claims(claims)
                .build())
            .build();
    }

    private static CatalogPolicyContext context(String identity, Object... credentials) {
        Map<String, Object> claims = credentials.length == 0
            ? Map.of()
            : Map.of(Credentials.VC_CLAIM, List.of(credentials));
        return new CatalogPolicyContext(new ParticipantAgent(identity, claims, Map.of()));
    }

    private static boolean membership(Object rightValue, CatalogPolicyContext context) {
        return new DataspaceMembershipFunction<CatalogPolicyContext>(new NoopMonitor())
            .evaluate(Operator.EQ, rightValue, Permission.Builder.newInstance().build(), context);
    }

    private static boolean recipient(Object rightValue, CatalogPolicyContext context) {
        return new RecipientFunction<CatalogPolicyContext>(new NoopMonitor())
            .evaluate(Operator.IS_ANY_OF, rightValue, Permission.Builder.newInstance().build(), context);
    }

    // ── membership ───────────────────────────────────────────────────────────

    @Test
    void aMemberOfThisDataspaceIsAdmitted() {
        var vc = credential(Credentials.MEMBERSHIP_CREDENTIAL, Map.of("memberOf", DATASPACE));
        assertTrue(membership(DATASPACE, context(THIRD_PARTY, vc)));
    }

    @Test
    void anExpandedClaimKeyIsReadToo() {
        // A credential that reached the agent through JSON-LD expansion carries
        // the claim under the issuer's term IRI. Reading only the plain key is
        // reading half the credentials, and the half that is missed denies.
        var vc = credential(Credentials.MEMBERSHIP_CREDENTIAL,
            Map.of("https://dataspaces.localhost/ns/credentials/v1#memberOf", DATASPACE));
        assertTrue(membership(DATASPACE, context(THIRD_PARTY, vc)));
    }

    @Tag("rule:A-11")
    @Test
    void aMemberOfAnotherDataspaceIsDenied() {
        var vc = credential(Credentials.MEMBERSHIP_CREDENTIAL,
            Map.of("memberOf", "https://other.example.org/dataspace"));
        assertFalse(membership(DATASPACE, context(THIRD_PARTY, vc)));
    }

    @Tag("rule:A-11")
    @Test
    void noMembershipCredentialDenies() {
        var vc = credential("OrganizationCredential", Map.of("memberOf", DATASPACE));
        assertFalse(membership(DATASPACE, context(THIRD_PARTY, vc)),
            "the claim must come from a MembershipCredential, not from whatever carries the word");
        assertFalse(membership(DATASPACE, context(THIRD_PARTY)),
            "an agent presenting nothing is not a member");
    }

    @Tag("rule:A-11")
    @Test
    void anUnreadableMembershipOperandDenies() {
        var vc = credential(Credentials.MEMBERSHIP_CREDENTIAL, Map.of("memberOf", DATASPACE));
        assertFalse(membership(List.of(DATASPACE, "https://other.example.org/dataspace"),
            context(THIRD_PARTY, vc)));
        assertFalse(membership(null, context(THIRD_PARTY, vc)));
    }

    @Test
    void anExpandedOperandIsUnwrappedRatherThanStringified() {
        // `rightValue.toString()` on {"@value": "…"} produces an object dump, and
        // the comparison then fails on exactly the policies that took the
        // expanded path — silently, by denying.
        var vc = credential(Credentials.MEMBERSHIP_CREDENTIAL, Map.of("memberOf", DATASPACE));
        assertTrue(membership(Map.of("@value", DATASPACE), context(THIRD_PARTY, vc)));
    }

    // ── recipient ────────────────────────────────────────────────────────────

    @Test
    void aNamedRecipientIsAdmitted() {
        assertTrue(recipient(List.of(REC, THIRD_PARTY), context(THIRD_PARTY)));
    }

    @Tag("rule:A-11")
    @Test
    void aParticipantOutsideTheSetIsDenied() {
        assertFalse(recipient(List.of(REC), context(THIRD_PARTY)));
    }

    @Tag("rule:A-11")
    @Test
    void anEmptyRecipientSetDeniesRatherThanAdmittingEverybody() {
        // The shape a governance file produces when no recipient alias resolves
        // to a DID. "No recipients" must never read as "no restriction".
        assertFalse(recipient(List.of(), context(THIRD_PARTY)));
        assertFalse(recipient(null, context(THIRD_PARTY)));
    }

    @Test
    void theRecipientSetIsReadThroughTheJsonLdWrappers() {
        assertTrue(recipient(
            List.of(Map.of("@id", REC), Map.of("@id", THIRD_PARTY)),
            context(THIRD_PARTY)));
    }

    @Tag("rule:A-11")
    @Test
    void anUnsupportedOperatorDenies() {
        var function = new RecipientFunction<CatalogPolicyContext>(new NoopMonitor());
        assertFalse(function.evaluate(Operator.IS_NONE_OF, List.of(THIRD_PARTY),
            Permission.Builder.newInstance().build(), context(THIRD_PARTY)));
    }
}
