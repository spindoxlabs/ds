{{/*
Portal environment. The portal is SSR — these upstreams are called server-side,
never from the browser, so they use in-cluster DNS. Sibling releases follow
ds-<service>-<participant>.
*/}}
{{- define "portal.origin" -}}
{{- printf "https://%s.%s" (((.Values.global).hosts).portal | default "portal") (.Values.global).baseDomain -}}
{{- end -}}

{{- define "portal.env" -}}
{{- $p := .Values.participant.name -}}
{{- include "ds.env.common" . }}
- name: ORIGIN
  value: {{ include "portal.origin" . | quote }}
# Server-side upstreams (in-cluster).
- name: CONNECTOR_URL
  value: {{ printf "http://ds-connector-%s:30001" $p | quote }}
- name: PROVENANCE_URL
  value: {{ printf "http://ds-provenance-%s:30000" $p | quote }}
- name: FEDERATED_CATALOG_URL
  value: {{ printf "http://ds-federated-catalog-%s:30003" $p | quote }}
- name: IDENTITY_REGISTRY_URL
  value: {{ printf "http://ds-identity-registry.%s.svc.cluster.local:30005" ((.Values.global).namespaces).authority | quote }}
{{- if .Values.datasetApi.url }}
- name: CATALOGUE_URL
  value: {{ .Values.datasetApi.url | quote }}
{{- end }}
# Consumer-side wiring. Without these the portal falls back to the compose
# host-gateway convention (172.17.0.1), which does not resolve in-cluster.
- name: CONSUMER_CONNECTOR_URL
  value: {{ .Values.consumer.connectorUrl | default (printf "http://ds-connector-%s:30001" $p) | quote }}
- name: CONSUMER_PARTICIPANT_DID
  value: {{ include "ds.participantDid" . | quote }}
{{- if .Values.consumer.defaultAssigner }}
- name: CONSUMER_DEFAULT_ASSIGNER
  value: {{ .Values.consumer.defaultAssigner | quote }}
{{- end }}
{{- if .Values.consumer.defaultCounterPartyAddress }}
- name: CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS
  value: {{ .Values.consumer.defaultCounterPartyAddress | quote }}
{{- end }}
# Login is oauth2-proxy's, not the portal's. The portal stopped being a
# confidential OIDC client — no AUTH_SECRET, no client secret, no callback
# registration — and reads the access token the proxy forwards as
# `X-Auth-Request-Access-Token`. This value is only where the browser is sent to
# start or end a session; the ds-oauth2-proxy release serves it on this host.
- name: OAUTH2_PROXY_BASE_URL
  value: {{ include "portal.origin" . | quote }}
- name: PORTAL_SERVICE_CLIENT_ID
  value: {{ .Values.auth.serviceClientId | quote }}
- name: PORTAL_SERVICE_CLIENT_SECRET
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: PORTAL_SERVICE_CLIENT_SECRET}
{{- include "ds.env.extra" . }}
{{- end -}}
