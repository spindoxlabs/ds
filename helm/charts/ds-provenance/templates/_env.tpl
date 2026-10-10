{{- define "prov.env" -}}
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
# The key of the keyed pseudonym every person id is hashed as in the record's
# chain (ADR-0025). Set once per store and never rotated: a new key fails the
# verification of every existing record.
- name: PROVENANCE_SUBJECT_PSEUDONYM_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: PROVENANCE_SUBJECT_PSEUDONYM_KEY
- name: PROVENANCE_DATABASE_URL
  value: {{ include "ds.postgres.url" (dict "ctx" . "database" (include "ds.db.provenance" .) "driver" "asyncpg") | quote }}
# The `@context` IRI on every JSON-LD response. Unset, it stayed at the dev
# default — so an in-cluster deployment published `provenance.dataspaces.localhost`
# to every reader, an address that resolves for nobody. This chart mounts no
# Ingress, so the honest default is the in-cluster Service; a deployment that does
# expose provenance overrides `contextUrl`.
- name: PROVENANCE_CONTEXT_URL
  value: {{ .Values.contextUrl | default (printf "http://%s:%v/prov/context" (include "ds.fullname" .) .Values.service.port) | quote }}
- name: PROVENANCE_MAX_LINEAGE_DEPTH
  value: {{ .Values.maxLineageDepth | quote }}
- name: PROVENANCE_OIDC_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: PROVENANCE_OIDC_INSECURE_DEV
  value: "false"
# A data subject reads their own history from a verifiable credential, not a
# scope. The key that verifies it is resolved from the anchor's DID document
# (`DID-17`), and the trust list says whether that issuer is still accredited.
# Without either the ProductionGuard refuses to start rather than serve a
# person's record on an unverified claim.
- name: PROVENANCE_TRUST_ANCHOR_DID
  value: {{ .Values.trustAnchor.did | default (printf "did:web:%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
- name: PROVENANCE_TRUST_LIST_URL
  value: {{ .Values.trustAnchor.trustListUrl | default (printf "https://%s.%s/trust" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
- name: PROVENANCE_DID_WEB_USE_HTTPS
  value: "true"
{{- $dw := .Values.didWeb | default dict }}
{{- $dwHosts := $dw.internalHosts | default list }}
{{- $dwNets := $dw.internalNetworks | default list }}
{{- if or $dwHosts $dwNets }}
{{- if not (and $dwHosts $dwNets) }}
{{- fail "didWeb: set both internalHosts and internalNetworks, or neither (ADR-0029)" }}
{{- end }}
{{/* ADR-0029: the dataspace's own hosts may resolve into these private networks. */}}
- name: PROVENANCE_DID_WEB_INTERNAL_HOSTS
  value: {{ join "," $dwHosts | quote }}
- name: PROVENANCE_DID_WEB_INTERNAL_NETWORKS
  value: {{ join "," $dwNets | quote }}
{{- end }}
- name: PROVENANCE_VC_INSECURE_DEV
  value: "false"
- name: PROVENANCE_CREDENTIAL_STATUS_URL
  value: {{ .Values.trustAnchor.credentialStatusUrl | default (printf "https://%s.%s/status/1" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
{{- if .Values.trustAnchor.credentialStatusCacheSeconds }}
- name: PROVENANCE_CREDENTIAL_STATUS_CACHE_SECONDS
  value: {{ .Values.trustAnchor.credentialStatusCacheSeconds | quote }}
{{- end }}
# The registry that binds a person's login to their credential (R3): asked with
# the person's own token (`GET /users/me`), so no secret is needed for it. The
# authority namespace's instance holds the Keycloak mappings, as for the connector.
- name: PROVENANCE_IDENTITY_REGISTRY_URL
  value: {{ printf "http://ds-identity-registry.%s.svc.cluster.local:30005" ((.Values.global).namespaces).authority | quote }}
{{- if ne (toString .Values.personTokenRequired) "" }}
- name: PROVENANCE_PERSON_TOKEN_REQUIRED
  value: {{ .Values.personTokenRequired | toString | quote }}
{{- end }}
{{- include "ds.env.aliases" (dict "ctx" . "prefix" "PROVENANCE_") }}
{{- include "ds.env.extra" . }}
{{- end -}}
