package dataspaces.edc;

import org.eclipse.edc.participant.spi.ParticipantAgent;
import org.eclipse.edc.participant.spi.ParticipantAgentPolicyContext;
import org.eclipse.edc.policy.engine.spi.AtomicConstraintRuleFunction;
import org.eclipse.edc.policy.model.Operator;
import org.eclipse.edc.policy.model.Permission;
import org.eclipse.edc.spi.monitor.Monitor;

import java.util.List;

/**
 * Evaluates {@code {namespace}Membership eq "<dataspace uri>"} against the
 * {@code memberOf} claim of the counterparty's {@code MembershipCredential}.
 *
 * <p>It replaces {@code AccessScopeFunction}, which asked ds-connector over HTTP
 * whether a hand-kept string was in the participant's {@code allowed_scopes}.
 * {@link Credentials} has the full argument; the short version is that the
 * answer was already in the connector's hands, signed, and the HTTP round trip
 * re-centralised what DCP decentralises.
 *
 * <h2>No cache, deliberately</h2>
 *
 * <p>There is nothing left to cache. The claim is read out of an object EDC
 * built for this request from a presentation it has already verified, so the
 * evaluation is a list walk — no I/O, no TTL, and no window in which a
 * suspended participant keeps a stale {@code true}. The remaining staleness is
 * EDC's own {@code edc.iam.credential.revocation.cache.validity} (15 minutes by
 * default), which bounds how long a flipped StatusList bit takes to be seen.
 *
 * <h2>Fails closed</h2>
 *
 * <p>No agent, an unreadable right operand, no {@code MembershipCredential}, or
 * a {@code memberOf} that is not the dataspace asked for: {@code false}
 * ({@code CR-4}). An unparseable operand is logged, because a constraint that
 * denies everybody looks exactly like a working one.
 */
public class DataspaceMembershipFunction<C extends ParticipantAgentPolicyContext>
    implements AtomicConstraintRuleFunction<Permission, C> {

    private static final String MEMBER_OF_CLAIM = "memberOf";

    private final Monitor monitor;

    public DataspaceMembershipFunction(Monitor monitor) {
        this.monitor = monitor;
    }

    @Override
    public boolean evaluate(Operator operator, Object rightValue, Permission rule, C context) {
        if (operator != Operator.EQ) {
            monitor.warning("DataspaceMembershipFunction: operator %s is not supported — denying".formatted(operator));
            return false;
        }

        String expected = Purposes.unwrapScalar(rightValue);
        if (expected == null || expected.isBlank()) {
            monitor.warning("DataspaceMembershipFunction: unreadable membership operand %s — denying"
                .formatted(Purposes.describeValue(rightValue)));
            return false;
        }

        ParticipantAgent agent = context.participantAgent();
        List<String> memberships = Credentials.claimValues(
            agent, Credentials.MEMBERSHIP_CREDENTIAL, MEMBER_OF_CLAIM);
        if (memberships.isEmpty()) {
            monitor.debug("DataspaceMembershipFunction: no %s claim on any %s — denying (credentials: %s)"
                .formatted(MEMBER_OF_CLAIM, Credentials.MEMBERSHIP_CREDENTIAL, Credentials.describe(agent)));
            return false;
        }
        return memberships.contains(expected);
    }
}
