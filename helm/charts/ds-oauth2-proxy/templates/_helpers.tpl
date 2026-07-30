{{/*
The proxy is served on the *portal's* host under /oauth2, not on a host of its
own. One host means one cookie domain and one redirect URI to register, and the
sign-in round trip never leaves the origin the user is already on.
*/}}
{{- define "oauth2proxy.host" -}}
{{- printf "%s.%s" (((.Values.global).hosts).portal | default "portal") (.Values.global).baseDomain -}}
{{- end -}}

{{/*
The in-cluster URL nginx calls as an auth subrequest, and the public URL it
redirects an unauthenticated browser to.
*/}}
{{- define "oauth2proxy.authUrl" -}}
{{- printf "http://%s.%s.svc.cluster.local:%v/oauth2/auth" (include "ds.fullname" .) .Release.Namespace .Values.service.port -}}
{{- end -}}

{{- define "oauth2proxy.signinUrl" -}}
{{- printf "https://%s/oauth2/start?rd=$escaped_request_uri" (include "oauth2proxy.host" .) -}}
{{- end -}}
