package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.event.contractnegotiation.ContractNegotiationEvent;
import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.ContractNegotiationPendingGuard;
import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.store.ContractNegotiationStore;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.iam.oauth2.spi.client.Oauth2Client;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.PolicyEngine;
import org.eclipse.edc.policy.engine.spi.RuleBindingRegistry;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.runtime.metamodel.annotation.Provider;
import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.event.EventRouter;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.spi.types.TypeManager;
import org.eclipse.edc.transaction.spi.TransactionContext;
import org.eclipse.edc.web.spi.WebService;
import org.eclipse.edc.web.spi.configuration.ApiContext;

/**
 * EDC extension that registers custom ODRL ConstraintFunctions for the
 * dataspaces platform vocabulary.
 *
 * <p>{@link AccessScopeFunction}, {@link ConsentStatusFunction} and
 * {@link AgreementConsentFunction} are thin HTTP proxies to ds-connector — no
 * business logic lives in Java.
 *
 * <h2>Two scopes, two questions</h2>
 *
 * <ul>
 *   <li>{@code contract.negotiation} — <em>may access start?</em> Membership,
 *       purpose and consent are evaluated against a DCP-verified participant
 *       agent before an agreement is signed.</li>
 *   <li>{@code policy.monitor} — <em>may access continue?</em> EDC's policy
 *       monitor re-evaluates the signed agreement's policy for every started
 *       provider transfer and terminates the transfer the moment evaluation
 *       fails. Consent is revocable (GDPR Art. 7(3)), so it has to be answered
 *       here too, not only at negotiation.</li>
 * </ul>
 *
 * <p>Membership and {@code ds:contractRequired} are deliberately <b>not</b>
 * bound to {@code policy.monitor}: both are conditions on entering an
 * agreement, and EDC's scope filter drops any operand not bound to the scope,
 * so leaving them unbound is how they are excluded. Purpose <b>is</b> bound
 * there — not because it can change, but because the consent functions read the
 * purposes off the permission they are handed, and a filtered-out purpose
 * constraint would leave them asking the connector an unscoped question, which
 * the connector fails closed.
 *
 * <p>Configuration properties:
 * <ul>
 *   <li>{@code dataspaces.odrl.namespace} — ODRL profile namespace (default: {@code https://w3id.org/dsp/policy/})</li>
 *   <li>{@code ds.connector.internal.url} — ds-connector base URL (default: {@code http://ds-connector:30001})</li>
 *   <li>{@code ds.access.scope.cache.ttl.seconds} — TTL for scope check cache (default: {@code 60})</li>
 * </ul>
 */
@Extension("Dataspaces ODRL Constraint Functions")
public class DataspacesExtension implements ServiceExtension {

    private static final String NEGOTIATION_SCOPE = "contract.negotiation";
    private static final String MONITOR_SCOPE = PolicyMonitorContext.POLICY_MONITOR_SCOPE;

    /**
     * Rule actions the governance mapper can emit, in every form the policy may
     * carry depending on whether the ODRL context was applied. A rule whose
     * action is unbound is removed from the filtered policy entirely, taking its
     * consent constraint with it — so an unbound action silently disables the
     * check rather than failing it.
     */
    private static final String[] ACTIONS = {
        "ds:query",
        "odrl:aggregate",
        "odrl:use",
        "odrl:transfer",
        "https://dataspaces.localhost/ns/energy#query",
        "http://www.w3.org/ns/odrl/2/aggregate",
        "http://www.w3.org/ns/odrl/2/use",
        "http://www.w3.org/ns/odrl/2/transfer",
    };

    @Inject
    private RuleBindingRegistry ruleBindingRegistry;

    @Inject
    private PolicyEngine policyEngine;

    @Inject
    private EventRouter eventRouter;

    @Inject
    private TypeManager typeManager;

    @Inject
    private Oauth2Client oauth2Client;

    @Inject
    private WebService webService;

    @Inject
    private ContractNegotiationStore negotiationStore;

    @Inject
    private TransactionContext transactionContext;

    private ConnectorClient connector;

