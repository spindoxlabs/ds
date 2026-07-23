{{- define "prov.env" -}}
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
- name: PROVENANCE_DATABASE_URL
  value: {{ include "ds.postgres.url" (dict "ctx" . "database" (include "ds.db.provenance" .) "driver" "asyncpg") | quote }}
- name: PROVENANCE_BASE_URL
  value: {{ printf "http://%s:%v" (include "ds.fullname" .) .Values.service.port | quote }}
- name: PROVENANCE_MAX_LINEAGE_DEPTH
  value: {{ .Values.maxLineageDepth | quote }}
- name: PROVENANCE_OIDC_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
- name: PROVENANCE_OIDC_INSECURE_DEV
  value: "false"
{{- include "ds.env.extra" . }}
{{- end -}}
