{{/*
================================================================================
ds-common — naming
================================================================================
*/}}

{{- define "ds.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ds.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "ds.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ds.labels" -}}
helm.sh/chart: {{ include "ds.chart" . }}
{{ include "ds.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: dataspace
{{- if .Values.participant }}
dataspace.spindoxlabs.io/participant: {{ .Values.participant.name | quote }}
dataspace.spindoxlabs.io/role: {{ .Values.participant.role | quote }}
{{- end }}
{{- end -}}

{{- define "ds.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ds.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "ds.serviceAccountName" -}}
{{- default (include "ds.fullname" .) .Values.serviceAccount.name -}}
{{- end -}}

{{/*
================================================================================
Images — ghcr.io/spindoxlabs/ds-<service>
Digest wins over tag when both are set.
================================================================================
*/}}

{{- define "ds.image" -}}
{{- $g := (.Values.global).image | default dict -}}
{{- $i := .Values.image | default dict -}}
{{- $registry := $i.registry | default $g.registry | default "ghcr.io/spindoxlabs" -}}
{{- $prefix := $g.prefix | default "ds-" -}}
{{- $repo := $i.repository | default (printf "%s%s" $prefix .Values.service.name) -}}
{{- if $i.digest -}}
{{- printf "%s/%s@%s" $registry $repo $i.digest -}}
{{- else -}}
{{- $tag := $i.tag | default $g.tag | default .Chart.AppVersion -}}
{{- printf "%s/%s:%s" $registry $repo $tag -}}
{{- end -}}
{{- end -}}

{{- define "ds.imagePullPolicy" -}}
{{- .Values.image.pullPolicy | default ((.Values.global).image).pullPolicy | default "IfNotPresent" -}}
{{- end -}}

{{- define "ds.imagePullSecrets" -}}
{{- $secrets := .Values.imagePullSecrets | default ((.Values.global).image).pullSecrets -}}
{{- with $secrets }}
imagePullSecrets:
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
================================================================================
Security context

runAsUser is set explicitly and MUST be numeric: kubelet cannot verify
runAsNonRoot against an image whose USER is a name, and refuses to start the
container. The images pin uid 10001 — see the Dockerfile of each service.
================================================================================
*/}}

{{- define "ds.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: {{ .Values.podSecurityContext.runAsUser | default 10001 }}
runAsGroup: {{ .Values.podSecurityContext.runAsGroup | default 10001 }}
fsGroup: {{ .Values.podSecurityContext.fsGroup | default 10001 }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "ds.containerSecurityContext" -}}
allowPrivilegeEscalation: false
privileged: false
readOnlyRootFilesystem: {{ .Values.containerSecurityContext.readOnlyRootFilesystem | default true }}
capabilities:
  drop:
    - ALL
{{- end -}}

{{/*
================================================================================
Environment

DS_ENV=production is a CONSTANT of these charts, not a value. It is the single
switch that turns every service's ProductionGuard from warn-only into
fail-closed (libs/ds-auth/src/ds_auth/production.py). Do not make it
configurable — an omitted or downgraded DS_ENV is exactly the failure mode the
guard exists to prevent.
================================================================================
*/}}

{{- define "ds.env.common" -}}
- name: DS_ENV
  value: production
- name: POD_NAMESPACE
  valueFrom:
    fieldRef:
      fieldPath: metadata.namespace
{{- end -}}

{{/*
Extra plain env from .Values.env (map form).
*/}}
{{- define "ds.env.extra" -}}
{{- range $k, $v := .Values.env }}
{{- if not (empty $v) }}
- name: {{ $k }}
  value: {{ $v | quote }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
================================================================================
Secrets

Three modes, one call site:
  existingSecret set              → reference it, create nothing
  global.externalSecrets.enabled  → an ExternalSecret CR produces it
  otherwise                       → this chart renders a Secret from values
================================================================================
*/}}

{{- define "ds.secretName" -}}
{{- if .Values.existingSecret -}}
{{- .Values.existingSecret -}}
{{- else -}}
{{- include "ds.fullname" . -}}
{{- end -}}
{{- end -}}

{{/* True when this chart is responsible for creating the Secret object. */}}
{{- define "ds.createSecret" -}}
{{- if .Values.existingSecret -}}
false
{{- else if ((.Values.global).externalSecrets).enabled -}}
false
{{- else -}}
true
{{- end -}}
{{- end -}}

{{/*
================================================================================
Database

The password never lands in a ConfigMap or a rendered URL. DB_USER/DB_PASSWORD
come from the Secret and Kubernetes interpolates them into the URL with $(VAR).

Args: dict "ctx" $ "database" <name> "driver" <asyncpg|jdbc>
================================================================================
*/}}

{{- define "ds.postgres.url" -}}
{{- $pg := (.ctx.Values.global).postgres -}}
{{- if eq (.driver | default "asyncpg") "jdbc" -}}
jdbc:postgresql://{{ $pg.host }}:{{ $pg.port }}/{{ .database }}?sslmode={{ $pg.sslMode | default "require" }}
{{- else -}}
postgresql+asyncpg://$(DB_USER):$(DB_PASSWORD)@{{ $pg.host }}:{{ $pg.port }}/{{ .database }}?ssl={{ $pg.sslMode | default "require" }}
{{- end -}}
{{- end -}}

{{/*
================================================================================
Public addressing — every public host is a subdomain of global.baseDomain
================================================================================
*/}}

{{/* Args: dict "ctx" $ "sub" <string> */}}
{{- define "ds.publicHost" -}}
{{- printf "%s.%s" .sub (.ctx.Values.global).baseDomain -}}
{{- end -}}

{{/* The participant's public host — also its did:web identity. */}}
{{- define "ds.participantHost" -}}
{{- printf "%s.%s" .Values.participant.name (.Values.global).baseDomain -}}
{{- end -}}

{{- define "ds.participantDid" -}}
{{- if .Values.participant.did -}}
{{- .Values.participant.did -}}
{{- else -}}
{{- printf "did:web:%s" (include "ds.participantHost" .) -}}
{{- end -}}
{{- end -}}

{{/*
Participant-scoped database names — <prefix>_<participant>, matching the roles
provisioned in docs/cnpg-cluster.example.yaml. One helper per service so the
naming lives in exactly one place.
*/}}
{{- define "ds.db.connector" -}}
{{- printf "%s_%s" ((((.Values.global).postgres).databases).connectorPrefix | default "connector") .Values.participant.name -}}
{{- end -}}

{{- define "ds.db.provenance" -}}
{{- printf "%s_%s" ((((.Values.global).postgres).databases).provenancePrefix | default "provenance") .Values.participant.name -}}
{{- end -}}

{{- define "ds.db.edc" -}}
{{- printf "%s_%s" ((((.Values.global).postgres).databases).edcPrefix | default "edc") .Values.participant.name -}}
{{- end -}}

{{/*
TLS block for an Ingress.

The secret name is derived from the HOST, not from the Ingress object: a host
served by several Ingress objects (different rewrite behaviours need different
objects) must share one certificate, or cert-manager issues duplicates that
fight over the same secret.

Args: dict "ctx" $ "hosts" (list)
*/}}
{{- define "ds.ingress.tls" -}}
{{- $tls := ((.ctx.Values.global).ingress).tls | default dict -}}
tls:
  - hosts:
{{- range .hosts }}
      - {{ . | quote }}
{{- end }}
    secretName: {{ $tls.secretName | default (printf "tls-%s" (first .hosts | replace "." "-")) }}
{{- end -}}

{{/*
Ingress annotations.

issueCert must be true on exactly ONE Ingress object per host. cert-manager
creates a Certificate per annotated Ingress, so annotating several objects that
share a host produces competing Certificates for one secret.

Args: dict "ctx" $ "issueCert" <bool>
*/}}
{{- define "ds.ingress.annotations" -}}
{{- $ing := (.ctx.Values.global).ingress | default dict -}}
{{- $tls := $ing.tls | default dict -}}
{{- if and .issueCert $tls.clusterIssuer (not $tls.secretName) }}
cert-manager.io/cluster-issuer: {{ $tls.clusterIssuer | quote }}
{{- end }}
nginx.ingress.kubernetes.io/ssl-redirect: "true"
nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
{{- with $ing.annotations }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{/*
================================================================================
Probes — every Python service serves /health on its own port; the portal
answers on /.
================================================================================
*/}}

{{- define "ds.probes" -}}
{{- $path := .Values.service.healthPath | default "/health" -}}
livenessProbe:
  httpGet:
    path: {{ $path }}
    port: http
  initialDelaySeconds: {{ .Values.probes.livenessInitialDelay | default 20 }}
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 6
readinessProbe:
  httpGet:
    path: {{ $path }}
    port: http
  initialDelaySeconds: {{ .Values.probes.readinessInitialDelay | default 5 }}
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
{{- end -}}

{{- define "ds.resources" -}}
{{- $r := .Values.resources | default (.Values.global).resources -}}
{{- with $r }}
resources:
{{ toYaml . | indent 2 }}
{{- end }}
{{- end -}}

{{/*
================================================================================
readOnlyRootFilesystem needs somewhere writable. Every service gets /tmp.
================================================================================
*/}}

{{- define "ds.tmpVolume" -}}
- name: tmp
  emptyDir: {}
{{- end -}}

{{- define "ds.tmpVolumeMount" -}}
- name: tmp
  mountPath: /tmp
{{- end -}}
