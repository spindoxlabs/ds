package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.event.contractnegotiation.ContractNegotiationEvent;
import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.ContractNegotiationPendingGuard;
import org.eclipse.edc.connector.controlplane.contract.spi.negotiation.store.ContractNegotiationStore;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.AgreementPolicyContext;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.ContractNegotiationPolicyContext;
import org.eclipse.edc.connector.controlplane.contract.spi.policy.TransferProcessPolicyContext;
import org.eclipse.edc.connector.controlplane.transfer.spi.event.TransferProcessEvent;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.iam.oauth2.spi.client.Oauth2Client;
import org.eclipse.edc.policy.engine.spi.PolicyEngine;
import org.eclipse.edc.policy.engine.spi.RuleBindingRegistry;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.runtime.metamodel.annotation.Provider;
import org.eclipse.edc.spi.EdcException;
import org.eclipse.edc.spi.event.EventRouter;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.monitor.Monitor;
import org.eclipse.edc.spi.system.ServiceExtensionContext;
import org.eclipse.edc.spi.types.TypeManager;
import org.eclipse.edc.transaction.spi.TransactionContext;
import org.eclipse.edc.web.spi.WebService;
import org.eclipse.edc.web.spi.configuration.ApiContext;

import java.util.List;

/**
 * EDC extension that registers custom ODRL ConstraintFunctions for the
 * dataspaces platform vocabulary.
 *
 * <p>{@link AccessScopeFunction}, {@link ConsentStatusFunction} and
 * {@link AgreementConsentFunction} are thin HTTP proxies to ds-connector — no
 * business logic lives in Java.
 *
 * <h2>Three scopes, three questions</h2>
 *
 * <ul>
 *   <li>{@code contract.negotiation} — <em>may an agreement be signed?</em>
 *       Membership, purpose and consent are evaluated against a DCP-verified
 *       participant agent before the agreement exists.</li>
 *   <li>{@code transfer.process} — <em>may access start?</em>
 *       {@code ContractValidationServiceImpl.validateAgreement} evaluates the
 *       signed agreement when the consumer asks for the transfer, before the
 *       transfer process is created and before any EDR is issued.</li>
 *   <li>{@code policy.monitor} — <em>may access continue?</em> EDC's policy
 *       monitor re-evaluates the signed agreement's policy for every started
 *       provider transfer and terminates the transfer the moment evaluation
 *       fails. Consent is revocable (GDPR Art. 7(3)), so it has to be answered
 *       at all three, not only at negotiation.</li>
 * </ul>
 *
 * <p>Membership and {@code ds:contractRequired} are deliberately <b>not</b>
 * bound outside {@code contract.negotiation}: both are conditions on entering an
 * agreement, and EDC's scope filter drops any operand not bound to the scope,
 * so leaving them unbound is how they are excluded. Purpose <b>is</b> bound
 * everywhere — not because it can change, but because the consent functions read
 * the purposes off the permission they are handed, and a filtered-out purpose
 * constraint would leave them asking the connector an unscoped question, which
 * the connector fails closed.
 *
 * <h2>Configuration</h2>
 *
 * <p>Three settings are <b>required</b> — the extension refuses to start without
 * them, because an EDC that boots and then silently denies every negotiation
 * because a policy evaluation cannot reach the connector is far harder to
 * diagnose than one that says why:
 *
 * <ul>
 *   <li>{@code ds.connector.internal.token.url} — the Keycloak token endpoint</li>
 *   <li>{@code ds.connector.internal.client.id} — this connector's client</li>
 *   <li>{@code ds.connector.internal.client.secret} — its secret</li>
 * </ul>
 *
 * <p>Three are optional and defaulted:
 *
 * <ul>
 *   <li>{@code dataspaces.odrl.namespace} — ODRL profile namespace (default:
 *       {@code https://w3id.org/dsp/policy/}). <b>Must match the namespace of the
 *       ODRL profile ds-connector maps with</b> — the two are configured
 *       independently and a mismatch unbinds every operand silently. The
 *       binding-vs-emission conformance test in {@code libs/governance} is what
 *       catches that drift.</li>
 *   <li>{@code ds.connector.internal.url} — ds-connector base URL (default: {@code http://ds-connector:30001})</li>
 *   <li>{@code ds.access.scope.cache.ttl.seconds} — TTL for the decision caches (default: {@code 60})</li>
 * </ul>
 *
 * <p>EDC merges the environment into its config, converting
 * {@code ENVIRONMENT_NOTATION} to {@code dot.notation}, so each of these is also
 * settable as an environment variable. The {@code .properties} file cannot carry
 * the three credential settings as {@code ${PLACEHOLDER}} — see
 * {@link #setting(ServiceExtensionContext, String)}.
 */
