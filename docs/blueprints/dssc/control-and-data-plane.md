# How a Data Plane and Control Plane Work Together

> **Source** · DSSC Blueprint v3.0 › Technical Building Blocks › How a Data Plane and Control Plane Work Together
> **Section type** · Framing section of the Technical Building Blocks pane — **not a building block**

Upstream presents this page as framing, not as a building block. It sits directly under
the *Technical Building Blocks* pane, at the same level as the three interoperability
pillars that contain the named building blocks, and it has no pillar, no explainers and
no best-practice sub-pages of its own. Its purpose is to draw one distinction — between a
**control plane** and a **data plane** — and then to state which of the interactions
specified elsewhere in the technical building blocks belong to which plane. The source
itself says that "in a number of technical building blocks, parts of the interactions on
the control plane level are specified" and that this page summarises them.

## Scope and objectives

The page covers three things, in this order:

1. **The distinction itself.** The control plane "is responsible for deciding how data is
   managed, routed and processed"; the data plane "is responsible for the actual sharing
   of data". Upstream illustrates this with an example: "the control plane handles user
   identification, access, and usage policies, while the data plane handles the actual
   exchange of data."
2. **The asymmetry that follows from it.** Upstream draws an implication: the control
   plane "can be standardised to a high level, using common standards for identification,
   authentication, etc.", whereas the data plane "can be different for each data space and
   use case depending on the types of data exchange that take place". Some data spaces
   focus on sharing large datasets, others on message exchange, others take an
   event-based approach; upstream states "there is no one-size-fits-all", while noting
   that some mechanisms — especially in the data interoperability pillar — "can assist in
   making sure different data planes work together."
3. **Where the implementations come from.** Upstream states that developing a control and
   data plane from scratch is "often not necessary", and points to its own section on
   services for implementing technical building blocks.

The page does not define the two planes as deployable components, does not specify an
interface between them beyond the statement in "Management of the Transfer Process"
below, and does not assign either plane to a particular actor.

## Capabilities

Upstream frames the two planes as responsibilities rather than as capability lists. The
division is rendered here exactly as the source states it.

### Control plane

Responsible for **deciding how data is managed, routed and processed**. Upstream's
illustrative allocation puts user identification, access, and usage policies on this
plane. Because these concerns are common across data spaces, upstream concludes the
control plane can be standardised to a high level using common standards for
identification, authentication, and similar.

Upstream summarises the control-plane interactions specified across the technical
building blocks as four items, said to be summarised in a figure ("Figure 1"). Its own
labels and wording:

- **Identity and Attestations** — "The exchange of an identity and other relevant
  attestations. This is likely to include a credential indicating that someone is
  participating in a particular data space (thus complying with the relevant rulebook).
  We propose to use the W3C Verifiable Credentials standard for this purpose."
- **Catalogue Entries** — "These provide metadata describing the available Data Products
  in a catalogue. We propose using the W3C DCAT standard for this purpose."
- **Policies and Contract Negotiation** — "A data provider defines the access and usage
  policies for its Data Products. This can be defined using the ODRL standard. Based on
  the exchanged identities and attestation, and using any policy information points, a
  decision can be reached on whether or not to grant access to the data." Upstream adds a
  note: "contract negotiation is used in a technical, not in a legal sense here."
- **Management of the Transfer Process** — "Finally, the actual data exchange can take
  place (in the data plane). The control plane is still interfacing with the data plane,
  e.g., to ensure the proper execution of the agreed policies (policy enforcement)."

This last item is the only statement upstream makes on this page about the *interaction*
between the two planes: the control plane remains interfaced with the data plane while
the exchange itself runs, with policy enforcement given as the example of why.

Upstream also states that the control plane "can be built using foundational open
standards (Verifiable Credentials, ODRL, and DCAT)", cross-referencing its section on
building on top of foundational standards, and that "further protocols defining how these
standards can work together are being developed."

### Data plane

