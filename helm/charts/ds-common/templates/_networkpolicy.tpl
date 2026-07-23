{{/*
================================================================================
NetworkPolicy — default deny, explicit allows only.

Kubernetes has no "deny" rule: a policy that selects a pod and lists no matching
peer denies everything else for that direction. So each service gets one
default-deny policy plus narrowly-scoped allow policies.

Egress allows are opt-in per chart via .Values.networkPolicy.egress. DNS is
always allowed — without it every outbound connection fails to resolve.
================================================================================
*/}}

{{- define "ds.networkPolicy.defaultDeny" -}}
{{- if ((.Values.global).networkPolicy).enabled }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "ds.fullname" . }}-default-deny
  labels:
    {{- include "ds.labels" . | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "ds.selectorLabels" . | nindent 6 }}
  policyTypes:
    - Ingress
    - Egress
  egress:
    # DNS is a prerequisite for every other egress rule below.
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    # PostgreSQL (CloudNativePG, external to these charts).
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 169.254.169.254/32 # cloud metadata endpoint
      ports:
        - protocol: TCP
          port: {{ ((.Values.global).postgres).port | default 5432 }}
{{- with .Values.networkPolicy.egress }}
{{ toYaml . | indent 4 }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
Allow ingress from the ingress-controller namespace. Used only by the charts
that actually publish a host (portal, identity-registry, edc).

Args: dict "ctx" $ "ports" (list of int)
*/}}
{{- define "ds.networkPolicy.fromIngressController" -}}
{{- if ((.ctx.Values.global).networkPolicy).enabled }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "ds.fullname" .ctx }}-from-ingress
  labels:
    {{- include "ds.labels" .ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "ds.selectorLabels" .ctx | nindent 6 }}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ ((.ctx.Values.global).ingress).controllerNamespace | default "ingress-nginx" }}
      ports:
{{- range .ports }}
        - protocol: TCP
          port: {{ . }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
Allow ingress from named workloads, in this namespace or another.

Args: dict "ctx" $ "ports" (list) "from" (list of dicts:
        {namespace: <ns>, name: <app.kubernetes.io/name value>})
*/}}
{{- define "ds.networkPolicy.fromWorkloads" -}}
{{- if ((.ctx.Values.global).networkPolicy).enabled }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "ds.fullname" .ctx }}-from-workloads
  labels:
    {{- include "ds.labels" .ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "ds.selectorLabels" .ctx | nindent 6 }}
  policyTypes:
    - Ingress
  ingress:
    - from:
{{- range .from }}
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ .namespace }}
          podSelector:
            matchLabels:
              app.kubernetes.io/name: {{ .name }}
{{- end }}
      ports:
{{- range .ports }}
        - protocol: TCP
          port: {{ . }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
/metrics is unauthenticated on ds-connector, ds-provenance and
ds-federated-catalog (see root AGENTS.md — a known gap, not a pattern).
It is never exposed through an Ingress; this restricts it to Prometheus.

Args: dict "ctx" $ "port" <int>
*/}}
{{- define "ds.networkPolicy.metricsFromPrometheus" -}}
{{- if and ((.ctx.Values.global).networkPolicy).enabled ((.ctx.Values.global).monitoring).serviceMonitor }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "ds.fullname" .ctx }}-metrics
  labels:
    {{- include "ds.labels" .ctx | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "ds.selectorLabels" .ctx | nindent 6 }}
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ ((.ctx.Values.global).monitoring).prometheusNamespace | default "monitoring" }}
      ports:
        - protocol: TCP
          port: {{ .port }}
{{- end }}
{{- end -}}
