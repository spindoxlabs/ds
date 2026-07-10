package dataspaces.edc;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Requires;
import org.eclipse.edc.spi.iam.ClaimToken;
import org.eclipse.edc.spi.iam.IdentityService;
import org.eclipse.edc.spi.iam.TokenParameters;
import org.eclipse.edc.spi.iam.TokenRepresentation;
import org.eclipse.edc.spi.iam.VerificationContext;
import org.eclipse.edc.spi.result.Result;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.CredentialSubject;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.Issuer;
import org.eclipse.edc.iam.verifiablecredentials.spi.model.VerifiableCredential;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;

/**
 * Demo-only fallback for local DCP interoperability.
 *
 * <p>EDC's DCP verifier is still attempted first. If it rejects the local demo
 * VP/VC shape, this wrapper can accept the self-issued JWT enough to let the
 * catalogue/negotiation flow run end-to-end. Keep disabled outside local demos.
 */
@Extension("Dataspaces demo identity fallback")
@Requires(IdentityService.class)
public class DemoIdentityFallbackExtension implements ServiceExtension {
    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public void initialize(ServiceExtensionContext context) {
        boolean enabled = Boolean.parseBoolean(context.getSetting("ds.demo.identity.enabled", "false"));
        if (!enabled) {
            return;
        }
        IdentityService delegate = context.getService(IdentityService.class);
        context.registerService(IdentityService.class, new FallbackIdentityService(delegate, mapper, context.getMonitor()));
        context.getMonitor().warning("Demo identity fallback is enabled. Do not use this setting outside local demos.");
    }

    private static class FallbackIdentityService implements IdentityService {
        private final IdentityService delegate;
        private final ObjectMapper mapper;
        private final org.eclipse.edc.spi.monitor.Monitor monitor;

        FallbackIdentityService(IdentityService delegate, ObjectMapper mapper, org.eclipse.edc.spi.monitor.Monitor monitor) {
            this.delegate = delegate;
            this.mapper = mapper;
            this.monitor = monitor;
        }

        @Override
        public Result<TokenRepresentation> obtainClientCredentials(String participantContextId, TokenParameters tokenParameters) {
            return delegate.obtainClientCredentials(participantContextId, tokenParameters);
        }

        @Override
        public Result<ClaimToken> verifyJwtToken(
            String participantContextId,
            TokenRepresentation tokenRepresentation,
            VerificationContext verificationContext
        ) {
            Result<ClaimToken> verified = delegate.verifyJwtToken(participantContextId, tokenRepresentation, verificationContext);
            if (verified.succeeded()) {
                return verified;
            }

            try {
                String token = tokenRepresentation.getToken().replaceFirst("(?i)^Bearer\\s+", "");
                Map<String, Object> claims = decodeClaims(token);
                Object issuer = claims.get("iss");
                Object subject = claims.get("sub");
                if (issuer == null || subject == null || !issuer.equals(subject)) {
                    return verified;
                }
                VerifiableCredential credential = VerifiableCredential.Builder.newInstance()
                    .id("urn:dataspaces:demo-membership:" + subject)
                    .issuer(new Issuer(subject.toString()))
                    .type("VerifiableCredential")
                    .type("MembershipCredential")
                    .issuanceDate(Instant.now())
                    .credentialSubject(CredentialSubject.Builder.newInstance()
                        .id(subject.toString())
                        .claim("id", subject.toString())
                        .build())
                    .build();
                claims.put("vc", List.of(credential));
                monitor.warning("Demo identity fallback accepted SI token for %s after DCP verifier failure: %s"
                    .formatted(issuer, verified.getFailureDetail()));
                return Result.success(ClaimToken.Builder.newInstance().claims(claims).build());
            } catch (Exception e) {
                return verified;
            }
        }

        private Map<String, Object> decodeClaims(String jwt) throws Exception {
            String[] parts = jwt.split("\\.");
            if (parts.length < 2) {
                throw new IllegalArgumentException("Not a JWT");
            }
            byte[] payload = Base64.getUrlDecoder().decode(parts[1]);
            return mapper.readValue(new String(payload, StandardCharsets.UTF_8), new TypeReference<>() {});
        }
    }
}
