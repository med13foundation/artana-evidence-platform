# TG04 Frozen V10 Versus Staged V3 Untouched Canary Preflight

Created: 2026-07-20

Decision: `INVALID_EXPERIMENT_NOT_UNSEALED`

The requested paired untouched-source canary was stopped before PMID
selection, PubMed content access, source hashing, provider calls, or graph
writes. Frozen staged V3 cannot accept an arbitrary new PubMed source without
changing its scientific prompts, schemas, and event scopes. Those changes are
explicitly outside the authorized canary.

## Custody Status

- New PMID selected: no
- New PubMed identifier accessed: no
- New PubMed content accessed: no
- Untouched-source hash created: no
- Provider calls: 0
- Retries: 0
- Fallbacks: 0
- Graph writes: 0
- Untouched-source budget consumed: 0

No source identifier or content exists to audit for prior exposure because the
experiment stopped before deterministic selection.

## Frozen Inputs Verified

- Frozen V10 tree SHA-256:
  `bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a`
- Frozen staged V3 tree SHA-256:
  `dd9a00070395bb459fd7669c2b4626f89110d8573a8b7a3ba23a75fb4d8493c8`
- Frozen staged V2 implementation inherited by V3 SHA-256:
  `cdaad7672181ddb791c5859cfefbc374766324f5130de48d1c0bc9de1ccfdee6`
- Frozen staged prompt file SHA-256:
  `4089cc618d969c81dd30ae4b2fad089b22b8a27b2e591928902d1459ef76c6f3`

The repository worktree contained only the pre-existing untracked `uv.lock`.

## Blocking Schema Incompatibility

Frozen staged V3 inherits V2's source-specific contracts and prompts.

The role prompt requires:

- exactly events `A2` and `A5`;
- exactly participant IDs `P1` through `P6`; and
- event-local scopes supplied before the role call.

The statistical prompt also requires findings for exactly `A2` and `A5` and
contains the fixed exposed targets from PMID `40289860`.

The provider schemas enforce exactly two findings, and deterministic validation
rejects any identifier set other than `{A2, A5}`.

The scope builder hardcodes the two exposed passages:

- `A2_CLAUSE`; and
- `A5_CLAUSE`.

Therefore, on a new source, frozen staged V3 can only:

1. fail because the hardcoded passages are absent;
2. hallucinate or transplant the exposed A2/A5 events; or
3. require changed prompts, schemas, and scope construction.

Options 1 and 2 make the paired scientific comparison invalid. Option 3
violates the instruction to compare frozen staged V3 and freeze it without
changing the staged scientific prompts.

## Why Selection Stopped

Selecting and sealing a PMID would spend the untouched-source identifier budget
even though the staged arm is already known to be schema-incompatible. Fetching
the content would consume the stronger untouched-content budget. The requested
stop rule classifies a schema violation as `INVALID_EXPERIMENT`, so custody
requires stopping before either action.

No requested scientific metric can be truthfully computed because the staged
arm has no source-general event inventory or cardinality contract.

## Required Remediation Before A Canary

A valid paired canary needs a separately preregistered source-general staged
contract. That would be a new architecture checkpoint, not a reinterpretation
of V3. At minimum it must add:

1. an agent-owned event discovery stage returning categorical event candidates,
   exact source spans, and explanations without fixed A2/A5 identities;
2. deterministic assignment of stable candidate IDs and atomic source scopes;
3. V3-style agent-owned role, comparison, measurement, statistical,
   epistemic, and source-only review stages over the discovered scopes;
4. variable-cardinality schemas and deterministic duplicate/contradiction
   checks; and
5. a blinded common reviewer capable of adjudicating outputs from both arms
   without seeing arm identity.

That checkpoint must pass exposed development fixtures and the full service
gate before selecting a new PMID. Only then can a content-blind identifier seal,
prior-exposure audit, one-time PubMed fetch, content-hash audit, and paired live
execution be valid.

## Conclusion

The requested canary did not run. This protects the untouched source and avoids
creating a misleading comparison where V10 receives the new source while the
staged arm remains bound to a previous article. The next legitimate step is to
authorize the source-general staged checkpoint separately; it cannot be smuggled
into this frozen-canary execution.
