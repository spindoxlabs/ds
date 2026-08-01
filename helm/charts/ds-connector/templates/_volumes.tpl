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
{{- if .Values.vocabularies.configMap }}
- name: vocabularies
  mountPath: {{ .Values.vocabularies.mountPath }}
  readOnly: true
{{/*
The cache is read-only only when the operator supplied the copies. With an
emptyDir the startup loader writes into it, so it must not be marked readOnly —
and the pod would crash-loop on a mount it cannot write rather than on the
fetch failure it is actually reporting.
*/}}
- name: vocabulary-cache
  mountPath: {{ .Values.vocabularies.cache.mountPath }}
  readOnly: {{ ne .Values.vocabularies.cache.configMap "" }}
{{- end }}
{{- end -}}
