{{/* Volume mounts shared by the connector's init and main containers. */}}
{{- define "conn.volumeMounts" -}}
{{- include "ds.tmpVolumeMount" . }}
{{- if include "conn.servesEdrKey" . }}
- name: edr-verification
  mountPath: {{ .Values.edr.mountPath }}
  readOnly: true
{{- end }}
{{- if include "conn.governanceConfigMap" . }}
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

{{/*
ds3: the governance ConfigMap this connector mounts. `governance.files` (key →
content, the deployment's assembled governance) is rendered by this chart as
`<release>-governance`, with a digest of it as checksum/governance;
`governance.configMap` names one the operator made, with `governance.checksum`
its hand digest. One source: files with either of the two is a render error.
*/}}
{{- define "conn.governanceConfigMap" -}}
{{- $g := .Values.governance -}}
{{- if $g.files -}}
{{- if $g.configMap -}}
{{- fail "ds-connector: governance.files and governance.configMap are both set — the chart renders the governance ConfigMap from files, so leave configMap empty (or drop files to mount your own)" -}}
{{- end -}}
{{- if $g.checksum -}}
{{- fail "ds-connector: governance.files and governance.checksum are both set — with files the chart computes the digest from the content; drop checksum" -}}
{{- end -}}
{{- printf "%s-governance" (include "ds.fullname" .) -}}
{{- else -}}
{{- $g.configMap -}}
{{- end -}}
{{- end -}}

{{- define "conn.governanceChecksum" -}}
{{- if .Values.governance.files -}}
{{- toJson .Values.governance.files | sha256sum -}}
{{- else -}}
{{- .Values.governance.checksum -}}
{{- end -}}
{{- end -}}
