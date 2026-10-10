{{- define "edc.host" -}}
{{- include "ds.participantHost" . -}}
{{- end -}}

{{- define "edc.did" -}}
{{- include "ds.participantDid" . -}}
{{- end -}}

{{- define "edc.trustAnchorDid" -}}
{{- .Values.trustAnchor.did | default (printf "did:web:%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain) -}}
{{- end -}}

{{/*
This participant's own identity registry (`ds-identity-registry-<participant>`, in this
release's namespace): it holds the participant's key and the secret this EDC presents
to its STS (`D-47`, `D-51`). Not the trust anchor's, which mints no STS secret and
cannot sign for a participant. Derived from the participant name, never the release.
*/}}
{{- define "edc.irBase" -}}
{{- printf "http://ds-identity-registry-%s.%s.svc.cluster.local:30005" .Values.participant.name .Release.Namespace -}}
{{- end -}}

{{- define "edc.connectorService" -}}
{{- .Values.connectorServiceName | default (printf "ds-connector-%s" .Values.participant.name) -}}
{{- end -}}
