package dataspaces.edc;

import org.eclipse.edc.connector.controlplane.contract.spi.policy.AgreementPolicyContext;
import org.eclipse.edc.connector.controlplane.contract.spi.types.agreement.ContractAgreement;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Evaluates {@code {namespace}ConsentStatus eq "active"} against a <b>contract
 * agreement</b>, in the two scopes that carry one.
 *
 * <p>The identity comes from {@link ContractAgreement#getConsumerId()} and the
 * dataset from {@link ContractAgreement#getAssetId()}: both were fixed when the
 * agreement was signed, so unlike the negotiation-scope check there is no
 * dependence on participant-agent attributes.
 *
 * <h2>Two scopes, two stances</h2>
 *
 * <table>
 *   <caption>Where this function runs</caption>
 *   <tr><th>Scope</th><th>Question</th><th>On an unanswerable check</th></tr>
 *   <tr>
 *     <td>{@code transfer.process}</td>
 *     <td>may access <em>start</em>?</td>
 *     <td>{@link Stance#PRE_START} — deny at once</td>
 *   </tr>
 *   <tr>
 *     <td>{@code policy.monitor}</td>
 *     <td>may access <em>continue</em>?</td>
 *     <td>{@link Stance#IN_FLIGHT} — tolerate a bounded number of consecutive
 *         passes, then terminate</td>
 *   </tr>
 * </table>
 *
 * <p>Consent is revocable at any time (GDPR Art. 7(3)), so checking it once at
 * negotiation is not enough. {@code transfer.process} is evaluated by
 * {@code ContractValidationServiceImpl.validateAgreement} when the consumer asks
 * for the transfer, <em>before</em> the transfer process exists and before any
 * EDR is issued — the window between signing an agreement and the first byte,
 * which nothing used to cover. {@code policy.monitor} then re-evaluates the same
 * agreement on every pass for started provider transfers and terminates the
 * transfer as soon as evaluation fails.
 *
 * <p><b>The two stances are not a compromise, they are the same rule applied to
 * different costs.</b> Refusing to start a transfer destroys nothing — the
 * consumer retries — so there is no reason to tolerate silence there. Failing
 * closed on the first unanswerable pass of a <em>running</em> transfer would let
 * one momentary outage destroy live agreements, and it would buy nothing while
 * it lasted: the dataset-api PEP asks the same question on every query and fails
 * closed on its own, so no rows move meanwhile. But never failing closed is
 * worse — root {@code AGENTS.md} requires a constraint function to deny on
 * error, and "the other enforcement point will catch it" stops being a reason
 * once the outage is the steady state. A consent revoked during a sustained
 * outage would never be seen here at all.
 *
 * <p>A definite "no" denies immediately in both stances. The tolerance is for
 * <em>silence</em>, never for a denial.
 */
public class AgreementConsentFunction<C extends AgreementPolicyContext>
    implements AtomicConstraintRuleFunction<Permission, C> {

    /**
     * How this function answers a consent check it cannot get an answer to.
     *
     * <p>Deliberately a pair of constants rather than a setting. Two settings
     * this extension already declares are supplied by no deployment
     * ({@code EDC-12}), and a knob that lets one raise the tolerance to infinity
     * restores the defect it exists to remove.
     */
    enum Stance {
        /**
         * Pre-start, at {@code transfer.process}. One unanswerable check is
         * enough: nothing is running yet, so denying costs a retry.
         *
         * <p>Logged at {@code info} when it allows. It fires once per transfer
         * request, and an enforcement point that is silent when it permits
         * leaves no way to tell <em>checked and allowed</em> from <em>never
         * ran</em> — which is exactly the state this scope was in before it was
         * bound, and exactly what a green end-to-end run cannot distinguish.
         */
        PRE_START(1, "refusing to start the transfer", true),

        /**
         * In flight, at {@code policy.monitor}. Three, because the monitor
         * re-evaluates on a timer: one pass is a blip, three in a row is an
         * outage that has outlived any reasonable retry, and consent could have
         * been revoked at any point during it without this function seeing it.
         *
         * <p>Logged at {@code debug} when it allows: it fires on every pass for
         * every running transfer, so the same line at {@code info} would be pure
         * noise, and the "did it run at all?" question is already answered by
         * the pre-start gate on the same agreement.
         */
        IN_FLIGHT(3, "terminating the transfer", false);

        private final int maxConsecutiveFailures;
        private final String verdict;
        private final boolean announceAllow;

        Stance(int maxConsecutiveFailures, String verdict, boolean announceAllow) {
            this.maxConsecutiveFailures = maxConsecutiveFailures;
            this.verdict = verdict;
            this.announceAllow = announceAllow;
        }
    }

    private final ConsentApi consent;
    private final Monitor monitor;
    private final Stance stance;

    /**
     * Consecutive unanswerable checks, per agreement.
     *
     * <p>Bounded by construction: an entry is removed on any definite answer and
     * on the denial itself, so it holds only agreements currently mid-outage —
     * unlike the decision caches, which {@link TtlCache} bounds explicitly.
     */
    private final Map<String, Integer> consecutiveFailures = new ConcurrentHashMap<>();

    AgreementConsentFunction(ConsentApi consent, Monitor monitor, Stance stance) {
        this.consent = consent;
        this.monitor = monitor;
        this.stance = stance;
    }

    /** The pre-start gate, for {@code transfer.process}. */
    static <C extends AgreementPolicyContext> AgreementConsentFunction<C> preStart(
        ConsentApi consent, Monitor monitor
    ) {
        return new AgreementConsentFunction<>(consent, monitor, Stance.PRE_START);
    }

    /** The continuous check, for {@code policy.monitor}. */
    static <C extends AgreementPolicyContext> AgreementConsentFunction<C> inFlight(
        ConsentApi consent, Monitor monitor
    ) {
        return new AgreementConsentFunction<>(consent, monitor, Stance.IN_FLIGHT);
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, C context) {
        if (operator != Operator.EQ) return false;
        // Not `rightValue.toString()`: on an expanded policy that yields
        // "\"granted\"" — quotes included — and the comparison below then denies
        // with nothing said. See Purposes.unwrapScalar.
        String expectedStatus = Purposes.unwrapScalar(rightValue);
        if (expectedStatus == null) {
            monitor.warning("AgreementConsentFunction: unreadable consent operand %s — %s"
                .formatted(Purposes.describeValue(rightValue), stance.verdict));
            return false;
        }
        if (!"active".equals(expectedStatus) && !"granted".equals(expectedStatus)) return false;

        ContractAgreement agreement = context.contractAgreement();
        if (agreement == null) {
            monitor.warning("AgreementConsentFunction: no contract agreement in context — %s"
                .formatted(stance.verdict));
            return false;
        }

        String datasetId = agreement.getAssetId();
        if (datasetId == null || datasetId.isBlank()) {
            monitor.warning("AgreementConsentFunction: agreement %s carries no asset id — %s"
                .formatted(agreement.getId(), stance.verdict));
            return false;
        }

        String consumerId = agreement.getConsumerId() != null ? agreement.getConsumerId() : "";
        List<String> purposes = Purposes.of(rule);

        // No subject is named: the question is whether *anyone* still consents
        // to this consumer, dataset and purpose. The moment the pool empties the
        // transfer has no lawful basis.
        ConsentApi.Decision decision = consent.check("", datasetId, consumerId, purposes);
        if (decision == null) {
            return tolerate(agreement.getId());
        }

        // A definite answer, of either kind, clears the streak.
        consecutiveFailures.remove(agreement.getId());
        boolean satisfied = decision.satisfied(false);
        if (!satisfied) {
            monitor.info("AgreementConsentFunction: no subject consents to %s for %s — %s"
                .formatted(datasetId, consumerId, stance.verdict));
        } else {
            String allowed =
                "AgreementConsentFunction[%s]: consent verified for %s / %s (purposes=%s) — %s"
                    .formatted(
                        stance.name().toLowerCase(), datasetId, consumerId, purposes,
                        stance == Stance.PRE_START ? "transfer may start" : "transfer may continue");
            if (stance.announceAllow) {
                monitor.info(allowed);
            } else {
                monitor.debug(() -> allowed);
            }
        }
        return satisfied;
    }

    /**
     * Answer a check the connector could not answer, per this function's
     * {@link Stance}.
     *
     * @return {@code true} while the outage is still within tolerance.
     */
    private boolean tolerate(String agreementId) {
        int failures = consecutiveFailures.merge(agreementId, 1, Integer::sum);
        if (failures < stance.maxConsecutiveFailures) {
            monitor.warning(
                ("AgreementConsentFunction: consent check unavailable for agreement %s "
                    + "(%d/%d) — leaving the transfer running for now; the dataset-api PEP "
                    + "fails closed per query. Re-evaluated next pass.")
                    .formatted(agreementId, failures, stance.maxConsecutiveFailures));
            return true;
        }
        // Sustained, not transient — or, at PRE_START, the first and only
        // question we were going to ask. Root AGENTS.md: a constraint function
        // must deny on error, and "the other enforcement point will catch it"
        // stops being a reason once the outage is the steady state, which is
        // precisely when a revocation could have been issued and never seen.
        // Forget the agreement so a recovered connector starts from zero rather
        // than denying the next evaluation immediately.
        consecutiveFailures.remove(agreementId);
        monitor.severe(
            ("AgreementConsentFunction: consent check unavailable for agreement %s on %d "
                + "consecutive evaluation(s) — %s. Consent cannot be confirmed.")
                .formatted(agreementId, stance.maxConsecutiveFailures, stance.verdict));
        return false;
    }
}
