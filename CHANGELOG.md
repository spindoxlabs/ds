# CHANGELOG

<!-- version list -->

## v0.6.0 (2026-10-19)

### Bug Fixes

- An agreement is recorded once whichever writer comes first, so the webhook keeps the shared DSP id
  ([`6ea3ca5`](https://github.com/spindoxlabs/ds/commit/6ea3ca5643f190204d703c12a04c30f870d948ae))

- Org apply onboards every organisation with a dataspace block, also when nothing is exposed
  ([`13f5ebe`](https://github.com/spindoxlabs/ds/commit/13f5ebe93907a5affc99d094b7eaf36855f92dda))

- Up lock
  ([`97e956f`](https://github.com/spindoxlabs/ds/commit/97e956f80d2b77a18ad1fe65fd25c375479ba2be))

### Chores

- Dev seeds name organization types rec, dso, org
  ([`cf45b45`](https://github.com/spindoxlabs/ds/commit/cf45b450b09f2f901d0526c0ddafa138f2928f64))

### Documentation

- Add X-17, an agreement does not lift an organization row filter
  ([`6e2b8f7`](https://github.com/spindoxlabs/ds/commit/6e2b8f70211f2453bde62f644fc1a2d2c825616b))

- Add X-18, the consumer's presented organization decides organization rows
  ([`a4db8eb`](https://github.com/spindoxlabs/ds/commit/a4db8eb4472d1427ed6567d15f7ad3bd17478638))

- Rule ids and plain reasons instead of external references
  ([`f044bcc`](https://github.com/spindoxlabs/ds/commit/f044bcca990a0424144fc6eb679b03806635116f))

### Features

- Allow_all/deny_all are layer verdicts, a malformed row filter is refused, validate runs the
  platform rules first
  ([`61ff792`](https://github.com/spindoxlabs/ds/commit/61ff79268f2d6ddeab833e96d27151b76b6bbf87))

- Force organization level filter on dataplane
  ([`5f82d43`](https://github.com/spindoxlabs/ds/commit/5f82d43c232b89809c24848a8677dfac6859d5c1))

- Org credential carries organizationId and organizationType; add org reissue cli
  ([`7e15c8b`](https://github.com/spindoxlabs/ds/commit/7e15c8bea8db31550cd7c1bd84bb57149380e000))

- Org reissue suspends the predecessor; holder omits its own retired credentials (P-30, P-31)
  ([`e38f73b`](https://github.com/spindoxlabs/ds/commit/e38f73b4c2f32a6b0c7a4821951519e6b01d3276))

- Organization credential as a DEFAULT DCP scope; the verdict carries the consumer's organization
  ([`3c7f07d`](https://github.com/spindoxlabs/ds/commit/3c7f07d295d323eb0cbb241b3e8882bb80c0a1df))

- Rules P-32, C-22, C-23, X-20 and ADR-0030; e2e flows for the organization layer and the reissue
  ([`8d2cfcf`](https://github.com/spindoxlabs/ds/commit/8d2cfcf30c738993b9bcf4b214f871715bf311cb))

- The dataplane verdict carries the consumer's organizations
  ([`b9691fc`](https://github.com/spindoxlabs/ds/commit/b9691fcb39b01342198c577cc73962ecab20895e))


## v0.5.0 (2026-10-16)

### Documentation

- Update sops secrets handling
  ([`a202a38`](https://github.com/spindoxlabs/ds/commit/a202a38b602975b7fa1f3797cc29a1638a4c7e5f))

### Features

- Add org reverify cli
  ([`bc6ed93`](https://github.com/spindoxlabs/ds/commit/bc6ed93535be1ccd96e1a98e13f7ed2116071fcb))


## v0.4.2 (2026-10-13)

### Bug Fixes

- Lower jaeger verbose reporting
  ([`9371ab3`](https://github.com/spindoxlabs/ds/commit/9371ab3228d8b8e9f60580724294199585688481))


## v0.4.1 (2026-10-13)

### Bug Fixes

- Add tracing on java services
  ([`aefc98c`](https://github.com/spindoxlabs/ds/commit/aefc98c01a3036372fd5f950c8b971e5664180e4))


## v0.4.0 (2026-10-12)

### Code Style

- Wrap the pre-ping tests and comments to the line length
  ([`c326d31`](https://github.com/spindoxlabs/ds/commit/c326d314f935973d184b5ba27e33ca3fd3b6f056))

### Features

- **helm**: Global.tracing.egressTo admits the trace collector from every default-deny policy; an
  endpoint without peers or a port fails the render
  ([`cc2c08a`](https://github.com/spindoxlabs/ds/commit/cc2c08aaa6eb284b2184492848cfbf4b13454ebb))


## v0.3.1 (2026-10-12)

### Bug Fixes

- **db**: The registry, connector and provenance engines pre-ping pooled connections (an IPVS
  kube-proxy drops idle TCP at 900 s)
  ([`1d0866c`](https://github.com/spindoxlabs/ds/commit/1d0866c49a5f047fe1e72facb09cfcc3d187a464))


## v0.3.0 (2026-10-12)

### Bug Fixes

- **portal**: Relock with npm 10 so npm ci on Node 22 accepts it
  ([`ad6d81d`](https://github.com/spindoxlabs/ds/commit/ad6d81d7b305763152d58c88c5b56ab43c1e8538))

### Features

- **helm**: Global.networkPolicy.dnsExtraTo admits a node-local DNS cache in every DNS egress rule
  ([`232eb9c`](https://github.com/spindoxlabs/ds/commit/232eb9ca6242dc5d3bac1ccbe61e100c90c80fc0))


## v0.2.0 (2026-10-11)

### Bug Fixes

- Update status
  ([`a5e8f5c`](https://github.com/spindoxlabs/ds/commit/a5e8f5c8a079ca5f3b9bf70505a27aa7d36cf2b0))

- **ci**: Lint, ds-auth org-client scopes; portal vite 8 + cytoscape-dagre 4. Closes #45, closes
  #46, closes #49
  ([`e10a746`](https://github.com/spindoxlabs/ds/commit/e10a746ee3601b0f55a8a0577a32522102766d05))

### Chores

- **deps**: Bump com.squareup.okhttp3:okhttp from 4.12.0 to 5.5.0
  ([#43](https://github.com/spindoxlabs/ds/pull/43),
  [`2561b38`](https://github.com/spindoxlabs/ds/commit/2561b386f9cf0b32e2f4b9e8553ec808158934cf))

- **deps**: Bump eclipse-temurin in /services/edc-connector
  ([#39](https://github.com/spindoxlabs/ds/pull/39),
  [`8425925`](https://github.com/spindoxlabs/ds/commit/84259254d7ff0b4c9180573302027a3f4f1f259b))

- **deps**: Bump jakarta.ws.rs:jakarta.ws.rs-api from 3.1.0 to 4.0.0
  ([#42](https://github.com/spindoxlabs/ds/pull/42),
  [`b29454a`](https://github.com/spindoxlabs/ds/commit/b29454adf4755163d2ccf11b5036ce356a0c536a))

- **deps**: Bump org.eclipse.parsson:parsson ([#41](https://github.com/spindoxlabs/ds/pull/41),
  [`ced15f0`](https://github.com/spindoxlabs/ds/commit/ced15f0e7759209ea55ea0b7aee52ad7483db248))

- **deps**: Bump org.junit:junit-bom from 5.10.2 to 6.1.3
  ([#48](https://github.com/spindoxlabs/ds/pull/48),
  [`b9cc126`](https://github.com/spindoxlabs/ds/commit/b9cc12668a8daab8362cfceff535e5d056a479e2))

- **deps**: Bump the actions group across 1 directory with 15 updates
  ([#47](https://github.com/spindoxlabs/ds/pull/47),
  [`d8053ff`](https://github.com/spindoxlabs/ds/commit/d8053ffd7c0123ccfdd2907c39512c0b1547343d))

- **deps**: Bump the npm-minor-patch group across 1 directory with 11 updates
  ([#52](https://github.com/spindoxlabs/ds/pull/52),
  [`3634002`](https://github.com/spindoxlabs/ds/commit/3634002d2af5fe3589909b7b82908e6693d73f04))

### Features

- **helm**: Participant profiles, a portal per participant, seed and governance from values,
  enrolment through the charts
  ([`0f1fb9e`](https://github.com/spindoxlabs/ds/commit/0f1fb9e787e24a04575eeca498a2317c7e82fc15))


## v0.1.0 (2026-10-10)

- Initial Release