@Extension("Dataspaces ODRL Constraint Functions")
public class DataspacesExtension implements ServiceExtension {

    private static final String NEGOTIATION_SCOPE = ContractNegotiationPolicyContext.NEGOTIATION_SCOPE;
    private static final String TRANSFER_SCOPE = TransferProcessPolicyContext.TRANSFER_SCOPE;
    private static final String MONITOR_SCOPE = PolicyMonitorContext.POLICY_MONITOR_SCOPE;

    /** Every scope in which this platform's policies are evaluated. */
    private static final String[] SCOPES = {NEGOTIATION_SCOPE, TRANSFER_SCOPE, MONITOR_SCOPE};

    /**
     * Rule actions the governance mapper can emit, in every form the policy may
     * carry depending on whether the ODRL context was applied. A rule whose
     * action is unbound is removed from the filtered policy entirely, taking its
     * consent constraint with it — so an unbound action silently disables the
     * check rather than failing it.
     *
     * <p>The profile query action is <b>not</b> here: it is
     * {@code {namespace}Query} and is bound from the configured namespace, so a
     * deployment that changes the namespace does not have to edit this list.
     * A deployment-specific IRI was hardcoded here once and outlived the profile
     * that produced it — see {@code EDC-13}.
     *
     * <p>{@code odrl:use} is bound although the mapper does not emit it: it is
     * ODRL's default action, selectable through {@code dataspace.permitted_actions},
     * and EDC's own core binds it in these scopes anyway.
     */
    static final List<String> ACTIONS = List.of(
        "odrl:aggregate",
        "odrl:use",
        "odrl:transfer",
        "http://www.w3.org/ns/odrl/2/aggregate",
        "http://www.w3.org/ns/odrl/2/use",
        "http://www.w3.org/ns/odrl/2/transfer"
    );

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

        ConnectorClient connector = connector(context);
        ConsentApi consentApi = new ConsentApi(connector);

        // ── Negotiation lifecycle → ds-connector ─────────────────────────────
        // DSP carries no signal the connector could use to learn that a
        // negotiation was terminated. EDC's event router does, so we forward it.
        eventRouter.register(
            ContractNegotiationEvent.class,
            new NegotiationEventPublisher(connector, typeManager, context.getMonitor())
        );

        // ── Transfer lifecycle → ds-connector ────────────────────────────────
        // The same gap on the transfer half. `POST /webhooks/transfer-process`
        // existed with no producer in any deployment, which left a *provider*
        // emitting no `DataTransferCompleted` — one of the sixteen events
        // rulebook L-1 makes mandatory for every participant.
        eventRouter.register(
            TransferProcessEvent.class,
            new TransferEventPublisher(connector, context.getMonitor())
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

        // Everything that decides an access decision, in one package-visible
        // method so it can be exercised without booting an EDC runtime.
        // `PolicyRegistrationTest` walks it: what is bound, in which scope, and
        // whether every bound operand has a function. That check is why
        // `ds:accessScope` and the negotiation-scope consent bypass could sit
        // here unnoticed — nothing could see the registration surface.
        registerPolicy(
            policyEngine, ruleBindingRegistry, connector, consentApi,
            namespace, cacheTtlSeconds, context.getMonitor()
        );
    }

