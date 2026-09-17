# EDC 0.18.0 — policy engine

How EDC represents ODRL, where it evaluates a policy, and what an extension registers to
take part. Paths are relative to the `Connector` repository at tag `v0.18.0`; `.../` elides
the Java package path.

## The ODRL model

`Connector: spi/common/policy-model/src/main/java/org/eclipse/edc/policy/model/`

| Class | Holds |
|---|---|
| `Policy` | `permissions`, `prohibitions`, `obligations` (duties), `profiles`, `inheritsFrom`, `assigner`, `assignee`, `target`, `extensibleProperties`, `type` (default `SET`). `withTarget(String)` returns a copy with a new target |
| `PolicyType` | `SET`, `OFFER`, `CONTRACT` |
| `Rule` (abstract) | `action`, `constraints` |
| `Permission` / `Prohibition` / `Duty` | a `Rule` plus `duties` / `remedies` / `consequences` |
| `Action` | `type`, `includedIn`, `constraint` |
| `AtomicConstraint` | `leftExpression`, `operator` (default `EQ`), `rightExpression` |
| `AndConstraint`, `OrConstraint`, `XoneConstraint` | subclasses of `MultiplicityConstraint` |
| `Operator` | `EQ`, `NEQ`, `GT`, `GEQ`, `LT`, `LEQ`, `IN` (`isPartOf`), `HAS_PART`, `IS_A`, `IS_ALL_OF`, `IS_ANY_OF`, `IS_NONE_OF` |

**A `Rule` has no `target`** — only `Policy` does. A function handed a `Permission` cannot
learn from it which asset is being negotiated.

JSON-LD ⇄ model conversion lives in
`Connector: core/control-plane/control-plane-transform/.../transform/odrl/`:
`to/JsonObjectToPolicyTransformer` maps `odrl:Set` / `Offer` / `Agreement` to
`SET` / `OFFER` / `CONTRACT` (missing type → `SET`), **requires** `assigner` and `assignee` on
an `Agreement`, and passes both through `ParticipantIdMapper.fromIri`;
`from/JsonObjectFromPolicyTransformer` renders the other way.

Evaluation semantics
(`Connector: core/common/lib/policy-evaluator-lib/.../evaluator/PolicyEvaluator.java`):
AND = all children, OR = any, XONE = exactly one; a prohibition whose constraints evaluate
true is a failure; a permission's duties are evaluated before its own constraints.

## Scopes are typed contexts

Since decision record `2024-10-05-typed-policy-context`, a scope is a **`PolicyContext`
subclass** registered under a string name. Functions and validators are registered against a
context *class*; the engine uses an entry when
`entry.contextType().isAssignableFrom(context.getClass())` (`isScoped` in
`Connector: core/common/lib/policy-engine-lib/.../engine/PolicyEngineImpl.java`). Registering
on a shared interface therefore applies a function to every context that implements it.

The base interface is `Connector: spi/common/policy-engine-spi/.../PolicyContext.java`
(`reportProblem`, `hasProblems`, `getProblems`, `scope()`). Two marker interfaces matter:

- `ParticipantAgentPolicyContext` (`spi/common/participant-spi`) — exposes `participantAgent()`.
- `AgreementPolicyContext` (`spi/control-plane/contract-spi/.../contract/spi/policy/`) —
  exposes `contractAgreement()` and `now()`.

### Every scope in 0.18.0

These seven are the only `@PolicyScope` constants in main code.

