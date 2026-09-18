package dataspaces.edc;

import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;

/**
 * Evaluates {@code odrl:recipient isAnyOf [<did>, …]} against the counterparty's
 * verified identity.
 *
 * <p>ODRL 2.2 defines {@code odrl:recipient} as <em>"the party receiving the
 * result/outcome of exercising the action of the Rule"</em>, with a right operand
 * that identifies parties. The parties here are participant DIDs, and the
 * identity is {@link ParticipantAgent#getIdentity()} — the same value EDC stores
 * as {@code counterPartyId} and derives from the first {@code credentialSubject.id}
 * among the verified credentials, not from a self-asserted token field.
 *
 * <h2>One restriction, one implementation</h2>
 *
 * <p>The set comes from the sharing offers bound to the dataset
 * ({@code SharingOfferCatalogue.recipients_of}), which is the same statement
 * {@code circle.admits_wildcard} reads when it decides whether a standing consent
 * admits a requester ({@code D-14}). Two enforcement points, one declaration —
 * see the plan's "One rule, one implementation".
 *
 * <h2>Where it is bound</h2>
 *
 * <p>In the {@code catalog} scope, and only there, because it belongs to the
 * <b>access</b> policy. EDC evaluates that policy twice with a
 * {@code CatalogPolicyContext}: when it builds a catalogue for a counterparty
 * ({@code ContractDefinitionResolverImpl.resolveFor}) and again when that
 * counterparty opens a negotiation
 * ({@code ContractValidationServiceImpl.validateInitialOffer}). So a
 * non-recipient never sees the dataset, and asking for it by id is refused
 * rather than merely unlisted.
 *
 * <h2>Fails closed</h2>
 *
 * <p>An empty recipient set denies. That is the shape a governance file produces
 * when none of its offers' recipient aliases resolves to a DID, and it must
 * never read as "no restriction": a restriction that evaporates when its inputs
 * are missing is the fail-open {@code CR-4} exists to forbid. The publish is
 * refused before this can happen — {@code offer-recipient-resolves} is an error,
 * not a warning — and this is the second line.
 */
public class RecipientFunction<C extends ParticipantAgentPolicyContext>
    implements AtomicConstraintRuleFunction<Permission, C> {

    static final String COMPACT = "odrl:recipient";
    static final String EXPANDED = "http://www.w3.org/ns/odrl/2/recipient";

    private final Monitor monitor;

    public RecipientFunction(Monitor monitor) {
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, C context) {
        // `EQ` is accepted beside `IS_ANY_OF` so that a hand-written or
        // pre-existing single-recipient policy is evaluated rather than silently
        // denied; the mapper always emits `isAnyOf`, including for one.
        if (operator != Operator.IS_ANY_OF && operator != Operator.EQ && operator != Operator.IN) {
            monitor.warning("RecipientFunction: operator %s is not supported — denying".formatted(operator));
            return false;
        }

        List<String> recipients = Purposes.unwrapList(rightValue);
        if (recipients.isEmpty()) {
            monitor.warning("RecipientFunction: unreadable or empty recipient operand %s — denying"
                .formatted(Purposes.describeValue(rightValue)));
            return false;
        }

        ParticipantAgent agent = context.participantAgent();
        String identity = agent == null ? null : agent.getIdentity();
        if (identity == null || identity.isBlank()) {
            monitor.warning("RecipientFunction: no verified counterparty identity — denying");
            return false;
        }
        return recipients.contains(identity);
    }
}
