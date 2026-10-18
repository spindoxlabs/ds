package dataspaces.edc;

import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.CredentialSubject;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.Issuer;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.VerifiableCredential;
import org.eclipse.edc.policy.model.Policy;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * The consumer's organisation, as the finalized event forwards it.
 *
 * <p>The agreement a {@code ContractNegotiationFinalized} event carries has been
 * read back from EDC's store, so its {@code vc} claim holds maps, not
 * {@link VerifiableCredential}s. The round-trip test is the one that matters:
 * a reader that only knew the object form would forward nothing, and the
 * connector would read "no organisation" for every agreement.
 */
class NegotiationEventPublisherTest {

    private static final String CONSUMER = "did:web:third-party.dataspaces.localhost";

    private static VerifiableCredential credential(String type, Map<String, Object> claims) {
        return VerifiableCredential.Builder.newInstance()
            .type("VerifiableCredential")
            .type(type)
            .issuer(new Issuer("did:web:trust-anchor.dataspaces.localhost", Map.of()))
            .issuanceDate(Instant.parse("2026-10-18T00:00:00Z"))
            .credentialSubject(CredentialSubject.Builder.newInstance()
                .id(CONSUMER)
                .claims(claims)
                .build())
            .build();
    }

    private static ContractAgreement agreement(Map<String, Object> claims) {
        return ContractAgreement.Builder.newInstance()
            .id("agreement-1")
            .providerId("did:web:rec.dataspaces.localhost")
            .consumerId(CONSUMER)
            .assetId("dataset-1")
            .policy(Policy.Builder.newInstance().build())
            .claims(claims)
            .build();
    }

    private static final Map<String, Object> ORG = Map.of(
        "organizationId", "example-org",
        "organizationType", "rec",
        "legalName", "Example Organization");

    private static final Map<String, Object> MEMBER = Map.of("memberOf", "dataspace");

    @Test
    void the_presented_organisation_is_forwarded() {
        var claims = Map.<String, Object>of(Credentials.VC_CLAIM, List.of(
            credential("MembershipCredential", MEMBER),
            credential("OrganizationCredential", ORG)));

        var organization = NegotiationEventPublisher.presentedOrganization(agreement(claims));

        assertEquals(List.of("example-org"), organization.get("organizationId"));
        assertEquals(List.of("rec"), organization.get("organizationType"));
    }

    @Test
    void an_agreement_read_back_from_the_store_is_read_too() {
        // No java.time module on this classpath; the dates are not what is read,
        // the subject's shape is.
        var mapper = JsonMapper.builder()
            .disable(MapperFeature.REQUIRE_HANDLERS_FOR_JAVA8_TIMES)
            .build();
        // What the SQL store writes and reads: JSON in, `Map<String, Object>` out.
        @SuppressWarnings("unchecked")
        Map<String, Object> stored = mapper.convertValue(
            Map.of(Credentials.VC_CLAIM, List.of(
                credential("MembershipCredential", MEMBER),
                credential("OrganizationCredential", ORG))),
            Map.class);
        Object first = ((List<?>) stored.get(Credentials.VC_CLAIM)).get(0);
        assertEquals(true, first instanceof Map, "the stored form is a map, which is the point");

        var organization = NegotiationEventPublisher.presentedOrganization(agreement(stored));

        assertEquals(List.of("example-org"), organization.get("organizationId"));
        assertEquals(List.of("rec"), organization.get("organizationType"));
    }

    @Test
    void only_the_organisation_credential_is_read() {
        // The claim name on another credential type says nothing about the
        // organisation the counterparty acts for.
        var claims = Map.<String, Object>of(Credentials.VC_CLAIM, List.of(
            credential("MembershipCredential", Map.of("organizationId", "somebody-else"))));

        var organization = NegotiationEventPublisher.presentedOrganization(agreement(claims));

        assertEquals(List.of(), organization.get("organizationId"));
        assertEquals(List.of(), organization.get("organizationType"));
    }

    @Test
    void no_claims_forward_empty_lists() {
        var organization = NegotiationEventPublisher.presentedOrganization(agreement(null));

        assertEquals(List.of(), organization.get("organizationId"));
        assertEquals(List.of(), organization.get("organizationType"));
    }

    @Test
    void two_organisations_are_both_forwarded_for_the_connector_to_refuse() {
        var claims = Map.<String, Object>of(Credentials.VC_CLAIM, List.of(
            credential("OrganizationCredential", ORG),
            credential("OrganizationCredential", Map.of("organizationId", "other-org"))));

        var organization = NegotiationEventPublisher.presentedOrganization(agreement(claims));

        assertEquals(List.of("example-org", "other-org"), organization.get("organizationId"));
    }
}
