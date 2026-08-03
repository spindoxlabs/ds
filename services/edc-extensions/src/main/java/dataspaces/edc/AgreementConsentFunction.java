package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.connector.policy.monitor.spi.PolicyMonitorContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

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
 * <p><b>Denies on a definite "no", and on sustained silence.</b> A connector
 * that says no subject consents terminates the transfer immediately. A connector
 * that cannot answer is tolerated for a bounded number of consecutive passes and
 * then terminates too.
 *
 * <p>Both halves are deliberate. Failing closed on the first unanswerable pass
 * would let one momentary outage destroy live agreements, and it would buy
 * nothing while it lasted: the dataset-api PEP asks the same question on every
 * query and fails closed on its own, so no rows move meanwhile. But never
 * failing closed is worse — root {@code AGENTS.md} requires a constraint
 * function to deny on error, and "the other enforcement point will catch it"
 * stops being a reason once the outage is the steady state. A consent revoked
 * during a sustained outage would never be seen here at all.
 */
public class AgreementConsentFunction implements AtomicConstraintRuleFunction<Permission, PolicyMonitorContext> {

    /**
     * Unanswerable passes tolerated per agreement before the transfer is
     * terminated. Three, because EDC's policy monitor re-evaluates on a timer:
     * one pass is a blip, three in a row is an outage that has outlived any
     * reasonable retry, and consent could have been revoked at any point during
     * it without this function being able to see it.
     *
     * <p>Deliberately a constant rather than a setting. Two settings this
     * extension already declares are read by nothing (`EDC-12`), and a knob that
     * lets a deployment raise this to infinity restores the defect it exists to
     * remove.
     */
    private static final int DEFAULT_MAX_CONSECUTIVE_FAILURES = 3;

    private final ConsentApi consent;
    private final Monitor monitor;
    private final int maxConsecutiveFailures;

    /**
     * Consecutive unanswerable checks, per agreement.
     *
     * <p>Bounded by construction: an entry is removed on any definite answer and
     * on termination, so it holds only agreements currently mid-outage — unlike
     * the two decision caches in this unit, which `EDC-11` is about.
     */
    private final Map<String, Integer> consecutiveFailures = new ConcurrentHashMap<>();

    public AgreementConsentFunction(ConsentApi consent, Monitor monitor) {
        this(consent, monitor, DEFAULT_MAX_CONSECUTIVE_FAILURES);
    }

    AgreementConsentFunction(ConsentApi consent, Monitor monitor, int maxConsecutiveFailures) {
        this.consent = consent;
        this.monitor = monitor;
        this.maxConsecutiveFailures = maxConsecutiveFailures;
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
            int failures = consecutiveFailures.merge(agreement.getId(), 1, Integer::sum);
            if (failures < maxConsecutiveFailures) {
                // A single unanswerable pass is not a denial. This verdict
                // terminates a *running* transfer, so failing closed on one blip
                // would let a momentary connector outage destroy live agreements
                // — and meanwhile no rows move anyway, because the dataset-api
                // PEP asks the same question per query and fails closed itself.
                monitor.warning(
                    ("AgreementConsentFunction: consent check unavailable for agreement %s "
                        + "(%d/%d) — leaving the transfer running for now; the dataset-api PEP "
                        + "fails closed per query. Re-evaluated next pass.")
                        .formatted(agreement.getId(), failures, maxConsecutiveFailures));
                return true;
            }
            // Sustained, not transient. Root AGENTS.md: a constraint function
            // must deny on error, and "the other enforcement point will catch
            // it" stops being a reason once the outage is the steady state —
            // that is precisely when a revocation could have been issued and
            // never seen. Forget the agreement so a recovered connector starts
            // from zero rather than terminating the next transfer immediately.
            consecutiveFailures.remove(agreement.getId());
            monitor.severe(
                ("AgreementConsentFunction: consent check unavailable for agreement %s on %d "
                    + "consecutive passes — terminating. Consent cannot be confirmed and the "
                    + "outage is no longer transient.")
                    .formatted(agreement.getId(), maxConsecutiveFailures));
            return false;
        }

        // A definite answer, of either kind, clears the streak.
        consecutiveFailures.remove(agreement.getId());
        boolean satisfied = decision.satisfied(false);
        if (!satisfied) {
            monitor.info("AgreementConsentFunction: no subject consents to %s for %s — transfer will be terminated"
                .formatted(datasetId, consumerId));
        }
        return satisfied;
    }
}
