package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;

/**
 * Evaluates {@code {namespace}ConsentStatus eq "active"} against a <b>running
 * transfer</b>, in the {@code policy.monitor} scope.
 *
 * <p>Consent is revocable at any time (GDPR Art. 7(3)), so checking it once at
 * negotiation is not enough: a transfer that started under a valid consent must
 * stop when that consent is withdrawn. EDC's policy monitor re-evaluates the
 * <em>agreement</em> policy on every pass for provider-side started transfers
 * and terminates the transfer as soon as evaluation fails — which is what this
 * function turns into a consent check.
 *
 * <p>The identity comes from {@link ContractAgreement#getConsumerId()} and the
 * dataset from {@link ContractAgreement#getAssetId()}: both were fixed when the
 * agreement was signed, so unlike the negotiation-scope check there is no
 * dependence on participant-agent attributes.
 *
 * <p><b>Denies on a definite "no", not on silence.</b> A connector that says no
 * subject consents terminates the transfer. A connector that cannot answer does
 * not: this is the coarser of two enforcement points, and the dataset-api PEP
 * re-asks the same question on every query and fails closed on its own — so an
 * unanswerable consent question already stops the data moving, without also
 * destroying an agreement that would need a fresh negotiation to rebuild.
 */
public class AgreementConsentFunction implements AtomicConstraintRuleFunction<Permission, PolicyMonitorContext> {

    private final ConsentApi consent;
    private final Monitor monitor;

    public AgreementConsentFunction(ConsentApi consent, Monitor monitor) {
        this.consent = consent;
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, PolicyMonitorContext context) {
        if (operator != Operator.EQ) return false;
        String expectedStatus = rightValue.toString();
        if (!"active".equals(expectedStatus) && !"granted".equals(expectedStatus)) return false;

        ContractAgreement agreement = context.contractAgreement();
        if (agreement == null) {
            monitor.warning("AgreementConsentFunction: no contract agreement in context — terminating");
            return false;
        }

        String datasetId = agreement.getAssetId();
        if (datasetId == null || datasetId.isBlank()) {
            monitor.warning("AgreementConsentFunction: agreement %s carries no asset id — terminating"
                .formatted(agreement.getId()));
            return false;
        }

        String consumerId = agreement.getConsumerId() != null ? agreement.getConsumerId() : "";
        List<String> purposes = Purposes.of(rule);

        // No subject is named: the question is whether *anyone* still consents
        // to this consumer, dataset and purpose. The moment the pool empties the
        // transfer has no lawful basis and the monitor terminates it.
        ConsentApi.Decision decision = consent.check("", datasetId, consumerId, purposes);
        if (decision == null) {
            // "I could not ask" is not "the answer is no", and here the
            // difference matters: this verdict terminates a *running* transfer,
            // and a terminated transfer needs a fresh negotiation to recover.
            // Failing closed at negotiation costs a retry; failing closed here
            // would let one unreachable connector — or one bad request — destroy
            // live agreements irreversibly.
            //
            // Not terminating is safe because this is the coarse of two
            // enforcement points: the dataset-api PEP calls the same consent
            // check on every query and fails closed itself, so while the
            // connector cannot answer, no rows leave the provider anyway. The
            // transfer survives; the data does not move.
            monitor.warning(
                ("AgreementConsentFunction: consent check unavailable for agreement %s — leaving the "
                    + "transfer running (the dataset-api PEP fails closed per query). Re-evaluated next pass.")
                    .formatted(agreement.getId()));
            return true;
        }

        boolean satisfied = decision.satisfied(false);
        if (!satisfied) {
            monitor.info("AgreementConsentFunction: no subject consents to %s for %s — transfer will be terminated"
                .formatted(datasetId, consumerId));
        }
        return satisfied;
    }
}