    /**
     * Bind every operand and register every function, for both scopes.
     *
     * <p>Package-visible and free of {@link ServiceExtensionContext} on purpose:
     * the bindings *are* the enforcement surface, and until this was separable
     * nothing could assert what they were.
     */
    static void registerPolicy(
        PolicyEngine policyEngine,
        RuleBindingRegistry ruleBindingRegistry,
        ConnectorClient connector,
        ConsentApi consentApi,
        String namespace,
        long cacheTtlSeconds,
        Monitor monitor
    ) {
        String membershipOperand = namespace + "Membership";
        String consentOperand = namespace + "ConsentStatus";
        String queryAction = namespace + "Query";
        // Both forms of the consent operand. The mapper emits the expanded one;
        // the compact one appears on a policy that reached the store without the
        // ODRL context applied, and on agreements signed before the profile
        // moved. `ConsentConstraints` matches on the local name for the same
        // reason.
        String[] consentOperands = {consentOperand, "ds:consentStatus"};

        // ── Actions, in every scope ──────────────────────────────────────────
        for (String scope : SCOPES) {
            for (String action : ACTIONS) {
                ruleBindingRegistry.bind(action, scope);
            }
            ruleBindingRegistry.bind(queryAction, scope);
            // odrl:purpose — bound in both the compact and the expanded form,
            // since whether the ODRL context is applied depends on how the
            // policy reached the store.
            ruleBindingRegistry.bind(Purposes.COMPACT, scope);
            ruleBindingRegistry.bind(Purposes.EXPANDED, scope);
            for (String operand : consentOperands) {
                ruleBindingRegistry.bind(operand, scope);
            }
        }

        // ── Negotiation-only operands ────────────────────────────────────────
        // Conditions on *entering* an agreement. Unbound elsewhere, so EDC's
        // scope filter strips them from the policies the transfer gate and the
        // monitor evaluate.
        //
        // `ds:accessScope` used to be bound here with no registered function and
        // no producer anywhere in the platform. That is the worse of the two
        // failure modes: a bound operand with no function fails evaluation
        // outright, so had anything ever emitted it, every negotiation would
        // have been denied with "No evaluation function found". It is unbound
        // now, and the binding-vs-emission conformance test in `libs/governance`
        // is what stops a dead binding coming back (`EDC-06`, `EDC-10`).
        ruleBindingRegistry.bind("ds:contractRequired", NEGOTIATION_SCOPE);
        ruleBindingRegistry.bind(membershipOperand, NEGOTIATION_SCOPE);

        // ── Negotiation scope: may an agreement be signed? ───────────────────
        //
        // Registered on ContractNegotiationPolicyContext, *not* on the broader
        // ParticipantAgentPolicyContext. The engine matches a function with
        // `contextType().isAssignableFrom(context.getClass())`, and the
        // catalogue and transfer contexts implement that interface too — so the
        // broad registration ran these functions in the transfer scope, where
        // they would now collide with the agreement-backed consent check on the
        // same operand key (PolicyEvaluator keeps one function per key, and the
        // winner is whichever was registered last).
        policyEngine.registerFunction(
            ContractNegotiationPolicyContext.class,
            Permission.class,
            membershipOperand,
            new AccessScopeFunction<>(connector, cacheTtlSeconds, monitor)
        );
        // Both forms: the operand is bound in this scope in both, and a bound
        // operand with *no* function fails evaluation outright. `ds:consentStatus`
        // was bound here and registered only in policy.monitor (`EDC-07`).
        for (String operand : consentOperands) {
            policyEngine.registerFunction(
                ContractNegotiationPolicyContext.class,
                Permission.class,
                operand,
                new ConsentStatusFunction<>(consentApi, monitor)
            );
        }
        // The dataset-aware half of the same check, and the one that actually
        // enforces it. A constraint function is handed the Permission, and
        // `Rule` has no target at 0.16.0 — so the dataset can only be read off
        // the Policy, which is what a PolicyValidatorRule receives.
        //
        // **This registration is what makes `ds:consentStatus` mean anything at
        // negotiation.** Removing it re-opens the bypass — see
        // NegotiationConsentValidator, and the test that asserts it is here.
        policyEngine.registerPostValidator(
            ContractNegotiationPolicyContext.class,
            new NegotiationConsentValidator(consentApi, monitor)
        );
        policyEngine.registerFunction(
            ContractNegotiationPolicyContext.class,
            Permission.class,
            "ds:contractRequired",
            new ContractRequiredFunction<>(monitor)
        );
        registerPurpose(policyEngine, ContractNegotiationPolicyContext.class, new PurposeFunction<>(monitor));

        // ── Transfer scope: may access start? ────────────────────────────────
        //
        // `ContractValidationServiceImpl.validateAgreement` evaluates here, from
        // TransferProcessProtocolServiceImpl.requestedAction — before the
        // transfer process is created and before an EDR exists. Nothing occupied
        // this scope, so a consent withdrawn after signing was enforced by
        // nothing until the first policy-monitor pass, which only runs for
        // transfers that have already started (`EDC-16`, DSSC-AUP-07).
        //
        // Pre-start stance: an unanswerable check denies at once. Refusing to
        // start costs the consumer a retry; the tolerance in the monitor exists
        // only because terminating destroys a running transfer.
        registerAgreementConsent(
            policyEngine, TransferProcessPolicyContext.class,
            AgreementConsentFunction.preStart(consentApi, monitor), consentOperands
        );
        registerPurpose(policyEngine, TransferProcessPolicyContext.class, new PurposeFunction<>(monitor));

        // ── Policy-monitor scope: may access continue? ───────────────────────
        registerAgreementConsent(
            policyEngine, PolicyMonitorContext.class,
            AgreementConsentFunction.inFlight(consentApi, monitor), consentOperands
        );
        registerPurpose(policyEngine, PolicyMonitorContext.class, new PurposeFunction<>(monitor));

        monitor.info(
            ("Dataspaces ODRL extensions registered: %sMembership (TTL=%ds), %sConsentStatus "
                + "(negotiation + transfer.process + policy.monitor), odrl:purpose, namespace=%s")
                .formatted(namespace, cacheTtlSeconds, namespace, namespace)
        );
    }

