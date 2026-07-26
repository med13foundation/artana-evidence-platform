# Restricted corpora: fetch on demand, commit only derived artifacts

## The rule

**No licence-restricted corpus text is ever committed to this repository.**

This repository is public. The BioNLP-ST 2011 GE licence (clause 6) requires
organiser permission before a commercial or non-academic organisation may make
the corpus public. We do not have that permission, so the corpus is fetched on
demand and only *derived* artifacts enter git:

| Committed                                         | Never committed          |
| ------------------------------------------------- | ------------------------ |
| Character offsets and locators                    | Document text            |
| SHA-256 digests of text, spans, archives          | Trigger and argument spans |
| Our event-type, role and polarity mappings        | Any verbatim sentence    |
| Adjudications, exclusion ledgers, counts          | Quoted excerpts in code, tests, or comments |

The same rule applies to code comments, docstrings, prompt strings and test
inputs. A corpus sentence pasted into a test as "realistic input" is
redistribution just as much as a fixture field is — a `source_text` grep will
not find it, but a content scan will.

## How to rehydrate

```sh
python3 scripts/fetch_bionlp_ge_corpus.py
```

This downloads the archive, verifies it against the SHA-256 recorded in the
fixture provenance, and extracts it to `.corpus-cache/` (git-ignored). Nothing
it writes is committed. To use a copy held elsewhere — a shared cache, or a
location outside the repository entirely — point the loader at it:

```sh
export ARTANA_BIONLP_GE_CORPUS=/path/to/BioNLP-ST_2011_genia_devel_data_rev1
```

`scripts/validation/claim_events/fixture.py::load_fixture` rejoins the two
halves automatically. Code that consumes a fixture needs no changes. If the
corpus is absent, it raises `RestrictedCorpusUnavailableError` naming the
licence, the fetch command and the environment variable — never a `KeyError` on
a missing field.

## Why the frozen digests did not change

The TG-04 fixtures are stored redacted, but `load_fixture` returns the
*rehydrated* panel and hashes that. Rehydration is exact — the importer writes
canonical JSON (`indent=2, sort_keys=True, ensure_ascii=True`), so restoring
text at the recorded offsets reproduces the original bytes.

So `FROZEN_DEVELOPMENT_FIXTURE_SHA256` keeps the value it has had since the
panel was frozen, and the preregistration that cites it stays valid. The seal is
in two halves, and both are checked:

- `REDACTED_DEVELOPMENT_FIXTURE_SHA256` pins the committed bytes — our offsets,
  labels, adjudications and the 419-entry exclusion ledger. Checked offline.
- Per-case `source_sha256` and `source_length` pin the document text those
  offsets address. Checked at rehydration, so a corpus at a different revision
  is rejected rather than silently rescoring the benchmark.

Together these pin strictly more than the single pre-redaction digest did: that
one proved the file had not changed, but said nothing about whether the text it
described was still the frozen corpus revision.

## What this costs

Checks that need the document text itself — the live runners, evidence-binding
replay, and source-unit enumeration, which must see unannotated sentences too —
cannot run without the corpus. They are marked `@requires_corpus` and skip with
a reason naming the licence and the fetch command. **They are never deleted, and
a skip is never the way to make a gate green.** Everything that can be checked
from derived data alone still runs offline.

## Adding a corpus

Before committing anything derived from a new corpus, check its licence for
redistribution terms. If it restricts public use:

1. Add a fetch script that verifies the archive against a pinned digest and
   writes only to a git-ignored path.
2. Commit offsets and digests, never text.
3. Gate text-dependent checks on availability, with a reason that names the
   remedy.
4. Run `make restricted-corpus-scan` (needs the corpus) to confirm no verbatim
   run leaked into any tracked file.

## The guard, and what each half misses

The check is in two halves because the thorough one needs a corpus we may not
commit. Neither half alone is sufficient, and neither is a clean bill of health.

| | `restricted-corpus-digest-check` | `restricted-corpus-scan` |
| --- | --- | --- |
| Needs the corpus | no | **yes** |
| Wired into | pre-commit, `make service-checks`, and CI unconditionally | `make restricted-corpus-scan`, by hand, before landing corpus-derived work |
| Compares against | committed digests of runs already removed | every document in the corpus |
| Catches | those runs coming back — a revert, a paste out of published history, a re-wrapped or re-cased copy | any verbatim run of 40+ characters, from any document |
| **Misses** | **any corpus text never removed before.** A fresh sentence from a document nobody has quoted is invisible to it | runs shorter than 40 characters; anything paraphrased rather than copied |

Both normalize the same way before comparing — case, typographic punctuation,
accents and whitespace all folded — so re-wrapping a paragraph or lower-casing
it into a slug does not slip past either.

The offline half indexes 32-character windows at a probe stride of 9, so
detection is guaranteed for a run of 40 normalized characters or more. Its
digest set is `restricted_corpus_digests.json`, rebuilt with
`make restricted-corpus-digests` from the same locators the redacted records
publish. The digests are one-way: they let a machine recognise restricted text,
not reconstruct it.

Neither half is path-exempt. An earlier revision of the corpus-backed scan
skipped `docs/validation/` — the one tree that still held restricted text — and
so printed a clean result while roughly 1.5 kB of GE prose sat at HEAD. A
tree-shaped exemption cannot be audited. The scan now allowlists a small number
of *phrases* that are shared scientific register rather than corpus content;
that excuses the phrase everywhere and blinds no file.

## How a record cites text it may not carry

`docs/validation/` holds adjudications and reports in which the quoted sentence
*is* the evidence for the finding. Deleting the quote would gut the record, so
each one is replaced by a reference that a licence holder can resolve exactly:

- `evidence_locator` / `char:<start>-<end>` — offsets into the **normalized**
  text of the document named by `document_id`;
- `evidence_sha256` — SHA-256 of the exact span those offsets address;
- `evidence_length` — its length in characters.

Fetch the corpus and the span is recoverable and verifiable byte-for-byte;
without it, the surrounding reasoning, the labels, the polarities and the
conclusions are all still readable. No finding, count or verdict changed when
the text was removed.

Spans shorter than 40 characters that name an entity, a trigger or a relation
cue were kept: they are the analytical content of the record rather than
republished prose, and replacing them with digests would leave findings a
reader could not follow. That is a judgement about where quotation stops and
reference begins, and it is the reason the scan's floor and the redaction rule
are the same number.
