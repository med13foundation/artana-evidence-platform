# TG04 Side-Typed Comparison V1

Status: `SCIENTIFIC_CONTENT_PASS_STRUCTURED_LEDGER_FAIL`

Scientific qualification: `false`

Advancement: `SEPARATE_MEASUREMENT_BASIS_AND_INHERITED_CONTEXT`

## Execution

- different already-exposed BioNLP development source;
- model: `openai:gpt-5.6-sol` with provider-default reasoning effort;
- one preregistered provider call;
- retries, fallback, replay, and graph writes: `0`;
- provider receipt: `verified_live`;
- V5 adversarial contract tests: `21 passed`;
- no benchmark score and no trusted-graph promotion.

The provider payload was `schema_invalid`, so the raw ledger was reviewed only as diagnostic scientific evidence.

## Scientific Result

Sol correctly preserved the complete source claim:

- TGF-beta induced Foxp3 in CbfbF/+ CD4-cre cells;
- the induction was dose dependent without an invented dose-response direction;
- the response was significantly reduced in CbfbF/F CD4-cre cells;
- `this` referred to the preceding TGF-beta-induced Foxp3 response;
- Foxp3 response in CbfbF/F cells was lower than in CbfbF/+ cells.

Both source-only reviewers agreed that source understanding was correct, the whole claim was complete, the comparison and anaphora were valid, dose dependence and significance were preserved, and unsupported claims were absent.

Independent adjudication therefore classified scientific content as `PASS` and unsupported claims as `ABSENT`.

## Why The Complete Ledger Failed

The output failed schema validation because E2 used participant `dose` as `COMPARISON_BASIS`, while V5 restricts that role to event targets. The scientific dose-dependence statement was valid; the role vocabulary was not.

Adjudication found three additional representation defects:

- TGF-beta was repeated as `TREATMENT_AGENT` on the reduced-response event, conflating inherited treatment context with the agent of that event.
- The comparator-specific induction event was used as the reduced event's `THEME`, conflating a response type with its right-side event instance.
- E3 contained both left and right context roles while being declared exclusively as left evidence.

Role fidelity and side ownership were therefore `INVALID`, and the complete ledger remained `FAIL`.

## Root Correction

The next contract must distinguish:

- a participant-valued measurement basis such as dose;
- directly stated treatment agency from inherited treatment context;
- an outcome participant from the event instance used as an anaphoric comparison basis;
- side-specific event evidence from a genuinely shared comparison event.

The next test remains exposed and non-qualifying. Higher reasoning effort is not the next variable: provider-default Sol already recovered the complete science, while the contract rejected its representation.

Untouched qualification remains unauthorized until the complete structured ledger passes, not only its prose interpretation.
