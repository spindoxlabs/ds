{{/*
The identity-registry environment, shared by the main container and every init
container (migrations and bootstrap both need the database URL).

Order matters: DB_USER and DB_PASSWORD are declared before the URL that
interpolates them with $(VAR). The password never appears in a ConfigMap or in
a rendered URL string.
*/}}
{{- define "ir.env" -}}
{{- include "ds.env.common" . }}
- name: DB_USER
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: DB_USER
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: DB_PASSWORD
- name: IDENTITY_REGISTRY_DATABASE_URL
  value: {{ include "ds.postgres.url" (dict "ctx" . "database" (include "ir.database" .) "driver" "asyncpg") | quote }}
{{/*
The role decides which half of the service this release is. An unrecognised
value is a refusal at startup, not a fallback to `trust-anchor` — a typo
silently promoted to the issuing role would hand a participant's deployment the
ability to mint credentials.
*/}}
- name: IDENTITY_REGISTRY_ROLE
  value: {{ include "ir.role" . | quote }}
{{- if eq (include "ir.role" .) "participant" }}
{{/*
A participant instance serves only the DIDs it holds keys for. Without a DID it
would report healthy and 404 everything, so the service refuses to start — and
`required` here turns that into a failed *render* instead of a failed rollout.
*/}}
- name: IDENTITY_REGISTRY_PARTICIPANT_DID
  value: {{ required "role=participant needs participant.did — the DID this instance holds the key for" .Values.participant.did | quote }}
{{- if .Values.participant.dspAddress }}
- name: IDENTITY_REGISTRY_PARTICIPANT_DSP_ADDRESS
  value: {{ .Values.participant.dspAddress | quote }}
{{- end }}
{{/*
Where this instance enrols. The anchor's own public URL, reached over TLS —
enrolment is where a participant's identity is bound, and doing it over plain
HTTP would let anyone on the path substitute the key being registered.
*/}}
- name: IDENTITY_REGISTRY_TRUST_ANCHOR_URL
  value: {{ printf "https://%s" (include "ir.trustAnchorDomain" .) | quote }}
{{/*
**The participant's own** — the trust anchor mints no STS secret (`D-51`),
because how a party authenticates to itself is not the anchor's decision. Its
own secret, in its own release's Secret.
*/}}
- name: IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET
{{- end }}
- name: IDENTITY_REGISTRY_ENCRYPTION_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: IDENTITY_REGISTRY_ENCRYPTION_KEY
- name: IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN
  value: {{ include "ir.trustAnchorDomain" . | quote }}
{{- if .Values.connectorUrls }}
# Told when the participant registry changes, so an operator does not watch a
# stale list for a minute after a promote. Best-effort: an unreachable connector
# just keeps its own TTL. Rendered by helmfile from the participant list.
- name: IDENTITY_REGISTRY_CONNECTOR_URLS
  value: {{ .Values.connectorUrls | quote }}
{{- end }}
- name: IDENTITY_REGISTRY_CREDENTIALS_CONTEXT_URL
  value: {{ .Values.credentialsContextUrl | default (printf "https://%s/ns/credentials/v1" (.Values.global).baseDomain) | quote }}
- name: IDENTITY_REGISTRY_DATASPACE_URI
  value: {{ .Values.dataspaceUri | default (printf "https://%s/dataspace" (.Values.global).baseDomain) | quote }}
- name: IDENTITY_REGISTRY_DEFAULT_CREDENTIAL_TTL_DAYS
  value: {{ .Values.credentialTtl.defaultDays | quote }}
- name: IDENTITY_REGISTRY_MAX_CREDENTIAL_TTL_DAYS
  value: {{ .Values.credentialTtl.maxDays | quote }}
{{/*
Setting the issuer is what makes ds_auth verify signature, audience and issuer
via JWKS. With DS_ENV=production the ProductionGuard refuses to start without
it, and the insecure-dev flag is pinned false rather than merely defaulted.
*/}}
- name: IDENTITY_REGISTRY_OIDC_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: IDENTITY_REGISTRY_OIDC_INSECURE_DEV
  value: "false"
