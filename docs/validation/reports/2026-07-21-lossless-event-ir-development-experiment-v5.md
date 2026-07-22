# Lossless Scientific Event Development Experiment V5

**Decision:** `INVALID_EXPERIMENT`

This is a one-call exposed-development result. It does not qualify the sealed test split, graph writes, or trusted promotion.

## Integrity

- Preregistration: `bc7376cfe0b2d64dbcd43baef1f39f6bed5f7d5c7a516238f2d44c8421775421`
- Frozen state: `2f312e52820fb2225093a63017efd1598fe1d5ef51a49aa3bab07235acc30056`
- Provider creation calls: `1`
- Polling retrieval requests: `42`
- Confirmation retrieval requests: `1`
- Input-item retrieval requests: `1`
- Provider retries: `0`
- Duplicate creation calls: `0`
- Fallbacks and repairs: `0`
- Graph writes and promotions: `0`
- Sealed test sources accessed: `0`

## Invalidating Failure

- Stage: `RECEIPT_BUDGET`
- Root cause: total token ceiling exceeded

## Read-Only Postmortem

A retrieval-only diagnostic inspected provider usage and structure after V5 was
already terminal. It did not make another model-generation call and does not
reinterpret V5 as valid.

- Response ID: `resp_056d95ed70a099e4006a6012c3fbf88199be2601f0407ece84`
- Provider status: `completed`
- Input tokens: `1,794` (`1,791` cached)
- Output tokens: `159,372`
- Reasoning tokens: `11,912`
- Total tokens: `161,166`
- Cost under the frozen pricing formula: `$4.7820705`
- Output topology: `23` reasoning items and `1` final message

The `$5.00` cost gate passed, but the `40,000` total-token gate could not
represent Sol's reported internal model work. OpenAI documents that reported
output usage includes generated tokens that are not visible in the final text.

The same read-only replay reached source-span validation and found `54/66`
model-provided offsets shifted by at most three characters. Every exact mention
text exists in the source, and the closest occurrence was unique in every case.
Scientific scoring remained withheld because changing the frozen V5 budget or
offsets after execution would invalidate the preregistration.

## Conclusion

The multi-reasoning topology correction worked: V5 passed that boundary. V5 is
still invalid because its total-token accounting ceiling was inconsistent with
provider-reported work. A new experiment must separately resolve exact-text
offset arithmetic and use a total-token ceiling compatible with the unchanged
`$5.00` cost gate.