    /**
     * Supersedes EDC's default no-op guard, so a provider negotiation for a
     * consent-gated dataset parks instead of being refused outright while a data
     * subject decides. See {@link ConsentPendingGuard}.
     *
     * <p>EDC may call this before or after {@link #initialize}, depending on
     * which extension asks for the guard first — hence
     * {@link #connector(ServiceExtensionContext)} rather than a field assigned
     * in {@code initialize}.
     */
    @Provider
    public ContractNegotiationPendingGuard consentPendingGuard(ServiceExtensionContext context) {
        return new ConsentPendingGuard(
            new ConsentApi(connector(context)),
            new ConsentAskApi(connector(context)),
            cacheTtlSeconds(context),
            context.getMonitor()
        );
    }

    @Override
    public void initialize(ServiceExtensionContext context) {
        String namespace = context.getSetting(
            "dataspaces.odrl.namespace", "https://w3id.org/dsp/policy/"
        );
        long cacheTtlSeconds = cacheTtlSeconds(context);

        String membershipOperand = namespace + "Membership";
        String consentOperand = namespace + "ConsentStatus";
        String queryAction = namespace + "Query";

        ConnectorClient connector = connector(context);
        ConsentApi consentApi = new ConsentApi(connector);

        // ── Negotiation lifecycle → ds-connector ─────────────────────────────
        // DSP carries no signal the connector could use to learn that a
        // negotiation was terminated. EDC's event router does, so we forward it.
        eventRouter.register(
            ContractNegotiationEvent.class,
            new NegotiationEventPublisher(connector, typeManager, context.getMonitor())
        );

        // ── ds-connector → this control plane ────────────────────────────────
        // The only way to un-park a negotiation: the Management API can
        // terminate one but cannot clear `pending`. On the management context,
        // so it inherits that API's authentication.
        webService.registerResource(
            ApiContext.MANAGEMENT,
            new NegotiationResumeController(
                negotiationStore, transactionContext, context.getMonitor()
            )
        );

        // ── Actions, in both scopes ──────────────────────────────────────────
        for (String scope : new String[]{NEGOTIATION_SCOPE, MONITOR_SCOPE}) {
            for (String action : ACTIONS) {
                ruleBindingRegistry.bind(action, scope);
            }
            ruleBindingRegistry.bind(queryAction, scope);
            // odrl:purpose — bound in both the compact and the expanded form,
            // since whether the ODRL context is applied depends on how the
            // policy reached the store.
            ruleBindingRegistry.bind(Purposes.COMPACT, scope);
            ruleBindingRegistry.bind(Purposes.EXPANDED, scope);
            ruleBindingRegistry.bind("ds:consentStatus", scope);
            ruleBindingRegistry.bind(consentOperand, scope);
        }

        // ── Negotiation-only operands ────────────────────────────────────────
        // Conditions on *entering* an agreement. Unbound in policy.monitor, so
        // EDC's scope filter strips them from the policy the monitor evaluates.
        ruleBindingRegistry.bind("ds:accessScope", NEGOTIATION_SCOPE);
        ruleBindingRegistry.bind("ds:contractRequired", NEGOTIATION_SCOPE);
        ruleBindingRegistry.bind(membershipOperand, NEGOTIATION_SCOPE);

        // ── Negotiation scope: may access start? ─────────────────────────────
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            membershipOperand,
            new AccessScopeFunction(connector, cacheTtlSeconds)
        );
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            consentOperand,
            new ConsentStatusFunction(consentApi, context.getMonitor())
        );
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            "ds:contractRequired",
            (op, rv, duty, ctx) -> true
        );
        registerPurpose(ParticipantAgentPolicyContext.class, new PurposeFunction<>(context.getMonitor()));

        // ── Policy-monitor scope: may access continue? ───────────────────────
        AgreementConsentFunction agreementConsent =
            new AgreementConsentFunction(consentApi, context.getMonitor());
        for (String operand : new String[]{consentOperand, "ds:consentStatus"}) {
            policyEngine.registerFunction(
                PolicyMonitorContext.class, Permission.class, operand, agreementConsent
            );
        }
        registerPurpose(PolicyMonitorContext.class, new PurposeFunction<>(context.getMonitor()));

        context.getMonitor().info(
            ("Dataspaces ODRL extensions registered: %sMembership (TTL=%ds), %sConsentStatus "
                + "(negotiation + policy.monitor), odrl:purpose, namespace=%s")
                .formatted(namespace, cacheTtlSeconds, namespace, namespace)
        );
    }

    /**
     * The shared client to ds-connector's internal API.
     *
     * <p>Built once and reused: it owns the OkHttp connection pool and, when
     * client credentials are configured, the cached access token. A second
     * instance would mean a second token refresh loop for no benefit.
     */
    private synchronized ConnectorClient connector(ServiceExtensionContext context) {
        if (connector == null) {
            connector = new ConnectorClient(
                context.getSetting("ds.connector.internal.url", "http://ds-connector:30001"),
                internalAuth(context),
                context.getMonitor()
            );
        }
        return connector;
    }

    private static long cacheTtlSeconds(ServiceExtensionContext context) {
        return Long.parseLong(context.getSetting("ds.access.scope.cache.ttl.seconds", "60"));
    }

    /**
     * How this EDC authenticates to ds-connector: a Keycloak
     * {@code client_credentials} token, as this connector's own client.
     *
     * <p>There is no {@code X-Api-Key} fallback. ds-connector stopped accepting
     * that header, so a fallback could only produce 403s — and an EDC that boots
     * and then silently denies every negotiation because a policy evaluation
     * cannot reach the connector is far harder to diagnose than one that refuses
     * to start with the reason in the message.
     */
    private InternalAuth internalAuth(ServiceExtensionContext context) {
        String clientId = setting(context, "ds.connector.internal.client.id");
        String clientSecret = setting(context, "ds.connector.internal.client.secret");
        String tokenUrl = setting(context, "ds.connector.internal.token.url");

        if (clientId.isEmpty() || clientSecret.isEmpty() || tokenUrl.isEmpty()) {
            throw new EdcException(
                "ds-connector internal API credentials are not configured. Set "
                    + "DS_CONNECTOR_INTERNAL_CLIENT_ID, DS_CONNECTOR_INTERNAL_CLIENT_SECRET and "
                    + "DS_CONNECTOR_INTERNAL_TOKEN_URL in the environment (EDC maps "
                    + "ENVIRONMENT_NOTATION to ds.connector.internal.*). They cannot be set in "
                    + "the .properties file as ${PLACEHOLDER}: EDC does not interpolate it. "
                    + "EDC_API_KEY is no longer accepted on /internal/* — it is EDC's Management "
                    + "API key and nothing else."
            );
        }

        context.getMonitor().info(
            "ds-connector internal API: authenticating as %s via client_credentials".formatted(clientId)
        );
        return new Oauth2InternalAuth(
            oauth2Client, tokenUrl, clientId, clientSecret, context.getMonitor()
        );
    }

    /**
     * A configuration value, treating an unresolved {@code ${PLACEHOLDER}} as absent.
     *
     * <p>EDC merges the environment into its config, converting
     * {@code ENVIRONMENT_NOTATION} to {@code dot.notation}, so
     * {@code DS_CONNECTOR_INTERNAL_CLIENT_ID} arrives as
     * {@code ds.connector.internal.client.id} without anything here.
     *
     * <p>What it does <em>not</em> do is interpolate the properties file:
     * {@code FsConfigurationExtension} is a plain {@code Properties.load()}, so a
     * {@code ${VAR}} written there is stored verbatim. Treating that literal as
     * absent turns a config mistake into the "not configured" error below,
     * rather than a client id literally named {@code ${...}} that 401s on every
     * call for reasons nothing explains.
     */
    private static String setting(ServiceExtensionContext context, String key) {
        String value = context.getSetting(key, "");
        if (value == null || value.contains("${")) {
            return "";
        }
        return value.trim();
    }

    private <C extends org.eclipse.edc.policy.engine.spi.PolicyContext> void registerPurpose(
        Class<C> contextType, PurposeFunction<C> function
    ) {
        for (String operand : new String[]{Purposes.COMPACT, Purposes.EXPANDED}) {
            policyEngine.registerFunction(contextType, Permission.class, operand, function);
        }
    }
}
