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

{{- define "conn.protocolPublicUrl" -}}
{{- if .Values.edc.protocolPublicUrl -}}
{{- .Values.edc.protocolPublicUrl -}}
{{- else -}}
{{- printf "https://%s/protocol/2025-1" (include "ds.participantHost" .) -}}
{{- end -}}
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
{{- if eq .Values.participant.role "provider" }}
- name: EDC_PROVIDER_MANAGEMENT_URL
  value: {{ printf "http://%s:%v/management" $edc .Values.edc.managementPort | quote }}
- name: EDC_PROVIDER_PROTOCOL_URL
  value: {{ include "conn.protocolPublicUrl" . | quote }}
{{- else }}
- name: CONNECTOR_CONSUMER_PARTICIPANT_DID
  value: {{ include "ds.participantDid" . | quote }}
- name: EDC_CONSUMER_MANAGEMENT_URL
  value: {{ printf "http://%s:%v/management" $edc .Values.edc.managementPort | quote }}
- name: EDC_CONSUMER_PROTOCOL_URL
  value: {{ include "conn.protocolPublicUrl" . | quote }}
{{- end }}
# The EDC API key doubles as the /internal X-Api-Key. Read from a mounted file
# (the connector's preferred form) so it never appears in the process env.
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
{{- if .Values.datasetApi.url }}
- name: CONNECTOR_DATASET_API_URL
  value: {{ .Values.datasetApi.url | quote }}
{{- end }}
- name: CONNECTOR_GOVERNANCE_YAML_PATH
  value: {{ printf "%s/governance.yaml" .Values.governance.mountPath | quote }}
{{- if .Values.governance.overlayName }}
- name: CONNECTOR_GOVERNANCE_OVERLAY_NAME
  value: {{ .Values.governance.overlayName | quote }}
{{- end }}
- name: CONNECTOR_TRUST_ANCHOR_DID
  value: {{ .Values.trustAnchor.did | default (printf "did:web:%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) | quote }}
- name: CONNECTOR_TRUST_ANCHOR_KEY_PATH
  value: {{ .Values.trustAnchor.keyMountPath | quote }}
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
{{- include "ds.env.extra" . }}
{{- end -}}
