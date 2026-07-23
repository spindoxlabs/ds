{{/* Volume mounts shared by the connector's init and main containers. */}}
{{- define "conn.volumeMounts" -}}
{{- include "ds.tmpVolumeMount" . }}
- name: edc-api-key
  mountPath: /run/secrets/edc
  readOnly: true
- name: trust-anchor
  mountPath: {{ dir .Values.trustAnchor.keyMountPath }}
  readOnly: true
{{- if .Values.governance.configMap }}
- name: governance
  mountPath: {{ .Values.governance.mountPath }}
  readOnly: true
{{- end }}
{{- end -}}
