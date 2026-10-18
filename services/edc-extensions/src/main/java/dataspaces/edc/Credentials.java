package dataspaces.edc;

import org.eclipse.edc.iam.verifiablecredentials.spi.model.CredentialSubject;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.VerifiableCredential;
import org.eclipse.edc.participant.spi.ParticipantAgent;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * Reads a claim off the verified credentials EDC already put on the agent.
 *
 * <h2>Why this exists at all</h2>
 *
 * <p>ds used to answer "is this counterparty a member of the dataspace?" with an
 * HTTP call: {@code GET /internal/participants/check} on ds-connector, which
 * asked the trust anchor {@code GET /admin/participants/check}, which tested a
 * hand-kept string against {@code participant.allowed_scopes}. One central call
 * per negotiation, cached for 60 s, to learn something the connector was already
 * holding: the trust anchor signs {@code memberOf} and {@code allowedScopes}
 * into every {@code MembershipCredential}, every connector asks for that
 * credential as a DCP <em>DEFAULT</em> scope
 * ({@code edc.iam.dcp.scopes.membership.*}), and DCP's whole point is that the
 * verifier does not phone home. The string and the claim could also drift:
 * {@code PATCH allowed_scopes} on the anchor does not re-issue the credential.
 * Plan {@code the-owner-scope-is-a-string-nobody-grants}.
 *
 * <h2>Where the claims come from</h2>
 *
 * <p>{@code ProtocolTokenValidatorImpl} turns the verified {@code ClaimToken}
 * into a {@link ParticipantAgent}, whose claims carry one entry — {@code vc},
 * the {@code List<VerifiableCredential>} that passed
 * {@code VerifiableCredentialValidationServiceImpl}: in validity period, not
 * revoked, issued by a configured trusted issuer. <b>Revocation and suspension
 * are checked there</b>, by {@code IsNotRevoked} against the StatusList2021
 * registers ds publishes — which is what makes deactivation immediate enough to
 * drop the HTTP check, bounded by
 * {@code edc.iam.credential.revocation.cache.validity} (15 minutes by default).
 *
 * <h2>Two spellings of one claim</h2>
 *
 * <p>Whether a claim key arrives as {@code memberOf} or as an expanded IRI
 * depends on how the credential reached the agent — a JWT-VC keeps the JSON keys,
 * a JSON-LD one may be expanded against the issuer's context. Both are read, for
 * the same reason {@link Purposes} reads the compact and expanded forms of an
 * operand: which one arrives is not decidable here, and reading one is reading
 * half the credentials.
 */
public final class Credentials {

    /** The credential type that carries dataspace membership. */
    public static final String MEMBERSHIP_CREDENTIAL = "MembershipCredential";

    /** The credential type that names the organisation a participant acts for. */
    public static final String ORGANIZATION_CREDENTIAL = "OrganizationCredential";

    /** EDC's claim key for the verified credential list. */
    static final String VC_CLAIM = "vc";

    private Credentials() {
    }

    /**
     * Every value of {@code claim} on a credential of {@code credentialType}.
     *
     * <p>Empty when the agent is null, holds no credentials, holds none of that
     * type, or none of them states the claim. Every caller treats empty as a
     * denial — a constraint this function cannot evaluate must not admit anyone
     * ({@code CR-4}).
     */
    public static List<String> claimValues(ParticipantAgent agent, String credentialType, String claim) {
        if (agent == null) {
            return new ArrayList<>();
        }
        return claimValues(agent.getClaims(), credentialType, claim);
    }

    /**
     * The same, over a claims map — an agent's, or a {@code ContractAgreement}'s.
     *
     * <p><b>Two shapes of one credential.</b> On a live agent {@code vc} holds
     * {@link VerifiableCredential} objects. An agreement's claims are persisted as
     * JSON and read back as plain maps (EDC's SQL negotiation store,
     * {@code claims} column), so the agreement a {@code ContractNegotiationFinalized}
     * event carries holds {@code Map}s: {@code type} a list, {@code credentialSubject}
     * a list (or one object) whose claims sit beside {@code id} —
     * {@code CredentialSubject} serialises them with {@code @JsonAnyGetter}. Both
     * are read; reading one would make a reloaded agreement look credential-less.
     */
    public static List<String> claimValues(Map<String, Object> claims, String credentialType, String claim) {
        List<String> values = new ArrayList<>();
        if (claims == null) {
            return values;
        }
        Object vcClaim = claims.get(VC_CLAIM);
        if (!(vcClaim instanceof Iterable<?> credentials)) {
            return values;
        }
        for (Object item : credentials) {
            if (item instanceof VerifiableCredential credential) {
                if (credential.getType() == null || !credential.getType().contains(credentialType)) {
                    continue;
                }
                if (credential.getCredentialSubject() == null) {
                    continue;
                }
                for (CredentialSubject subject : credential.getCredentialSubject()) {
                    if (subject != null) {
                        collect(subject.getClaims(), claim, values);
                    }
                }
            } else if (item instanceof Map<?, ?> credential) {
                if (!Purposes.unwrapList(credential.get("type")).contains(credentialType)) {
                    continue;
                }
                Object subjects = credential.get("credentialSubject");
                Iterable<?> each = subjects instanceof Iterable<?> list ? list : Collections.singletonList(subjects);
                for (Object subject : each) {
                    if (subject instanceof Map<?, ?> map) {
                        @SuppressWarnings("unchecked")
                        Map<String, Object> flat = (Map<String, Object>) map;
                        collect(flat, claim, values);
                    }
                }
            }
        }
        return values;
    }

    /** The credential types the agent presented, for a log line that says why. */
    public static String describe(ParticipantAgent agent) {
        if (agent == null || agent.getClaims() == null) {
            return "<no agent>";
        }
        Object vcClaim = agent.getClaims().get(VC_CLAIM);
        if (!(vcClaim instanceof Iterable<?> credentials)) {
            return "<no '%s' claim>".formatted(VC_CLAIM);
        }
        List<String> types = new ArrayList<>();
        for (Object item : credentials) {
            if (item instanceof VerifiableCredential credential && credential.getType() != null) {
                types.addAll(credential.getType());
            }
        }
        return types.isEmpty() ? "<no credentials>" : types.toString();
    }

    private static void collect(Map<String, Object> subjectClaims, String claim, List<String> into) {
        if (subjectClaims == null) {
            return;
        }
        for (var entry : subjectClaims.entrySet()) {
            if (!matches(entry.getKey(), claim)) {
                continue;
            }
            for (String value : Purposes.unwrapList(entry.getValue())) {
                if (!into.contains(value)) {
                    into.add(value);
                }
            }
        }
    }

    /**
     * The plain claim name, or an IRI whose last segment is it.
     *
     * <p>Anchored on {@code #} or {@code /} so that {@code memberOf} does not
     * also match a claim called {@code formerMemberOf}: a suffix test without the
     * separator is how a narrowing check quietly widens.
     */
    private static boolean matches(String key, String claim) {
        if (key == null) {
            return false;
        }
        if (key.equals(claim)) {
            return true;
        }
        return key.endsWith("#" + claim) || key.endsWith("/" + claim);
    }
}