    private static <C extends AgreementPolicyContext> void registerAgreementConsent(
        PolicyEngine policyEngine,
        Class<C> contextType,
        AgreementConsentFunction<C> function,
        String[] operands
    ) {
        for (String operand : operands) {
            policyEngine.registerFunction(contextType, Permission.class, operand, function);
        }
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

    private static final long DEFAULT_CACHE_TTL_SECONDS = 60L;

    /**
     * The decision-cache TTL, in seconds.
     *
     * <p>A bare {@code Long.parseLong} threw out of {@code initialize} — and out
     * of the {@code @Provider} method, which EDC may call first — so a typo in
     * one optional tuning value took the whole connector down at boot with a
     * {@code NumberFormatException} and no mention of the setting that caused
     * it. A cache lifetime is not a safety property: falling back to the default
     * and saying so loudly is strictly better than refusing to start.
     */
    private static long cacheTtlSeconds(ServiceExtensionContext context) {
        String configured = context.getSetting(
            "ds.access.scope.cache.ttl.seconds", String.valueOf(DEFAULT_CACHE_TTL_SECONDS)
        );
        try {
            long seconds = Long.parseLong(configured.trim());
            if (seconds <= 0) {
                throw new NumberFormatException("must be positive");
            }
            return seconds;
        } catch (NumberFormatException | NullPointerException e) {
            context.getMonitor().warning(
                "ds.access.scope.cache.ttl.seconds is '%s', which is not a positive number of seconds — using %d"
                    .formatted(configured, DEFAULT_CACHE_TTL_SECONDS));
            return DEFAULT_CACHE_TTL_SECONDS;
        }
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

    private static <C extends org.eclipse.edc.policy.engine.spi.PolicyContext> void registerPurpose(
        PolicyEngine policyEngine, Class<C> contextType, PurposeFunction<C> function
    ) {
        for (String operand : new String[]{Purposes.COMPACT, Purposes.EXPANDED}) {
            policyEngine.registerFunction(contextType, Permission.class, operand, function);
        }
    }
}
