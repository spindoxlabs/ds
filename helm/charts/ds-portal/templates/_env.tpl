{{/*
Portal environment. The portal is SSR — these upstreams are called server-side,
never from the browser, so they use in-cluster DNS. Sibling releases follow
ds-<service>-<participant>.
*/}}
{{- define "portal.origin" -}}
{{- printf "https://%s.%s" (((.Values.global).hosts).portal | default "portal") (.Values.global).baseDomain -}}
{{- end -}}

{{- define "portal.env" -}}
{{- $p := .Values.participant.name -}}
{{- include "ds.env.common" . }}
- name: ORIGIN
  value: {{ include "portal.origin" . | quote }}
# Server-side upstreams (in-cluster).
- name: CONNECTOR_URL
  value: {{ printf "http://ds-connector-%s:30001" $p | quote }}
- name: PROVENANCE_URL
  value: {{ printf "http://ds-provenance-%s:30000" $p | quote }}
- name: FEDERATED_CATALOG_URL
  value: {{ printf "http://ds-federated-catalog-%s:30003" $p | quote }}
- name: IDENTITY_REGISTRY_URL
  value: {{ printf "http://ds-identity-registry.%s.svc.cluster.local:30005" ((.Values.global).namespaces).authority | quote }}
# This participant's own registry, in its own namespace: the credentials of the
# people it onboarded are held here, not at the anchor (`DID-11` step 2).
- name: PARTICIPANT_IDENTITY_REGISTRY_URL
  value: {{ printf "http://ds-identity-registry-%s:30005" $p | quote }}
# Whose people that registry is custodian for. Asking it about a person filed
# under another organisation returns a truthful "I hold nothing", and treating
# that as authoritative logs them out (`DID-11` step 2).
- name: PARTICIPANT_DID
  value: {{ .Values.participant.did | default (printf "did:web:%s.%s" $p (.Values.global).baseDomain) | quote }}
{{- if .Values.datasetApi.url }}
- name: CATALOGUE_URL
  value: {{ .Values.datasetApi.url | quote }}
{{- end }}
# Consumer-side wiring. Without these the portal falls back to the compose
# host-gateway convention (172.17.0.1), which does not resolve in-cluster.
- name: CONSUMER_CONNECTOR_URL
  value: {{ .Values.consumer.connectorUrl | default (printf "http://ds-connector-%s:30001" $p) | quote }}
- name: CONSUMER_PARTICIPANT_DID
  value: {{ include "ds.participantDid" . | quote }}
{{- if .Values.consumer.defaultAssigner }}
- name: CONSUMER_DEFAULT_ASSIGNER
  value: {{ .Values.consumer.defaultAssigner | quote }}
{{- end }}
{{- if .Values.consumer.defaultCounterPartyAddress }}
- name: CONSUMER_DEFAULT_COUNTER_PARTY_ADDRESS
  value: {{ .Values.consumer.defaultCounterPartyAddress | quote }}
{{- end }}
# Login is oauth2-proxy's, not the portal's. The portal stopped being a
# confidential OIDC client — no AUTH_SECRET, no client secret, no callback
# registration — and reads the access token the proxy forwards as
# `X-Auth-Request-Access-Token`. This value is only where the browser is sent to
# start or end a session; the ds-oauth2-proxy release serves it on this host.
- name: OAUTH2_PROXY_BASE_URL
  value: {{ include "portal.origin" . | quote }}
# The proxy's Keycloak client, needed only by sign-out (`REV-04`): the portal
# sends the browser to the realm's `end_session` endpoint and Keycloak validates
# `post_logout_redirect_uri` against the client named there. It is the **proxy's**
# client, so it must match `auth.clientId` on the `ds-oauth2-proxy` release — a
# cross-chart constant, for the same reason `auth.proxy.port` is one. Getting it
# wrong is visible: Keycloak refuses the logout with an invalid-redirect page
# instead of failing silently.
- name: OAUTH2_PROXY_CLIENT_ID
  value: {{ .Values.auth.proxy.clientId | default "oauth2_proxy" | quote }}
# The realm issuer. The portal verifies every forwarded access token's signature
# against this issuer's JWKS (`hooks.server.ts` → `lib/server/token.ts`) and
# requests its service token from it — with no in-code fallback, so an unset
# value fails loudly rather than silently redirecting every VC-gated route to
# `/`. Same source as every other ds service.
- name: KEYCLOAK_ISSUER_URL
  value: {{ ((.Values.global).keycloak).issuerUrl | quote }}
# Layer B group aliases, from the one `global.keycloak.aliases` block every
# service reads — so the portal's nav and guards translate a foreign realm's
# group names exactly as the API does.
{{- include "ds.env.aliases" (dict "ctx" . "prefix" "PORTAL_") }}
- name: PORTAL_SERVICE_CLIENT_ID
  value: {{ .Values.auth.serviceClientId | quote }}
- name: PORTAL_SERVICE_CLIENT_SECRET
  valueFrom:
    secretKeyRef: {name: {{ include "ds.secretName" . }}, key: PORTAL_SERVICE_CLIENT_SECRET}
{{- include "ds.env.extra" . }}
{{- end -}}
