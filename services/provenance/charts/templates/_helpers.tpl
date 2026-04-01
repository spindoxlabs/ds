{{/*
Expand the name of the chart.
*/}}
{{- define "provenance.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "provenance.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "provenance.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "provenance.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "provenance.selectorLabels" -}}
app.kubernetes.io/name: {{ include "provenance.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Database secret name (from postgresql subchart or external)
*/}}
{{- define "provenance.dbSecretName" -}}
{{- if .Values.postgresql.enabled -}}
{{ include "provenance.fullname" . }}-postgresql
{{- else -}}
{{ include "provenance.fullname" . }}-db
{{- end -}}
{{- end }}