Responsible for **the actual sharing of data**. Upstream states that "the actual data
plane is very dependent on the specific use case" and gives no fixed set of interactions
for it. Instead it makes two recommendations about how a data space describes its data
plane, and one constraint on being explicit about the result:

- Upstream recommends "specifying the semantics/vocabulary of the data exchange".
- Upstream recommends "identifying the technical interfaces/APIs".
- These specifications "can be included in the rulebook for a data space".

The examples upstream gives of data-plane specifications — context, not requirements — are
the Asset Administration Shell API, adopted "in manufacturing organisations … to query
digital twins of manufacturing assets"; "generic standards such as GRAPHQL", which "can be
used to query large datasets"; and the CEF eDelivery specifications, used for messaging
"in some public sector data spaces, such as e-procurement, e-invoicing".

Upstream then states: "The Data Act mandates that - although the actual data plane can be
different for each application - data spaces should be explicit in specifying which
specifications apply."

## Standards and protocols

| Standard | Version / profile | Role | Normative force |
|---|---|---|---|
| W3C Verifiable Credentials | not stated | Exchange of an identity and other relevant attestations, on the control plane | recommended — upstream "propose[s] to use" it |
| W3C DCAT | not stated | Catalogue entries: metadata describing the available Data Products in a catalogue | recommended — upstream "propose[s] using" it |
| ODRL | not stated | Defining the access and usage policies a data provider sets for its Data Products | may |
| Asset Administration Shell API | not stated | Data-plane example: querying digital twins of manufacturing assets | referenced |
| GRAPHQL | not stated | Data-plane example: querying large datasets ("generic standards such as GRAPHQL") | referenced |
| CEF eDelivery specifications | not stated | Data-plane example: messaging in public sector data spaces (e-procurement, e-invoicing) | referenced |
| Data Act | no article or instrument number cited | Cited as mandating that data spaces be explicit about which data-plane specifications apply | referenced |

Upstream names Verifiable Credentials, ODRL and DCAT together as the "foundational open
standards" on which the control plane can be built. No version, profile or spec URL is
given for any standard on this page. Upstream's capitalisation "GRAPHQL" is preserved.

## Requirements

*Requirement IDs are a local index for benchmarking. The source does not number its
requirements.*

This page is framing prose. Most of its statements are descriptive or proposed rather than
normative, and the `Force` column records that: `informative` marks declarative or
illustrative prose, `recommended` marks upstream's own "we propose" / "we recommend"
formulations, and `may` marks its "can" formulations. Only one statement on the page
carries a `should`, and upstream attributes it to the Data Act rather than to itself.