| Scope | Context class | Agent? | Agreement? | Evaluated by | For |
|---|---|---|---|---|---|
| `catalog` | `CatalogPolicyContext` (`spi/control-plane/catalog-spi`) | yes | no | `ContractDefinitionResolverImpl` (`core/control-plane/control-plane-catalog`); again in `ContractValidationServiceImpl.validateInitialOffer` | the contract definition's **access policy** |
| `contract.negotiation` | `ContractNegotiationPolicyContext` (`spi/control-plane/contract-spi`) | yes | no | `ContractValidationServiceImpl.validateInitialOffer` (`core/control-plane/control-plane-contract/.../validation/`), called from `ContractNegotiationProtocolServiceImpl` | the **contract policy**, targeted at the asset |
| `transfer.process` | `TransferProcessPolicyContext` | yes | yes | `ContractValidationServiceImpl.validateAgreement`, from `TransferProcessProtocolServiceImpl` on an incoming `TransferRequestMessage` (provider) | the **agreement's** policy, at transfer start |
| `policy.monitor` | `PolicyMonitorContext` (`spi/policy-monitor/policy-monitor-spi`) | **no** | yes | `PolicyMonitor` (`core/policy-monitor/policy-monitor-core/.../manager/`) | the agreement's policy, periodically, while a provider transfer runs |
| `request.catalog` | `RequestCatalogPolicyContext` | — | — | see below | building/validating the DSP token |
| `request.contract.negotiation` | `RequestContractNegotiationPolicyContext` | — | — | see below | same |
| `request.transfer.process` | `RequestTransferProcessPolicyContext` | — | — | see below | same |

