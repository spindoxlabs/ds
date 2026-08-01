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
# scope. Without the trust-anchor key that credential cannot be verified, so the
# ProductionGuard refuses to start rather than serve on an unverified claim.
- name: PROVENANCE_TRUST_ANCHOR_DID
  value: {{ .Values.trustAnchor.did | default (printf "did:web:%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
- name: PROVENANCE_TRUST_ANCHOR_KEY_PATH
  value: {{ .Values.trustAnchor.keyMountPath | quote }}
- name: PROVENANCE_VC_INSECURE_DEV
  value: "false"
{{- include "ds.env.aliases" (dict "ctx" . "prefix" "PROVENANCE_") }}
{{- include "ds.env.extra" . }}
{{- end -}}
