# Target-Specific Specialist-Assisted Experiment V1

## Decision

`STOP_LUNA_SCIENTIFIC_FAILURE`

The experiment was valid and fail-fast. DeepEventMine ran once on the exposed
`PMID-16428936` abstract. Its output passed the minimum offline coverage gate,
so one Luna-high micro-canary ran. The first required nested event failed, and
the remaining three calls were not made.

## DeepEventMine Result

- Official commit: `e1c56013b4241e06c1cbe00992546367e4699036`
- GE11 checkpoint SHA-256:
  `789c01437966ac0ced10b78aa0e2a70eb3579edd1943cf7f91c4898a301fea33`
- Docker image:
  `sha256:84aecdb25d2336d3ae48514dcc75fc7e2e075c42a9276763895192909e973100`
- Execution count: 1
- Exit status: 0
- Runtime: 20.13 seconds
- Raw events: 8
- Normalized events: 7
- Exact grounded normalized events: 7/7
- Duplicate events removed: 1
- Unresolvable or invented spans: 0

The optional Brat visualization copy reported that its destination directory was
absent. This did not affect inference or source-offset postprocessing: both
completed, the normalized `.ann` was preserved, and the container returned zero.

Against the ten known incomplete exposed events, DeepEventMine exactly supplied
the trigger, Theme role, and c-Myc participant structure for two:

- `E-2773996d557442a07d58` / public gold `E30`: c-myc downregulation.
- `E-fd23ca8aac731381622e` / public gold `E24`: c-Myc expression.

Therefore the preregistered minimum of two potentially correctable participant
errors passed. However, nested-event coverage across the ten targets was 0.

## Luna Micro-Canary

The first packet contained the atomic sentence and one adjacent sentence. Luna
saw only DeepEventMine's source-grounded negative-regulation proposal:

```text
Decrease in c-Myc activity
```

Luna accepted that proposal and correctly attached it to a nested event. It also
explicitly concluded that the proposal set was `INCOMPLETE` because it did not
represent the current event where the decrease enhances cancer-cell sensitivity
to vinblastine.

This is the right fail-fast scientific conclusion. DeepEventMine found the inner
decrease, but not the sensitivity event or the outer enhancement. Luna did not
launder the incomplete proposal into a complete claim.

There was also a typed-output error: Luna labeled the accepted event proposal as
target kind `PARTICIPANT` with role `THEME`. A complete outer event would require
typed event-to-event attachment, not merely treating the inner event as a direct
participant.

## Provider Evidence

- Model: `openai:gpt-5.6-luna`
- Reasoning effort: `high`
- Response ID:
  `resp_0b0e5c99f4f0950a006a609b983a94819abaacea88f81dafef`
- Receipt: `VERIFIED_LIVE`
- Creation calls: 1
- Retries and duplicate creations: 0
- Input tokens: 870
- Output tokens: 1,218, including 516 reasoning tokens
- Total tokens: 2,088
- Latency: 12.73 seconds
- Cost: $0.008178

## Scientific Meaning

DeepEventMine helped with two simpler participant structures, so specialist
candidate generation is not useless. It did not solve the main nested scientific
failure. The required first canary proved that combining this GE11 output with
Luna-high still cannot reconstruct who participates in the complete sensitivity
event.

The baseline therefore remains 3/13 complete participant-bearing events. No
scientific improvement is claimed, and no result can enter graph promotion.

Focused validation passed with 17 tests plus Ruff and MyPy. The single requested
`make service-checks` run regenerated 88% coverage but did not leave a passing
pytest state; its failure cache contains broad pre-existing service failures
outside this experiment. The full suite was not repeated and those unrelated
failures were not folded into this bounded scientific checkpoint.

The most plausible root cause is model/task mismatch: the GE11 extractor is good
at GENIA-style molecular regulation and gene-expression structures, while this
Cancer Genetics abstract requires broader clinical/cellular event types and
multi-level nesting. Testing the two easier repairs would violate the explicit
first-event stop rule and would not answer the central question.
