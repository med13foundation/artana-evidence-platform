# TG04 Untouched V13 Versus V14 Pilot V1 Seal

Status: `COMPLETED_STOP_INVALID_ARM`

Manifest SHA-256: `434c3ca441887041099d8a5660353e5ff06b700dd81d4f8db65105064a6cede1`

## Scientific Question

On an untouched frozen source unit, does the complete V14 pipeline recover more
exact scientific events than V13-v3 without reducing precision, participant-role,
direction, polarity, grounding, unsupported-addition, or provider-custody safety?

This pilot compares the end-to-end sealed pipelines. It cannot attribute a result
solely to deterministic normalization because the arms issue independent primary
calls using their respective frozen prompt versions.

## Frozen Identity

- Product-code commit: `d204f5e9da02d8b24d13765022bbe8a3f9963db2`
- Model: `openai:gpt-5.6-luna`
- Fixture SHA-256: `26d67408a7a2446de5d36fca3f8a80a732b6519afe00e303c893eef3c824268d`
- Unit 1: `source-unit-b223c366d480eb18a857de9afc3ca50de9d4e80a97affe5d17e1ab69a0859073`
- Unit 1 input SHA-256: `f9f53e006b7b3a32cf3f6b28d3598b0fafba2609a8c3d92f805f6550cfaec7f9`
- Unit 2: `source-unit-ba7099212c9aded60d80c66920a00c2564ea3db3c524f858756791b28b2e22e0`
- Unit 2 input SHA-256: `e587e4f93031b7699a71c7fb7cd25801cb9863727f20329f51539fe4c49d4cf0`
- `preregistration.md`: `82b3808c739f76990cd6850d102a69253f11ce4c1ae7d0142af72a7eb661331e`
- `run.py`: `480ea103543661537a1cd16ba9661e5ae6a39eec07978f8aaa5cce74dabce44f`
- `test_run.py`: `cce9575a27ab7f887f32ac85d2de217571bd679376871b4006921b18e4015fc7`

The source text and hidden event answers are intentionally absent from this seal.

## Execution Boundary

- Run unit 1 only until V14 shows a strict exact-recall gain over V13.
- Require at least `0.90` V14 exact precision; at least `0.95` role, direction,
  and polarity fidelity; exact source binding; zero benchmark-unmatched claims;
  zero unsupported signals in either arm; and zero fallback or replay.
- Stop on equal recovery, an invalid arm, any unsupported-source ambiguity, or
  any safety regression. Unit 2 is spent only after unit 1 passes every gate.
- Maximum provider calls: `12`, enforced before delegation by the runner.
- Adapter retries: `0`; Responses-to-chat fallback is forbidden.
- Every successful arm requires three live-verified provider receipts bound to
  the declared model and exact output schemas.
- Graph writes: forbidden.
- Qualification eligibility: `false`.

## Provider-Free Validation

- Pilot tests: `18 passed`.
- Ruff: passed.
- Relevant source-unit, V13/V14, and receipt regression suite: passed.
- Independent scientific adversary: no material findings after fail-closed fixes.
- Independent execution adversary: no material findings beyond completing this
  seal before execution.

Passing this pilot authorizes only a separate repeated experiment. It does not
qualify Artana for trusted-graph promotion.

## Outcome

The one-shot pilot stopped after the first source. V13 completed three calls; V14
failed its primary structured-output contract after one call. The second untouched
source was not run.

- Decision: `STOP_INVALID_ARM`
- Provider calls: `4`
- Fallback/replay: `0`
- Graph writes: `0`
- Live-verified receipts: `4`
- Result file SHA-256: `831bce438f159d686cc119521fb030cccc7c1d481459de2723f3570224f74318`
- Internal report SHA-256: `b489f4ed520d2d2dcf77a23e0b147193b4c51e931686ae75893ec5f164433706`

V13 recovered two source-grounded events but reconstructed neither frozen event:
exact precision `0/2`, exact recall `0/2`, participant-role fidelity `0/4`, and
direction fidelity `0/2`. It lost the required `DR alpha` Theme and separate `S`
and `X2` Site roles.

V14 emitted two raw events but attached a controlled-event reference to a
gene/protein Cause, which the schema forbids. Removing only that invalid optional
reference made the payload schema-valid in a provider-free diagnostic. Its inner
event still contained the same Theme/Site role error, so no scientific-improvement
claim is warranted.

Independent source-only and benchmark adjudications agreed that the agents also
recovered a valid CIITA-dependent regulation claim omitted by the frozen gold.
That discovery remains review-only and cannot compensate for missed required
events. The next hypothesis is a role-first event inventory with provider-enforced
controlled-reference topology and separate, non-compensatory reconstruction and
source-supported-discovery ledgers.
