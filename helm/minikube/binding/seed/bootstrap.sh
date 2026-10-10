# Run by the trust anchor's bootstrap after `org apply` (the chart's seed hook). The
# holder accepts the community as the collector of the consent its connector holds
# (ADR-0026; the owners file marks `example-rec` `collects_consent: true`). Idempotent.
#
# **A revocation survives this script.** `collector add` never revives a revoked pair: it
# leaves the row revoked, exits 0 and prints who revoked it, when and why, so this
# bootstrap keeps running on every anchor start without undoing `ir-cli collector revoke`.
# Lifting a revocation is an explicit act with a reason, recorded on the row:
#   kubectl exec -n ds-authority deploy/ds-identity-registry -- ir-cli collector reinstate \
#     --holder-did <holder> --collector-did <collector> --reason "<why>" [--by <who>]
# Removing the pair from this file is not a revocation (the row stays as it is).
#
# **Deferred until both are enrolled.** `collector add` refuses a DID that is not an
# active participant, and a participant becomes active only when it spends its enrolment
# code, which needs this anchor running first. So on the first install this step prints
# that it is deferred and the bootstrap goes on; after the enrolment, restart the anchor
# (`kubectl rollout restart -n ds-authority deploy/ds-identity-registry`) and it runs.
# Failing here instead would fail the anchor's install, which helm then rolls back.
set -eu
HOLDER=did:web:example-dso.ds.test
COLLECTOR=did:web:example-rec.ds.test
active() { ir-cli participant list | grep -F "  $1 " | grep -q "status=active"; }
if active "$HOLDER" && active "$COLLECTOR"; then
  ir-cli collector add --holder-did "$HOLDER" --collector-did "$COLLECTOR"
else
  echo "collector step deferred: $HOLDER and $COLLECTOR are not both active participants yet (enrol, then restart the anchor)"
fi
ir-cli collector list
