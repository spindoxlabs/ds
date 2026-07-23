{{/*
The identity-registry environment, shared by the main container and every init
container (migrations and bootstrap both need the database URL).

Order matters: DB_USER and DB_PASSWORD are declared before the URL that
interpolates them with $(VAR). The password never appears in a ConfigMap or in
a rendered URL string.
*/}}
{{- define "ir.env" -}}
{{- include "ds.env.common" . }}
- name: DB_USER
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: DB_USER
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: DB_PASSWORD
- name: IDENTITY_REGISTRY_DATABASE_URL
  value: {{ include "ds.postgres.url" (dict "ctx" . "database" (((.Values.global).postgres).databases).identityRegistry "driver" "asyncpg") | quote }}
- name: IDENTITY_REGISTRY_ENCRYPTION_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: IDENTITY_REGISTRY_ENCRYPTION_KEY
- name: IDENTITY_REGISTRY_TRUST_ANCHOR_DOMAIN
  value: {{ include "ir.trustAnchorDomain" . | quote }}
- name: IDENTITY_REGISTRY_CREDENTIALS_CONTEXT_URL
  value: {{ .Values.credentialsContextUrl | default (printf "https://%s/ns/credentials/v1" (.Values.global).baseDomain) | quote }}
- name: IDENTITY_REGISTRY_DATASPACE_URI
  value: {{ .Values.dataspaceUri | default (printf "https://%s/dataspace" (.Values.global).baseDomain) | quote }}
- name: IDENTITY_REGISTRY_DEFAULT_CREDENTIAL_TTL_DAYS
  value: {{ .Values.credentialTtl.defaultDays | quote }}
- name: IDENTITY_REGISTRY_MAX_CREDENTIAL_TTL_DAYS
  value: {{ .Values.credentialTtl.maxDays | quote }}
{{/*
Setting the issuer is what makes ds_auth verify signature, audience and issuer
via JWKS. With DS_ENV=production the ProductionGuard refuses to start without
it, and the insecure-dev flag is pinned false rather than merely defaulted.
*/}}
- name: IDENTITY_REGISTRY_OIDC_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: IDENTITY_REGISTRY_OIDC_INSECURE_DEV
  value: "false"
- name: KEYCLOAK_ADMIN_URL
  value: {{ ((.Values.global).keycloak).adminUrl | quote }}
- name: KEYCLOAK_CLIENT_ID
  value: {{ .Values.keycloak.clientId | quote }}
- name: KEYCLOAK_CLIENT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ include "ds.secretName" . }}
      key: KEYCLOAK_CLIENT_SECRET
{{- include "ds.env.extra" . }}
{{- end -}}

{{- define "ir.trustAnchorDomain" -}}
{{- if .Values.trustAnchorDomain -}}
{{- .Values.trustAnchorDomain -}}
{{- else -}}
{{- printf "%s.%s" (((.Values.global).hosts).trustAnchor | default "trust-anchor") (.Values.global).baseDomain -}}
{{- end -}}
{{- end -}}

{{- define "ir.usersHost" -}}
{{- printf "%s.%s" (((.Values.global).hosts).users | default "users") (.Values.global).baseDomain -}}
{{- end -}}
