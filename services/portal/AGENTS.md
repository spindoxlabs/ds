# ds-portal

SvelteKit web front end for every participant role. Port 30004 (debug 30904), reached at
`http://portal.dataspaces.localhost`.

**Not an OIDC client.** oauth2-proxy holds the browser session behind Caddy `forward_auth`
and forwards the access token as `X-Auth-Request-Access-Token`; `hooks.server.ts` builds the
session per request. The header is transport, never authority — Caddy strips client-supplied
copies and every ds service re-verifies the JWT.

## References

| | |
|---|---|
| Requirements | [DSSC · Cross-cutting (personal data, natural persons)](../../docs/blueprints/dssc/cross-cutting.md) · [DSSC · Publication and Discovery](../../docs/blueprints/dssc/data-value-creation-enablers/publication-and-discovery.md) |
| Rules | [Rulebook · Personal data](../../docs/rulebook/personal-data.md) · [Rulebook · Participation and trust](../../docs/rulebook/participation.md) |
| Code as committed | [docs/services/portal.md](../../docs/services/portal.md) |

## Where to work

| Task | Start at |
|---|---|
| New page | `src/routes/<path>/+page.svelte` + `+page.server.ts` |
| Navigation | `src/routes/+layout.svelte` |
| Route guard, grants | `src/lib/server/auth.ts` (server) · `src/lib/stores/session.ts` (display only) |
| Call a backend | `src/lib/server/{connector,provenance,identity-registry}.ts` |
| ODRL rendering | `src/lib/server/odrl.ts` — `summarisePolicy()` |
| What a subject is asked | `src/routes/my-data/` + `getSharingOffers()` |
| Operator onboarding | `src/routes/admin/onboarding/` |

Environment variables are documented in `.env.example`, not here. **The in-code fallbacks
are a last resort, not the dev config** — a stale participant DID fails a negotiation with no
useful error.

## Rules that are not visible from the code

- **A `+server.ts` endpoint does not run `+layout.server.ts`.** It must guard itself. Four
  standalone consumer endpoints currently do not — see `.agents/defect-per-service.md`.
- **Authority arrives on two independent axes and they are not exclusive.** Keycloak groups
  (bundles, expanded by `bundles.generated.ts`) carry operator and provider authority; a
  verifiable credential carries `ConsumerUser` / `DataSubject`. One human legitimately holds
  several. Always `hasVcRole(session, …)`, never `session.userVcRole === …`; present the
  credential the call requires with `vcJwsForRole(session, role)`. There is no admin bypass
  on the VC axis — an operator who must act as a consumer needs a credential issued.
- **Gate with `hasGrant` / `requireGrant`**, which mirror `ds_auth.permissions.grant_satisfies`
  including the `{service}.admin` superset. A portal gating on different rules than the API
  either hides what the user may do or offers what the API will refuse.
- **A denied route fails with an explanation, not a redirect.** A silent bounce to `/` is
  indistinguishable from a broken page.
- **Never hardcode a purpose.** Pass what the offer declares, or nothing; the connector
  returns 422 for anything outside the taxonomy. Hardcoded labels once meant Pydantic
  silently dropped every declaration a person made while the UI implied it was recorded —
  **a choice the backend discards is worse than no choice.**
- **Only consent-based offers get a control.** Contract-based processing renders as
  disclosure; the connector returns 409 if you try to toggle it.
- **The subject timeline renders sentences, not codes** — it is read by the person the data
  is about, and it is the one view authenticated by a credential rather than a scope.
- **`ds` serves codes; the portal renders sentences.** `fallback_text_en` is the server-side
  English safety net so an unmapped code degrades to readable text.
- **`counter_party_address` is an identity, not a route.** It must equal the value registered
  as that participant's `dsp_address`; a perfectly reachable address that is not registered
  is still a `400 Unknown dataspace participant`. "I can curl it" is not evidence.

## Conventions

Svelte 5 runes. Mobile-first Tailwind. SSR — never call a backend from a browser component.

## Testing

```bash
task -d services/portal check        # svelte-check
npm run build                        # ALSO run this
task -d services/portal test:ui      # Playwright journeys (needs the stack up)
```

**`task check` is not sufficient.** `svelte-check` does not enforce SvelteKit's
server/client boundary: importing a *value* from `$lib/server/…` into a component typechecks
and then fails the production build. Run `npm run build` before considering a change done.

UI journeys sign in through the real Keycloak form, assert on API effects rather than DOM
cosmetics (a decision that survives a `reload()` is evidence the connector wrote it), and run
`workers: 1` because they mutate shared backend state. There is no `webServer` — `global-setup.ts`
fails fast if the stack is not running. New journeys should follow the same three rules.

**Regenerate `package-lock.json` inside the build image** after a dependency change — a
plain `npm install` on a glibc host prunes the musl-only optional deps and only the Docker
build breaks:

```bash
docker run --rm -v "$PWD":/w -w /w node:22-alpine \
  sh -c 'npm install --package-lock-only --include=optional'
```
