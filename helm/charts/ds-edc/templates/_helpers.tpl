{{- define "edc.host" -}}
{{- include "ds.participantHost" . -}}
{{- end -}}

{{- define "edc.did" -}}
{{- include "ds.participantDid" . -}}
{{- end -}}

{{- define "edc.trustAnchorDid" -}}
{{- .Values.trustAnchor.did | default (printf "did:web:%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) -}}
{{- end -}}

{{/* Identity-registry base URL — authority namespace, in-cluster DNS. */}}
{{- define "edc.irBase" -}}
{{- printf "http://ds-identity-registry.%s.svc.cluster.local:30005" ((.Values.global).namespaces).authority -}}
{{- end -}}

{{- define "edc.connectorService" -}}
{{- .Values.connectorServiceName | default (printf "ds-connector-%s" .Values.participant.name) -}}
{{- end -}}