The three `request.*` contexts (`Connector: spi/common/policy/request-policy-context-spi/`)
extend `RequestPolicyContext`, which carries a `RequestScope.Builder`. They are evaluated on
egress by `DspHttpRemoteMessageDispatcherImpl`
(`data-protocols/dsp/dsp-core/dsp-http-core/.../dispatcher/`) and on ingress by
`ProtocolTokenValidatorImpl`
(`core/control-plane/control-plane-aggregate-services/.../protocol/`). **Both discard the
result of `evaluate`**: the evaluation exists to let registered validators add credential
scopes to the builder, which then parameterise the outgoing token or the incoming token
verification. DCP registers exactly such validators — see
[Identity and trust](identity-and-trust.md#scopes).

Scope registration: `ContractCoreExtension` (`catalog`, `contract.negotiation`,
`transfer.process`), `CatalogCoreExtension` (`catalog`), `PolicyMonitorExtension`
(`policy.monitor`), `ControlPlaneServicesExtension` and `DspHttpCoreExtension` (`request.*`).

!!! note "Not in 0.18.0"
    Decision record `2025-04-25-agreement-policy-scope` proposes a `contract.agreement` scope
    and a `ContractAgreementPolicyContext`. Neither exists in the 0.18.0 code;
    `NegotiationProcessorsImpl.processRequested` transitions straight to `AGREEING`.
    There is no provisioning policy context either.

## The engine

Interface: `Connector: spi/common/policy-engine-spi/.../PolicyEngine.java` (`@ExtensionPoint`).
Implementation: `Connector: core/common/lib/policy-engine-lib/.../PolicyEngineImpl.java`,
provided by `CoreServicesExtension` together with `RuleBindingRegistryImpl` and
`ParticipantAgentServiceImpl`.

| Method | Purpose |
|---|---|
| `registerScope(String, Class<C>)` | name a context class |
| `registerFunction(Class<C>, Class<R>, String key, AtomicConstraintRuleFunction<R,C>)` | a function for one left operand |
| `registerFunction(Class<C>, Class<R>, DynamicAtomicConstraintRuleFunction<R,C>)` | a function that decides per left operand via `canHandle` (DR `2024-01-12-dynamic-constraint-functions`) |
| `registerFunction(Class<C>, Class<R>, PolicyRuleFunction<R,C>)` | a function over a whole rule |
| `registerPreValidator` / `registerPostValidator(Class<C>, PolicyValidatorRule<C>)` | a `BiFunction<Policy, C, Boolean>` over the **whole** policy |
| `evaluate(Policy, C)` | run it |
| `filter(Policy, String scope)` | apply the scope filter only |
| `validate(Policy)` | static validation (below) |
| `createEvaluationPlan(String scope, Policy)` | explain what would run; throws for an unregistered scope |

`evaluate` does, in order:

1. run pre-validators — the first failure ends evaluation;
2. collect the rule, atomic and dynamic functions whose context type matches;
3. **filter the policy to the scope** (`ScopeFilter.applyScope`);
4. evaluate the filtered policy;
5. on success, run post-validators — on the **unfiltered** policy.

Failure text: `Policy in scope %s not fulfilled: [...]`.

### Rule bindings and the scope filter

`Connector: spi/common/policy-engine-spi/.../RuleBindingRegistry.java` binds a *rule type* —
an action type or a left operand — to a scope. `bind(type, "foo")` also covers `foo.bar`
(the registry stores `scope + "."` and matches by prefix); `*` covers everything.
`dynamicBind(Function<String, Set<String>>)` is consulted only when a type has no static
binding.

`Connector: core/common/lib/policy-engine-lib/.../ScopeFilter.java` then **removes**, before
evaluation:

- any rule whose action type is not bound to the scope;
- any atomic constraint whose left operand is not bound to the scope;
- any multiplicity constraint left with no children.

The class's own javadoc warns that a rule stripped of all its constraints evaluates true.
This is the most important behaviour to know when writing a profile: **an unbound left
operand is silently ignored, not denied.**

The opposite case is a hard failure: a *bound* operand with no registered function yields
`"No evaluation function found"` and the constraint evaluates false
(`PolicyEvaluator`). A non-string left operand also fails.

Out of the box, `odrl:use` is bound only to `transfer.process` (`ContractCoreExtension`) and
`policy.monitor` (`PolicyMonitorExtension`), plus the four CEL scopes when `cel-core` is
present. Read with the filter rules above, an unbound `use` rule is dropped from `catalog`
and `contract.negotiation` evaluation unless some extension binds it — an inference from the
code, not verified at runtime.

### Validation at write time

Decision record `2024-08-16-policy-validation`.
`Connector: core/common/lib/policy-engine-lib/.../validation/PolicyValidator.java` rejects a
policy whose action or left operand is bound to no scope, or whose left operand has no
function, and runs each function's `validate`. `PolicyDefinitionServiceImpl` calls it on
create and update and returns `400` on failure. Switch: `edc.policy.validation.enabled`,
default `true` (`ControlPlaneServicesExtension`).

### Built-in functions

There is one Java constraint function in core:
`Connector: core/control-plane/lib/control-plane-policies-lib/.../ContractExpiryCheckFunction.java`,
left operand `edc:inForceDate` (`https://w3id.org/edc/v0.0.1/ns/inForceDate`), on
`Permission`, for any `AgreementPolicyContext`. The right operand is an ISO-8601 instant or
`contractAgreement+<n>s|m|h|d` relative to the signing date; operators `EQ`, `NEQ`, `GT`,
`GEQ`, `LT`, `LEQ`. Registered in `transfer.process` and `policy.monitor`.

No other left operand (spatial, purpose, membership …) is registered by core.

### CEL expressions

Decision record `2026-01-27-adopt-cel-expressions`: policies whose constraints are
`CelExpression` entities (`Connector: spi/common/cel-spi/`), evaluated by a dynamic function,
`CelExpressionFunction`, registered by `CelPolicyCoreExtension`
(`Connector: core/common/cel-core/`) for the `catalog`, `contract.negotiation`,
`transfer.process` and `policy.monitor` contexts. The DR calls it experimental.
**`cel-core` is in `controlplane-virtual-base-bom` only, not in `controlplane-base-bom`.**

## ParticipantAgent

`Connector: spi/common/participant-spi/.../ParticipantAgent.java` — `identity` (non-null),
`claims` (`Map<String,Object>`), `attributes` (`Map<String,String>`).

It is built for every incoming protocol message by `ProtocolTokenValidatorImpl`:

1. verify the token with the `IdentityService` → `ClaimToken`;
2. pick the participant-id extraction function for the message's protocol from the
   `DataspaceProfileContextRegistry`
   (`core/control-plane/control-plane-core/.../profile/DataspaceProfileContextRegistryImpl.java`);
3. no id → `401`;
4. `ParticipantAgentService.createFor(claimToken, id)` — claims are copied from the token,
   attributes are merged from every registered `ParticipantAgentServiceExtension`
   (`core/common/connector-core/.../agent/ParticipantAgentServiceImpl.java`).

The id extraction function depends on the identity module:

- **DCP**: `DefaultDcpParticipantIdExtractionFunction`
  (`extensions/common/iam/decentralized-claims/decentralized-claims-core/.../defaults/`) —
  the first non-null `credentialSubject.id` among the verified credentials in the `vc` claim.
- **iam-mock**: the `client_id` claim (`extensions/common/iam/iam-mock/.../IamMockExtension.java`).

Decision records `2025-07-25-multiple-participant-identifiers` (extraction becomes
per-profile) and `2025-10-29-participant-identifiers` (the local participant id comes from a
`ParticipantIdentityResolver`,
`spi/common/connector-participant-context-spi/.../identity/ParticipantIdentityResolver.java`).

## Agreements: assigner, assignee, equality

- **Provider side**, `NegotiationProcessorsImpl.processAgreeing`
  (`core/control-plane/control-plane-contract/.../negotiation/`): the agreement policy is the
  last offer's policy with `type = CONTRACT`, `assignee = counterPartyId` and
  `assigner = ` the provider's id from `ParticipantIdentityResolver`. The `ContractAgreement`
  carries `providerId`, `consumerId`, `contractSigningDate` (epoch seconds), `assetId` and,
  since DR `2025-10-03-contract-agreement-changes`, an `agreementId` shared by both sides
  distinct from the local entity id (`spi/control-plane/contract-spi/.../agreement/ContractAgreement.java`).
- **Provider checks** (`ContractValidationServiceImpl`): `validateInitialOffer` — access policy
  in `catalog`, asset exists, asset matches the definition's `assetsSelector`, contract policy
  targeted at the asset in `contract.negotiation`. `validateAgreement` — the agent's identity
  must equal `agreement.consumerId`, then `transfer.process`.
- **Consumer check**, `validateConfirmed`: the agent's identity must equal
  `agreement.providerId`, and the agreement policy (retargeted to the asset) must equal the
  last offer under `PolicyEquality`
  (`core/control-plane/control-plane-contract/.../policy/PolicyEquality.java`), which compares
  JSON trees ignoring only `@type`, `assignee` and `target`. **`assigner` is compared.**

How the provider builds the `ValidatableConsumerOffer` it evaluates from the consumer's
request was not traced in detail — not verified.

## The policy monitor

Decision record `2023-09-07-policy-monitor`. `PolicyMonitorExtension`
(`core/policy-monitor/policy-monitor-core/`) subscribes synchronously to
`TransferProcessStarted` and starts watching **provider** transfers only
(`subscriber/StartMonitoring.java`). Each pass (`manager/PolicyMonitor.java`) evaluates the
agreement policy in `policy.monitor`; on failure it calls
`TransferProcessService.terminate(...)`. Entries whose transfer reached `COMPLETING` or later
are closed. Settings: `edc.policy.monitor.batch-size` (20), `edc.policy.monitor.period`
(`PT1H`). The monitor store is in-memory unless `policy-monitor-store-sql` is present.

`PolicyMonitorContext` carries **no `ParticipantAgent`**; a function registered only on
`ParticipantAgentPolicyContext` never runs there.

## What ds adds on top

`services/edc-extensions/src/main/java/dataspaces/edc/DataspacesExtension.java` binds its
actions, the purpose operand and the consent operand in `contract.negotiation`,
`transfer.process` and `policy.monitor`, binds membership and `ds:contractRequired` in
`contract.negotiation` only, registers the matching functions, and adds a post-validator in
`contract.negotiation` because a rule function cannot see the policy target. Details:
[edc-extensions](../../services/edc-extensions.md).
