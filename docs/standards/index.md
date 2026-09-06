# Standards

External specifications this platform claims to implement, one page each: **which
version we pin, which parts we use, where the code sits against it, and what an
upstream change would cost us.**

This section exists because a specification name in a table is not a claim anybody can
check. "W3C Verifiable Credentials" in the
[specification inventory](../rulebook/data-exchange.md#5-the-specification-inventory)
says nothing about which of the two data models we emit, and "StatusList2021" says
nothing about the fact that the document behind that name has been withdrawn. A page
here is the long form of one inventory row, written so the claim can be re-checked
rather than trusted.

## What belongs here

A specification we **implement or align to**, where getting the version wrong changes
what a counterparty sees. Not every dependency: the DSP version pin lives in
[Data exchange](../rulebook/data-exchange.md) because it is a governance decision with
a release process attached, and JSON Schema is a tool rather than a claim.

| Page | Specification | What ds does with it |
|---|---|---|
| [VCDM 2.0 and Bitstring Status List](vcdm-2.0.md) | W3C Verifiable Credentials Data Model 2.0, W3C Bitstring Status List v1.0 | issues credentials and publishes their status — **on the superseded 1.1 / StatusList2021 pair** |
| [DPV 2.3](dpv-2.3.md) | W3C Data Privacy Vocabulary | aligns the local purpose taxonomy to an external vocabulary |

## The rule these pages follow

1. **Pin a version and a date.** A specification cited without one cannot drift
   visibly.
2. **Quote, do not paraphrase**, wherever the exact words decide a design.
3. **Measure the local side.** Where the code sits is a fact with a file and a line,
   not a recollection.
4. **Record the negative checks too.** An absent term is what makes a local extension
   necessary, and an unverified absence is the easiest thing to get wrong.
5. **Leave a re-check command**, so the next reader confirms the page instead of
   re-deriving it.

A page that says "we conform" without any of the five is the thing this section
replaces.
