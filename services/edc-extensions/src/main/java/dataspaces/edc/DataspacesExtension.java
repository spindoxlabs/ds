package dataspaces.edc;

import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.PolicyEngine;
import org.eclipse.edc.policy.engine.spi.RuleBindingRegistry;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.runtime.metamodel.annotation.Extension;
import org.eclipse.edc.runtime.metamodel.annotation.Inject;
import org.eclipse.edc.spi.system.ServiceExtension;
import org.eclipse.edc.spi.system.ServiceExtensionContext;

/**
 * EDC extension that registers custom ODRL ConstraintFunctions for the
 * dataspaces platform vocabulary ({@code ds:} namespace).
 *
 * <p>Both {@link AccessScopeFunction} and {@link ConsentStatusFunction} are
 * thin HTTP proxies to ds-connector — no business logic lives in Java.
 * {@link ContractRequiredFunction} is stateless and requires no delegation.
 *
 * <p>Configuration properties:
 * <ul>
 *   <li>{@code ds.connector.internal.url} — ds-connector base URL (default: {@code http://ds-connector:30001})</li>
 *   <li>{@code ds.access.scope.cache.ttl.seconds} — TTL for scope check cache (default: {@code 60})</li>
 * </ul>
 */
@Extension("Dataspaces ODRL Constraint Functions")
public class DataspacesExtension implements ServiceExtension {

    @Inject
    private RuleBindingRegistry ruleBindingRegistry;

    @Inject
    private PolicyEngine policyEngine;

    @Override
    public void initialize(ServiceExtensionContext context) {
        String connectorInternalUrl = context.getSetting(
            "ds.connector.internal.url", "http://ds-connector:30001"
        );
        long cacheTtlSeconds = Long.parseLong(
            context.getSetting("ds.access.scope.cache.ttl.seconds", "60")
        );

        // Bind custom left-operands to negotiation scope
        ruleBindingRegistry.bind("ds:accessScope",      "contract.negotiation");
        ruleBindingRegistry.bind("ds:consentStatus",    "contract.negotiation");
        ruleBindingRegistry.bind("ds:contractRequired", "contract.negotiation");

        // Register constraint evaluator functions — context class replaces scope in 0.16 API
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            "ds:accessScope",
            new AccessScopeFunction(connectorInternalUrl, cacheTtlSeconds, context.getMonitor())
        );
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            "ds:consentStatus",
            new ConsentStatusFunction(connectorInternalUrl, context.getMonitor())
        );
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            "ds:contractRequired",
            new ContractRequiredFunction()
        );

        context.getMonitor().info(
            "Dataspaces ODRL extensions registered: accessScope (TTL=%ds), consentStatus (retry×3), contractRequired"
                .formatted(cacheTtlSeconds)
        );
    }
}
