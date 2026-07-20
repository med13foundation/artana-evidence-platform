# TG04 CIITA Parser Stop

Status: `NO_USEFUL_PROPOSAL`

Scientific qualification: `false`

This exposed probe tested the verified pretrained DeepEventMine GE11 parser on the CIITA sentence where standalone Sol had produced scientifically insufficient child roles.

## Execution

- verified GE11/SciBERT Docker image;
- raw-text end-to-end entity and event prediction;
- supplied annotations: `0`;
- predictions: `1`;
- retries: `0`;
- exit status: `0`;
- graph writes: `0`.

## Parser Output

```text
T1 Protein 76 84 DR alpha
T2 Entity 85 102 proximal promoter
T3 Protein 128 133 CIITA
T4 Positive_regulation 4 19 transactivation
E1 Positive_regulation:T4 Theme:T1 Site:T2
```

## Scientific Review

The parser found useful surface anchors, but the event role was not source-valid. The transactivated objects in the sentence are the multiple cis elements, especially `S` and `X2`; `DR alpha` names the promoter/gene locus and should not replace those objects as the scientific Theme.

The parser also omitted `S`, `X2`, `group II CID cells`, and the CIITA dependency edge. An independent source-only reviewer therefore assigned `NO_USEFUL_PROPOSAL` and found the `DR alpha` Theme assignment contradictory.

This result exposes a central evaluation distinction: the GE11 corpus's gene-centered projection can reward an event representation that a source-only scientific reviewer rejects. Benchmark reproduction and source-semantic scientific quality are not interchangeable.

## Decision

The preregistered parser-seeded Sol call is not authorized. Do not treat parser event roles as authoritative.

The parser remains potentially useful only as a fallible candidate generator for triggers, entities, and possible edges. An agent-first hybrid must evaluate each candidate edge against the source and may accept, correct, extend, or reject it. That narrower candidate-adjudication hypothesis needs a separate exposed experiment before any untouched source.
