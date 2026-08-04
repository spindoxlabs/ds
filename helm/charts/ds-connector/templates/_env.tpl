{{/*
Connector environment. The connector selects its EDC client by role, so only
the role-appropriate EDC_* URLs are set. URLs use in-cluster DNS, never the
host-gateway convention from compose.
*/}}
{{/*
Sibling releases follow the ds-<service>-<participant> naming enforced by
helmfile, and each release name contains its chart name so the Service fullname
collapses to the release name. So a participant's EDC / provenance Service is
addressable from the participant name alone — NOT from this release's name.
*/}}
{{- define "conn.edcService" -}}
{{- .Values.edc.serviceName | default (printf "ds-edc-%s" .Values.participant.name) -}}
{{- end -}}

{{- define "conn.provenanceService" -}}
{{- .Values.provenanceServiceName | default (printf "ds-provenance-%s" .Values.participant.name) -}}
{{- end -}}

{{- define "conn.irUrl" -}}
{{- printf "http://ds-identity-registry.%s.svc.cluster.local:30005" ((.Values.global).namespaces).authority -}}
{{- end -}}

{{- define "conn.env" -}}
{{- $edc := include "conn.edcService" . -}}
{{- include "ds.env.common" . }}
- name: CONNECTOR_ROLE
  value: {{ .Values.participant.role | quote }}
- name: CONNECTOR_PARTICIPANT_ID
  value: {{ .Values.participant.name | quote }}
- name: CONNECTOR_PARTICIPANT_BASE_URL
  value: {{ printf "https://%s" (include "ds.participantHost" .) | quote }}
- name: CONNECTOR_PARTICIPANT_DID
  value: {{ include "ds.participantDid" . | quote }}
{{/*
Management only. The connector never dials a protocol (DSP) endpoint: a
counter-party is resolved by DSP address through the identity registry, and this
participant's own callback address is `edc.dsp.callback.address` in the ds-edc
chart. EDC_*_PROTOCOL_URL was set here and read by nothing.
*/}}
{{- if eq .Values.participant.role "provider" }}
- name: EDC_PROVIDER_MANAGEMENT_URL
  value: {{ printf "http://%s:%v/management" $edc .Values.edc.managementPort | quote }}
{{- else }}
- name: CONNECTOR_CONSUMER_PARTICIPANT_DID
  value: {{ include "ds.participantDid" . | quote }}
- name: EDC_CONSUMER_MANAGEMENT_URL
  value: {{ printf "http://%s:%v/management" $edc .Values.edc.managementPort | quote }}
{{- end }}
# EDC's Management API key, and **nothing else**. It no longer doubles as an
# `/internal` credential: those routes take a Keycloak bearer carrying
# `connector.internal` (`require_internal_scope`), and the `X-Api-Key` branch is
# deleted. This value is what the connector *presents outbound* to the EDC.
# Read from a mounted file (the connector's preferred form) so it never appears
# in the process env.
- name: EDC_API_KEY_FILE
  value: /run/secrets/edc/api-key
- name: DB_USER
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: DB_USER}
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: DB_PASSWORD}
- name: CONNECTOR_DATABASE_URL
  value: {{ include "ds.postgres.url" (dict "ctx" . "database" (include "ds.db.connector" .) "driver" "asyncpg") | quote }}
- name: CONNECTOR_IDENTITY_REGISTRY_URL
  value: {{ include "conn.irUrl" . | quote }}
- name: CONNECTOR_PROVENANCE_URL
  value: {{ printf "http://%s:30000" (include "conn.provenanceService" .) | quote }}
{{/*
No CONNECTOR_DATASET_API_URL: the dataset API calls the connector, never the
reverse. The address a consumer is handed is the asset's data_address.base_url in
governance.yaml, which the governance ConfigMap carries.
*/}}
- name: CONNECTOR_GOVERNANCE_YAML_PATH
  value: {{ printf "%s/governance.yaml" .Values.governance.mountPath | quote }}
{{- if .Values.governance.overlayName }}
- name: CONNECTOR_GOVERNANCE_OVERLAY_NAME
  value: {{ .Values.governance.overlayName | quote }}
{{- end }}
{{/*
Semantic vocabularies. Rendered only when a registry ConfigMap is named —
otherwise the connector's default path finds nothing, which is the intended
"nothing registered" state and must not become "points at an empty mount".
*/}}
{{- if .Values.vocabularies.configMap }}
- name: CONNECTOR_VOCABULARIES_PATH
  value: {{ printf "%s/vocabularies.yaml" .Values.vocabularies.mountPath | quote }}
- name: CONNECTOR_VOCABULARY_CACHE_DIR
  value: {{ .Values.vocabularies.cache.mountPath | quote }}
{{- end }}
- name: CONNECTOR_TRUST_ANCHOR_DID
  value: {{ .Values.trustAnchor.did | default (printf "did:web:%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
- name: CONNECTOR_TRUST_LIST_URL
  value: {{ .Values.trustAnchor.trustListUrl | default (printf "https://%s.%s/trust" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
- name: CONNECTOR_DID_WEB_USE_HTTPS
  value: "true"
- name: CONNECTOR_VC_INSECURE_DEV
  value: "false"
- name: CONNECTOR_OIDC_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: CONNECTOR_OIDC_INSECURE_DEV
  value: "false"
- name: CONNECTOR_KEYCLOAK_TOKEN_URL
  value: {{ ((.Values.global).keycloak).tokenUrl | quote }}
- name: CONNECTOR_SERVICE_CLIENT_SECRET
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: CONNECTOR_SERVICE_CLIENT_SECRET}
- name: CONNECTOR_NOTIFY_BACKENDS
  value: {{ .Values.notify.backends | quote }}
- name: CONNECTOR_NOTIFY_PORTAL_BASE_URL
  value: {{ .Values.notify.portalBaseUrl | default (printf "https://%s.%s" (((.Values.global).hosts).portal | default "portal") (.Values.global).baseDomain) | quote }}
- name: CONNECTOR_WEBHOOK_ALLOWED_HOSTS
  value: {{ join "," .Values.notify.webhookAllowedHosts | quote }}
{{- include "ds.env.aliases" (dict "ctx" . "prefix" "CONNECTOR_") }}
{{- with ((((.Values).global).keycloak).aliases).owners }}
# The second Layer B map, and the connector is its only consumer: the per-owner
# perimeter compares the token's organisation alias against the asset's owner.
# In a realm ds did not name, no claim alias matches any `Owner.id` and the
# perimeter refuses everything — it fails closed, so the symptom is operators
# locked out of their own assets rather than a breach.
- name: CONNECTOR_OWNER_ALIASES
  value: {{ toJson . | quote }}
{{- end }}
{{- include "ds.env.extra" . }}
{{- end -}}
