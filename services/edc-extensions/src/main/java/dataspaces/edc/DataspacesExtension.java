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
 * dataspaces platform vocabulary.
 *
 * <p>Both {@link AccessScopeFunction} and {@link ConsentStatusFunction} are
 * thin HTTP proxies to ds-connector — no business logic lives in Java.
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

    @Inject
    private RuleBindingRegistry ruleBindingRegistry;

    @Inject
    private PolicyEngine policyEngine;

    @Override
    public void initialize(ServiceExtensionContext context) {
        String namespace = context.getSetting(
            "dataspaces.odrl.namespace", "https://w3id.org/dsp/policy/"
        );
        String connectorInternalUrl = context.getSetting(
            "ds.connector.internal.url", "http://ds-connector:30001"
        );
        long cacheTtlSeconds = Long.parseLong(
            context.getSetting("ds.access.scope.cache.ttl.seconds", "60")
        );

        String membershipOperand = namespace + "Membership";
        String consentOperand = namespace + "ConsentStatus";

        // Bind custom left-operands to negotiation scope
        ruleBindingRegistry.bind(membershipOperand, "contract.negotiation");
        ruleBindingRegistry.bind(consentOperand,     "contract.negotiation");

        // Register constraint evaluator functions
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            membershipOperand,
            new AccessScopeFunction(connectorInternalUrl, cacheTtlSeconds, context.getMonitor())
        );
        policyEngine.registerFunction(
            ParticipantAgentPolicyContext.class,
            Permission.class,
            consentOperand,
            new ConsentStatusFunction(connectorInternalUrl, context.getMonitor())
        );

        context.getMonitor().info(
            "Dataspaces ODRL extensions registered: %sMembership (TTL=%ds), %sConsentStatus (retry×3), namespace=%s"
                .formatted(namespace, cacheTtlSeconds, namespace, namespace)
        );
    }
}
