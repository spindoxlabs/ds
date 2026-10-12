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
        {{- include "ds.networkPolicy.dnsTo" . | nindent 8 }}
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
{{- with (include "ds.networkPolicy.tracingEgress" .) }}
    {{- . | nindent 4 }}
{{- end }}
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
/metrics is unauthenticated on every ds service, deliberately: a Prometheus
scraper holds no Keycloak token, so a bearer guard would replace a working
control with a broken one. Reachability is the control, and this is it — the
endpoint is in no chart's Ingress, the default-deny baseline applies, and this
rule opens the port to the monitoring namespace alone.

See docs/rulebook/provenance-and-logging.md step 1, which settled it. This
comment used to cite the root agent guide as recording "a known gap"; it never
mentioned /metrics, and "gap" is the wrong word for a decision.

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

{{/*
The DNS rule's peers: the `k8s-app: kube-dns` pods, then
`global.networkPolicy.dnsExtraTo`. A cluster whose pods resolve through a
node-local cache (NodeLocal DNSCache) lists that host-network address there as
an ipBlock, since no pod selector reaches it. An empty peer would admit every
address, so it fails the render.

Args: the chart's root context
*/}}
{{- define "ds.networkPolicy.dnsTo" -}}
- namespaceSelector: {}
  podSelector:
    matchLabels:
      k8s-app: kube-dns
{{- range $i, $peer := (((.Values.global).networkPolicy).dnsExtraTo | default list) }}
{{- if not $peer }}
{{- fail (printf "global.networkPolicy.dnsExtraTo[%d] is empty: an empty peer admits every address on port 53" $i) }}
{{- end }}
{{ list $peer | toYaml }}
{{- end }}
{{- end -}}

{{/*
Egress to the trace collector, when `global.tracing.endpoint` is set: one rule to the
peers in `global.tracing.egressTo`, on the endpoint's port. Empty when tracing is off.

**Without it, tracing is on and nothing arrives.** Every pod here is default-deny egress,
the exporter batches and drops rather than blocking a request, so a collector the policy
does not admit looks exactly like a quiet service. Hence the failures: an endpoint with
NetworkPolicies on and no peer, an empty peer (it admits every address), and an endpoint
without an explicit port (the rule would have to guess one).
*/}}
{{- define "ds.networkPolicy.tracingEgress" -}}
{{- $t := (.Values.global).tracing | default dict }}
{{- if and $t.endpoint ((.Values.global).networkPolicy).enabled }}
{{- $port := regexFind "[0-9]+$" (regexFind ":[0-9]+$" (urlParse $t.endpoint).host) }}
{{- if not $port }}
{{- fail (printf "global.tracing.endpoint %q has no explicit port: the egress rule to the collector needs one (OTLP/HTTP is usually :4318)" $t.endpoint) }}
{{- end }}
{{- if not $t.egressTo }}
{{- fail "global.tracing.endpoint is set and NetworkPolicies are on, but global.tracing.egressTo is empty: every pod's egress is default-deny, so no span would reach the collector. List the collector's peers (e.g. a namespaceSelector and podSelector)" }}
{{- end }}
- to:
{{- range $i, $peer := $t.egressTo }}
{{- if not $peer }}
{{- fail (printf "global.tracing.egressTo[%d] is empty: an empty peer admits every address on the collector's port" $i) }}
{{- end }}
{{ list $peer | toYaml | indent 2 }}
{{- end }}
  ports:
    - protocol: TCP
      port: {{ $port }}
{{- end }}
{{- end -}}
