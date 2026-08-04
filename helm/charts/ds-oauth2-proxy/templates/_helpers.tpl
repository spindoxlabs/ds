{{/*
The proxy is served on the *portal's* host under /oauth2, not on a host of its
own. One host means one cookie domain and one redirect URI to register, and the
sign-in round trip never leaves the origin the user is already on.
*/}}
{{- define "oauth2proxy.host" -}}
{{- printf "%s.%s" (((.Values.global).hosts).portal | default "portal") (.Values.global).baseDomain -}}
{{- end -}}

{{/*
No `oauth2proxy.authUrl` / `oauth2proxy.signinUrl` helpers.

They were defined here and called by nothing. The two annotations they look like
they serve live on the **portal's** Ingress, in a different release — a helper in
this chart is not in scope there, so `ds-portal` builds both URLs itself from
`auth.proxy.authUrl` / `.signinUrl` (empty → derived). Two definitions of one URL,
one of them unreachable, is how the two drift.
*/}}
