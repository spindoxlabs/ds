{{/*
================================================================================
`helm test` — the local doctor's chart-owned rows, on a cluster
(chart parity Phase 4).

Each test Pod asserts **content**, not status: the DID document's `id`, the
catalogue's size against the governance, `/join` answering without a session.
A status-only check is what let an empty catalogue stay green for a fortnight.

**Image.** The ds-connector image of the same release — Python and `httpx`,
already pulled for every participant — so no third-party image enters the
deployment for a test.

**Labels.** The chart's `app.kubernetes.io/name` (so a `fromWorkloads` rule that
admits this chart admits its test) and an instance of `<release>-test`, so the
release's own default-deny, which selects name **and** instance, does not select
it: a test Pod refused by the policy it is testing past fails for the wrong
reason.

**TLS.** `tests.tlsVerify` (default true). A rehearsal cluster with a local CA
sets it false explicitly; nothing turns it off by omission.
================================================================================
*/}}

{{- define "ds.testImage" -}}
{{- $g := (.Values.global).image | default dict -}}
{{- $t := .Values.tests | default dict -}}
{{- $registry := $g.registry | default "ghcr.io/spindoxlabs" -}}
{{- $prefix := $g.prefix | default "ds-" -}}
{{- $tag := $t.imageTag | default $g.tag | default .Chart.AppVersion -}}
{{- printf "%s/%sconnector:%s" $registry $prefix $tag -}}
{{- end -}}

{{/*
Args: dict "ctx" $ "name" <suffix> "script" <python> "env" (list of env items)
      optional "volumes" "volumeMounts" (lists)
*/}}
{{- define "ds.testPod" -}}
{{- $ctx := .ctx -}}
{{- $t := $ctx.Values.tests | default dict -}}
apiVersion: v1
kind: Pod
metadata:
  name: {{ printf "%s-test-%s" (include "ds.fullname" $ctx) .name | trunc 63 | trimSuffix "-" }}
  labels:
    helm.sh/chart: {{ include "ds.chart" $ctx }}
    app.kubernetes.io/name: {{ include "ds.name" $ctx }}
    app.kubernetes.io/instance: {{ printf "%s-test" $ctx.Release.Name | trunc 63 | trimSuffix "-" }}
    app.kubernetes.io/component: test
    app.kubernetes.io/managed-by: {{ $ctx.Release.Service }}
    app.kubernetes.io/part-of: dataspace
  annotations:
    "helm.sh/hook": test
    # Kept after a failure, so `kubectl logs` can say why; replaced on the next run.
    "helm.sh/hook-delete-policy": before-hook-creation
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  {{- include "ds.imagePullSecrets" $ctx | nindent 2 }}
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: test
      image: {{ include "ds.testImage" $ctx }}
      imagePullPolicy: {{ include "ds.imagePullPolicy" $ctx }}
      command: ["python", "-c", {{ .script | quote }}]
      env:
        - name: TEST_TLS_VERIFY
          value: {{ ternary "true" "false" (ne (toString $t.tlsVerify) "false") | quote }}
        {{- with .env }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      securityContext:
        allowPrivilegeEscalation: false
        privileged: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      {{- with .volumeMounts }}
      volumeMounts:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      resources:
        requests: {cpu: 50m, memory: 64Mi}
        limits: {memory: 256Mi}
  {{- with .volumes }}
  volumes:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end -}}