| ID | Requirement | Force | Source |
|---|---|---|---|
| `DSSC-CDP-01` | The control plane is responsible for deciding how data is managed, routed and processed. | informative | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-02` | The data plane is responsible for the actual sharing of data. | informative | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-03` | Illustrative allocation: the control plane handles user identification, access, and usage policies, while the data plane handles the actual exchange of data. | informative | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-04` | The control plane can be standardised to a high level, using common standards for identification, authentication, etc. | may | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-05` | The data plane can be different for each data space and use case, depending on the types of data exchange that take place. | may | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-06` | There is no one-size-fits-all data plane: some data spaces focus on sharing large datasets, others on message exchange, others take an event-based approach. | informative | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-07` | Some mechanisms, especially in the data interoperability pillar, can assist in making sure different data planes work together. | may | `how-a-data-plane-and-control-plane-work-together.md` §1 |
| `DSSC-CDP-08` | Parts of the interactions on the control plane level are specified in a number of technical building blocks. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-09` | Control-plane interaction "Identity and Attestations": the exchange of an identity and other relevant attestations. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-10` | The identity exchange is likely to include a credential indicating that someone is participating in a particular data space, thus complying with the relevant rulebook. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-11` | The W3C Verifiable Credentials standard is proposed for the exchange of identity and attestations. | recommended | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-12` | Control-plane interaction "Catalogue Entries": entries providing metadata describing the available Data Products in a catalogue. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-13` | The W3C DCAT standard is proposed for catalogue entries. | recommended | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-14` | A data provider defines the access and usage policies for its Data Products. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-15` | Access and usage policies can be defined using the ODRL standard. | may | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-16` | Based on the exchanged identities and attestation, and using any policy information points, a decision can be reached on whether or not to grant access to the data. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-17` | On this page, "contract negotiation" is used in a technical, not in a legal sense. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-18` | Control-plane interaction "Management of the Transfer Process": after the preceding interactions, the actual data exchange can take place in the data plane. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-19` | The control plane is still interfacing with the data plane during the transfer, e.g. to ensure the proper execution of the agreed policies (policy enforcement). | informative | `how-a-data-plane-and-control-plane-work-together.md` §2 |
| `DSSC-CDP-20` | The control plane can be built using foundational open standards (Verifiable Credentials, ODRL, and DCAT). | may | `how-a-data-plane-and-control-plane-work-together.md` §2.1 |
| `DSSC-CDP-21` | Further protocols defining how these foundational standards can work together are being developed. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2.1 |
| `DSSC-CDP-22` | The semantics/vocabulary of the data exchange should be specified. | recommended | `how-a-data-plane-and-control-plane-work-together.md` §2.2 |
| `DSSC-CDP-23` | The technical interfaces/APIs of the data exchange should be identified. | recommended | `how-a-data-plane-and-control-plane-work-together.md` §2.2 |
| `DSSC-CDP-24` | These data-plane specifications can be included in the rulebook for a data space. | may | `how-a-data-plane-and-control-plane-work-together.md` §2.2 |
| `DSSC-CDP-25` | Data spaces should be explicit in specifying which specifications apply, although the actual data plane can be different for each application. Upstream attributes this to the Data Act ("The Data Act mandates that …"). | should | `how-a-data-plane-and-control-plane-work-together.md` §2.2 |
| `DSSC-CDP-26` | Developing a control and data plane from scratch is often not necessary. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2.3 |
| `DSSC-CDP-27` | The DSSC has identified services for implementing the control and data plane; they are presented in the section on services for implementing technical building blocks. | informative | `how-a-data-plane-and-control-plane-work-together.md` §2.3 |

## Open questions

> **Gap:** The page states that the control-plane interactions "are summarised in the
> image below (Figure 1)". The figure is not available as text. The four bullets rendered
> above are the accompanying prose; anything expressed only in the figure — an ordering,
> a sequence, an actor assignment, an explicit control-plane/data-plane boundary — cannot
> be recovered from the text and is not represented here.

> **Ambiguous:** Section numbering in the source is inconsistent with its content.
> "2.2 Data Plane Interactions" and "2.3 Implementing the Control and Data Plane" are
> nested under "2. Control Plane Interactions", although neither is about control-plane
> interactions. It is unclear whether the nesting is meaningful or an editing artefact.

> **Ambiguous:** Normative force. The control-plane standards are introduced with "We
> propose to use" / "We propose using" and the data-plane specifications with "we
> recommend". The source does not say whether these proposals are binding on a data space
> claiming conformance, nor what a data space that chooses otherwise must do instead.

> **Gap:** The Data Act citation at §2.2 gives no article, recital or instrument number,
> and the sentence mixes forces — "mandates that … data spaces **should** be explicit".
> Whether this is an obligation or a recommendation cannot be resolved from this page.

> **Gap:** No versions, profiles or specification URLs are given for W3C Verifiable
> Credentials, W3C DCAT or ODRL on this page, so the exact target of each proposal is
> undetermined here.

> **Ambiguous:** The cross-references at §2.2 for "semantics/vocabulary" and "technical
> interfaces/APIs" point at pages whose identifiers are marked as archived and as `_old`
> respectively, rather than at the current Data Models and Data Exchange building blocks.
> It is unclear whether the recommendation is meant to track the current building blocks
> or the superseded material.

> **Gap:** The page never states which actor operates either plane, whether the two planes
> may be provided by different parties, or what the interface between them is beyond "the
> control plane is still interfacing with the data plane". Any such detail lives in other
> parts of the blueprint, not here.
