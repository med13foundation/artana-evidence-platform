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
4. Run `python3 scripts/validation/check_restricted_corpus_text.py` (needs the
   corpus) to confirm no verbatim run leaked into any tracked file.

## Known exception

Files under `docs/validation/` still quote GE sentences — the largest is a
169-character run in the polarity adjudication record. That tree is frozen
merged evidence and was out of scope for the redaction that produced this note.
Removing corpus text from it is an open decision for the product owner.
