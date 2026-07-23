{{- define "cat.connectorService" -}}
{{- .Values.connectorServiceName | default (printf "ds-connector-%s" .Values.participant.name) -}}
{{- end -}}

{{- define "cat.env" -}}
{{- include "ds.env.common" . }}
- name: CATALOG_CONNECTOR_URL
  value: {{ printf "http://%s:%v" (include "cat.connectorService" .) .Values.connectorPort | quote }}
- name: CATALOG_IDENTITY_REGISTRY_URL
  value: {{ printf "http://ds-identity-registry.%s.svc.cluster.local:30005" ((.Values.global).namespaces).authority | quote }}
- name: CATALOG_BASE_URL
  value: {{ printf "http://%s:%v" (include "ds.fullname" .) .Values.service.port | quote }}
- name: CATALOG_CRAWL_INTERVAL
  value: {{ .Values.crawlInterval | quote }}
- name: CATALOG_STARTUP_DELAY
  value: {{ .Values.startupDelay | quote }}
- name: CATALOG_MAX_DATASETS_PER_PROVIDER
  value: {{ .Values.maxDatasetsPerProvider | quote }}
- name: CATALOG_KEYCLOAK_TOKEN_URL
  value: {{ ((.Values.global).keycloak).tokenUrl | quote }}
- name: CATALOG_SERVICE_CLIENT_ID
  value: {{ .Values.auth.serviceClientId | quote }}
- name: CATALOG_SERVICE_CLIENT_SECRET
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: CATALOG_SERVICE_CLIENT_SECRET}
- name: CATALOG_OIDC_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: CATALOG_OIDC_INSECURE_DEV
  value: "false"
{{- include "ds.env.extra" . }}
{{- end -}}
