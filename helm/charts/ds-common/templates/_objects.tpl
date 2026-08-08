{{/*
================================================================================
Fully-generic objects — identical across every service chart. Each chart ships a
one-line templates/*.yaml that includes these, so the shapes live in one place.
================================================================================
*/}}

{{- define "ds.service" -}}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "ds.fullname" . }}
  labels:
    {{- include "ds.labels" . | nindent 4 }}
spec:
  # ClusterIP always. Anything public is a path-scoped Ingress, never the Service.
  type: ClusterIP
  ports:
    - name: http
      port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
  selector:
    {{- include "ds.selectorLabels" . | nindent 4 }}
{{- end -}}

{{/*
The scrape instruction, paired with `ds.networkPolicy.metricsFromPrometheus`.

**Both halves or neither.** The NetworkPolicy opens the port to the monitoring namespace and
this tells Prometheus the port is there; either alone is inert, and the failure modes are
asymmetric. A policy with no ServiceMonitor is what this platform shipped until now — the
flag opened a network path and nothing walked through it, so `global.monitoring.serviceMonitor=true`
produced no metrics and no error. A ServiceMonitor with no policy is the inverse and at least
fails visibly, as `ds-provenance` did before its policy was added.

Gated on the same flag as the policy, so with chart defaults neither is rendered. The flag
means "this cluster runs a Prometheus that scrapes us"; it is off by default because a
ServiceMonitor referencing a CRD the cluster does not have is a failed install.

`/metrics` is unauthenticated on every ds service, deliberately — a scraper holds no Keycloak
token, so a bearer guard would replace a working control with a broken one. Reachability is
the control: the endpoint is in no chart's Ingress. See
docs/rulebook/provenance-and-logging.md step 1.

Args: the chart context ($).
*/}}
{{- define "ds.serviceMonitor" -}}
{{- if and ((.Values.global).monitoring).serviceMonitor }}
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "ds.fullname" . }}
  labels:
    {{- include "ds.labels" . | nindent 4 }}
    {{- with ((.Values.global).monitoring).labels }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
spec:
  selector:
    matchLabels:
      {{- include "ds.selectorLabels" . | nindent 6 }}
  namespaceSelector:
    matchNames:
      - {{ .Release.Namespace }}
  endpoints:
    # `port` is the Service port *name* — `http`, from `ds.service` — not a number.
    # A ServiceMonitor naming a port that does not exist scrapes nothing and says
    # nothing, which is the same silence this object exists to end.
    - port: http
      path: /metrics
      interval: {{ ((.Values.global).monitoring).interval | default "30s" }}
      scheme: http
{{- end }}
{{- end -}}

{{- define "ds.serviceAccount" -}}
{{- if .Values.serviceAccount.create }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "ds.serviceAccountName" . }}
  labels:
    {{- include "ds.labels" . | nindent 4 }}
# The service never calls the Kubernetes API; a mounted token would be a
# credential with no purpose and a real blast radius.
automountServiceAccountToken: false
{{- end }}
{{- end -}}

{{- define "ds.pdb" -}}
{{- if gt (int .Values.replicaCount) 1 }}
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "ds.fullname" . }}
  labels:
    {{- include "ds.labels" . | nindent 4 }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      {{- include "ds.selectorLabels" . | nindent 6 }}
{{- end }}
{{- end -}}

{{/*
ExternalSecret CR. Emitted instead of a Secret when
global.externalSecrets.enabled and no existingSecret is set. The chart declares
WHICH keys it needs and where they live; it never carries their values.

Args: dict "ctx" $ "remoteKey" <path in the store>
      "keys" (list of dict "secretKey" <k8s key> "property" <property in store>)
*/}}
{{- define "ds.externalSecret" -}}
{{- $ctx := .ctx -}}
{{- if and (($ctx.Values.global).externalSecrets).enabled (not $ctx.Values.existingSecret) }}
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {{ include "ds.fullname" $ctx }}
  labels:
    {{- include "ds.labels" $ctx | nindent 4 }}
spec:
  refreshInterval: {{ (($ctx.Values.global).externalSecrets).refreshInterval | default "1h" }}
  secretStoreRef:
    {{- toYaml (($ctx.Values.global).externalSecrets).secretStoreRef | nindent 4 }}
  target:
    name: {{ include "ds.fullname" $ctx }}
    creationPolicy: Owner
  data:
{{- $prefix := (($ctx.Values.global).externalSecrets).remotePrefix | default "dataspace" }}
{{- range .keys }}
    - secretKey: {{ .secretKey }}
      remoteRef:
        key: {{ printf "%s/%s" $prefix $.remoteKey }}
        property: {{ .property }}
{{- end }}
{{- end }}
{{- end -}}
