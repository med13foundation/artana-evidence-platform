# Fresh CG Candidate 1 — Preflight Failure

## Terminal status

`NOT_AUTHORIZED_NO_PROVIDER_CALL`

Candidate 1 selected `PMID-18165897` event `E12` as its first scientifically
representable event. Its public CG trigger is the exact span `negative` at
`1653:1661`, but that span is contained inside the biomedical token
`HER2neu-negative`.

Occurrence evaluator V2 requires event and participant mentions to use exact
token boundaries. Its deterministic resolver therefore rejected the candidate
before scientific scoring with `mention offsets split a source token`. This is
an instrumentation representability failure, not a model error and not a
scientific-reference disagreement.

No provider was called. The provisional selection, blinded review packet, two
primary reviews, tiebreak request/review, and mechanically resolved reference
are preserved in this directory. They receive no qualification or scientific
credit.

The corrected curation applies the already-frozen occurrence-V2 token-boundary
invariant while evaluating event representability, marks the affected document
ineligible with an explicit reason, and continues in the original reserve order
until eight bindable cases are selected.

## Preserved artifact hashes

| Artifact | SHA-256 |
| --- | --- |
| selection | `89e98798559ec727514105f2f4afd33aa2b5410b05dad262917716ca3b871ab1` |
| review packet | `505288903159f41d18238f7990c8b76a8adea6cefc8f6492fd1623603dde5d45` |
| reviewer A | `67554cd41434a9d364329fa91fc96bda90cb83507fc44036cb33ad99773c0d7a` |
| reviewer B | `e4dc85b87452eb2f6db9825b84e58de53d75b4ee076907f6230021560930085c` |
| tiebreak request | `08581601f6cc29c57357842ab1768f7b6cc6042cf22670ee9fa5a4fbc0f13bc4` |
| tiebreak reviewer | `60f73686f2e6c74db4d494f1239fc2e55e70c5c9d25e75c96d19893f18263ef1` |
| two-lane reference | `2033984e7e8b649168bc3adb0d0a627ffb623898f61b4dc16f364420f6f6e5ea` |