- name: IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: IDENTITY_REGISTRY_SERVICE_CLIENT_SECRET}
- name: KEYCLOAK_ADMIN_URL
  value: {{ ((.Values.global).keycloak).adminUrl | quote }}
{{/*
Provisioning bundles. A third party configures its own deployment from these, so
they must be addresses reachable *from outside this cluster*: an in-cluster
service DNS name in a bundle produces a connector that cannot resolve its own
trust anchor.
*/}}
- name: IDENTITY_REGISTRY_IDENTITY_REGISTRY_PUBLIC_URL
  value: {{ include "ir.publicUrl" . | quote }}
- name: KEYCLOAK_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: KEYCLOAK_REALM
  value: {{ ((.Values.global).keycloak).realm | quote }}
{{/*
The Keycloak posture, stated rather than inferred. `keycloak.mutate` defaults to
`keycloak.sync.enabled`, which is `false` — so a chart-deployed registry is a
*guest* by default and never writes to a realm it does not own, matching this
file's standing "KC is not ours to mutate". Set it true only where ds owns the
realm; promotion then creates `svc-ds-connector-<alias>` and the bundle carries
its secret. See docs/deployment/keycloak.md.
*/}}
- name: KEYCLOAK_MUTATE
  value: {{ (.Values.keycloak.mutate | default .Values.keycloak.sync.enabled) | quote }}
{{- if and .Values.keycloak.sync.enabled (eq (include "ir.role" .) "trust-anchor") }}
{{/*
Realm admin credentials, used only to create a third party's connector client at
bundle time. Without them the bundle is still issued — without Keycloak
credentials in it, so the third party's connector cannot authenticate to this
registry. Gated on the same flag as org-sync because it is the same access.
*/}}
- name: KEYCLOAK_ADMIN_USERNAME
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: KEYCLOAK_ADMIN_USERNAME
- name: KEYCLOAK_ADMIN_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: KEYCLOAK_ADMIN_PASSWORD
{{- end }}
{{- include "ds.env.aliases" (dict "ctx" . "prefix" "IDENTITY_REGISTRY_") }}
{{- include "ds.env.extra" . }}
{{- end -}}

{{/*
The role, normalised and validated at render time. A chart that let an unknown
role through would defer the failure to a CrashLoopBackOff, where the reason is
one `kubectl logs` away instead of in the diff.
*/}}
{{- define "ir.role" -}}
{{- $role := .Values.role | default "trust-anchor" -}}
{{- if not (has $role (list "trust-anchor" "participant")) -}}
{{- fail (printf "ds-identity-registry: role must be trust-anchor or participant, got %q" $role) -}}
{{- end -}}
{{- $role -}}
{{- end -}}

{{/*
This release's host. The anchor's is the trust-anchor domain; a participant's is
its own — which is also its did:web identity, so the two cannot diverge.
*/}}
{{- define "ir.host" -}}
{{- if eq (include "ir.role" .) "participant" -}}
{{- .Values.participant.host | default (printf "%s.%s" (required "role=participant needs participant.name" .Values.participant.name) (.Values.global).baseDomain) -}}
{{- else -}}
{{- include "ir.trustAnchorDomain" . -}}
{{- end -}}
{{- end -}}

{{- define "ir.publicUrl" -}}
{{- .Values.publicUrl | default (printf "https://%s" (include "ir.host" .)) -}}
{{- end -}}

{{/*
One database per release. A participant sharing the anchor's would put every key
back in one place — the split would be three processes and one custody boundary,
which is the thing `D-47` exists to rule out.
*/}}
{{- define "ir.database" -}}
{{- if .Values.database -}}
{{- .Values.database -}}
{{- else if eq (include "ir.role" .) "participant" -}}
{{- printf "identity_registry_%s" (required "role=participant needs participant.name" .Values.participant.name) | replace "-" "_" -}}
{{- else -}}
{{- (((.Values.global).postgres).databases).identityRegistry -}}
{{- end -}}
{{- end -}}

{{- define "ir.trustAnchorDomain" -}}
{{- if .Values.trustAnchorDomain -}}
{{- .Values.trustAnchorDomain -}}
{{- else -}}
{{- printf "%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain -}}
{{- end -}}
{{- end -}}
