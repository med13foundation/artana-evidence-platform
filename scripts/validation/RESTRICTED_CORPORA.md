# Restricted corpora: fetch on demand, commit only derived artifacts

## The rule

**No licence-restricted corpus text is ever committed to this repository.**

This repository is public. The BioNLP-ST 2011 GE licence (clause 6) requires
organiser permission before a commercial or non-academic organisation may make
the corpus public. We do not have that permission, so the corpus is fetched on
demand and only *derived* artifacts enter git:

| Committed                                          | Never committed                                          |
| -------------------------------------------------- | -------------------------------------------------------- |
| Character offsets and locators                     | Document text                                            |
| SHA-256 digests of text, spans and archives        | Any verbatim run of 40 normalized characters or more     |
| Our event-type, role and polarity mappings         | Any span reproduced *as* a span, at any length (one disclosed exception below) |
| Adjudications, exclusion ledgers, counts           | Any span field in a fixture, whatever its length         |
| The bare name of an entity, trigger or relation cue |                                                          |

The same rule applies to code comments, docstrings, prompt strings and test
inputs. A corpus sentence pasted into a test as "realistic input" is
redistribution just as much as a fixture field is — a `source_text` grep will
not find it, but a content scan will.

### Where quotation stops and reference begins

The line between a name and a span is the only part of this rule that takes
judgement, so it is worth being exact about.

A **name** is committed: `WT1`, `suppress`, `iTreg-driving conditions`. It is
the analytical content of the finding — a record that said "the parent trigger
is a digest" would be unreadable, and a matcher that compared against a digest
would be untestable. Names are short, they recur across the literature, and
they are what the finding is *about*.

A **span** is not, however short. A span is the document's own wording
reproduced as wording: a sentence, a clause, a fragment shown as an excerpt.
The distinction is not length — an argument surface written as a name followed
by its parenthesised abbreviation runs to 35 characters and is still the
document's construction rather than the entity's name, and one of those sat in
`tests/unit/test_fresh_hidden_discovery_audit.py` until it was replaced with
the names the matcher actually keys on.

Fixtures get neither. They are redacted mechanically by field, so no
`source_text`, `source_span`, `trigger_span` or `exact_span` survives in a
committed fixture at any length. Prose records are redacted by judgement, which
is why they still carry names and why the scan's floor and the redaction rule
are the same number.

One deliberate exception is recorded rather than hidden:
`docs/validation/reports/2026-07-18-tg04-fresh-hidden-discovery.md` keeps that
same 35-character argument surface, twice, because the finding is about how the
extractor rendered that surface and a digest in its place would make the
finding unreadable. It is one string in one file, disclosed here, and it is the
only place the rule is bent, and
`python3 scripts/validation/check_restricted_corpus_text.py --threshold 32` is
what shows whether that is still true. Run below the floor and it also reports
short generic phrases — "further studies are required to", "plays an important
role in the" — in the PubMed-derived evidence-selection fixtures and the
synthetic articles. Those are shared scientific register that happens to occur
in GE as well, not GE-derived text, which is why the floor sits where it does
and why the reported runs have to be read rather than counted.

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
| Wired into | pre-commit, `make service-checks`, and its own CI job with no condition on it | `make restricted-corpus-scan`, by hand, before landing corpus-derived work |
| Compares against | committed digests of runs already removed | every document in the corpus |
| Catches | those runs coming back at 40+ folded characters — a revert, a paste out of published history, a re-wrapped, re-cased or re-emphasised copy | any verbatim run of 40+ characters, from any document |
| **Misses** | **any corpus text never removed before** — a fresh sentence from a document nobody has quoted is invisible to it — and any removed run that folds below 32 characters, which cannot be indexed at all | runs shorter than 40 characters; anything paraphrased rather than copied; anything the comparison form does not fold |

Both normalize the same way before comparing — case, typographic punctuation,
accents, inline Markdown emphasis and code markers, and whitespace all folded —
so re-wrapping a paragraph, lower-casing it into a slug, or bolding three words
inside the quotation does not slip past either.

The offline half indexes 32-character windows at a probe stride of 9, so
detection is guaranteed for a run of 40 normalized characters or more. Its
digest set is `restricted_corpus_digests.json`, rebuilt with
`make restricted-corpus-digests` from the same locators the redacted records
publish. The digests are one-way: they let a machine recognise restricted text,
not reconstruct it.

That artifact is the whole of the offline half's detection data, and it is
machine-written, so emptying or truncating it would have narrowed what the gate
sees without changing anything a reader would notice — an empty index matches
nothing and reports every tree clean. The checker therefore refuses to scan
unless the committed set still hashes to `INDEX_SHA256` in
`scripts/validation/restricted_corpus_digests.py`. Rebuilding the set moves
both, in one commit, with the reason on the record; the builder prints the new
value.

Neither half reads a path it cannot open, and both take the tracked list from
`git ls-files -z`. Splitting that list on whitespace instead broke any path
containing a space or a tab into fragments naming no file, which both scans
skipped in silence: a filename was enough to exempt a file, and the clean line
counts only what was read.

### Two digests, one locator

`restricted_corpus_digests.json` publishes two SHA-256 values for each run, over
two different forms of the same span, because the two halves of the guard need
different things:

- `span_sha256` / `span_length` — the **exact span** the locator addresses.
  This is the same convention the redacted records use, so a record's
  `evidence_sha256` and the artifact's `span_sha256` for the same
  `document_id` + `char:` locator are equal, and a reader can cross-check one
  against the other. `tests/unit/test_restricted_corpus_text.py` asserts that
  equality for every span the polarity adjudication cites.
- `folded_sha256` / `folded_length` — the same span in the **comparison form**
  above. This is what the window digests are cut from and what decides whether
  a run is long enough for detection to be guaranteed.

They coincide in length for every span indexed today, because none contains
collapsible whitespace or markup. That is a coincidence, not a rule, and the
names carry the convention precisely so it cannot be read as one. While the
folded digest was published as a bare `sha256`, a record and the artifact showed
two different values for one locator with nothing to say which was which — an
honest difference of convention that read exactly like a corrupted record.

### What the offline half actually caught

"Catches a revert" is too strong a claim to leave unqualified, so here is the
measurement. Reverting each of the eight files redacted on 2026-07-25, one at a
time, and running `restricted-corpus-digest-check`:

| Reverted file | Caught | Why |
| --- | --- | --- |
| `adjudications/…-gold-polarity-inheritance-adjudication-v1.json` | yes | nine indexed runs, eight of them guaranteed |
| `reports/…-tg04-nary-live-controlled-stop.md` | yes | 267-character run |
| `reports/…-tg04-known-expert-source-unit.md` | yes | 109-character run |
| `reports/…-tg04-hidden-discovery-unit.md` | yes | 98-character run |
| `reports/…-tg04-fresh-hidden-discovery.md` | yes | 63-character run |
| `reports/…-tg04-gold-importer-exclusion-ledger.md` | yes | only since emphasis is folded out; **it was missed before** |
| `reports/…-tg04-finite-source-unit-pilot.md` | yes, but not guaranteed | folds to 36 characters — above the 32-character window, so it is indexed, below the 40-character guarantee, so detection depends on where the run lands |
| `reports/…-tg04-transport-identity-smoke.md` | **no** | the removed run folds to 26 characters, below the window; it cannot be indexed at all, and the corpus-backed scan is its only guard |

Seven of eight, one of them by alignment rather than by guarantee. Two removed
runs are too short for the offline half to hold: that one, and the 30-character
span at `PMID-7537762` `char:923-953` cited by the fresh-discovery report.

The ledger miss is the instructive one. Its quotations carried inline emphasis
*inside* the quoted sentence, and folding case and whitespace but not `**` cut
a 169-character indexed run into fragments of 9, 10, 33, 9 and 9 characters.
Only the 33-character fragment reaches the 32-character window at all, and it
offers exactly two indexed positions for a stride-9 probe to land on. Neither
was hit: the probe count for that file was zero. Markup inside a quotation
defeated the guard while looking, to a reader of the rendered Markdown, exactly
like an unbroken quotation. Emphasis and code markers are now folded out, which
closes that shape. Others remain open by the same mechanism and are named in
`restricted_corpus_normalization.py`: a link or footnote inserted mid-sentence,
an HTML tag, a comment prefix repeated down a wrapped quote, an ellipsis
standing in for elided words. Each splits a run, and a split run is a short run.

Neither half is path-exempt. An earlier revision of the corpus-backed scan
skipped `docs/validation/` — the one tree that still held restricted text — and
so printed a clean result while roughly 1.5 kB of GE prose sat at HEAD. A
tree-shaped exemption cannot be audited. The scan now allowlists a small number
of *phrases* that are shared scientific register rather than corpus content;
that excuses the phrase everywhere and blinds no file.

That the exemption is gone is now asserted rather than remembered.
`tests/unit/test_restricted_corpus_scan.py` plants one run in every tree that
has ever held corpus text and requires each to be reported, refuses any
module-level constant shaped like a path, and pins the two properties whose
absence was silent both times it happened: that a fragment shared by two
documents is grown against both, and that every run in a file is reported, not
only the longest.

## How a record cites text it may not carry

`docs/validation/` holds adjudications and reports in which the quoted sentence
*is* the evidence for the finding. Deleting the quote would gut the record, so
each one is replaced by a reference that a licence holder can resolve exactly:

- `evidence_locator` / `char:<start>-<end>` — offsets into the **normalized**
  text of the document named by `document_id`, in the sense of
  `claim_events/corpus_text.py::normalized_document_text`, which is not the
  guard's comparison form;
- `evidence_sha256` — SHA-256 of the exact span those offsets address;
- `evidence_length` — its length in characters.

Fetch the corpus and the span is recoverable and verifiable byte-for-byte;
without it, the surrounding reasoning, the labels, the polarities and the
conclusions are all still readable. No finding, count or verdict changed when
the text was removed.

What each record keeps is settled by the rule above: names, not spans. A
redaction must not add to the record either — describing a redacted span as
"a single sentence" when it stops 77 characters short of the sentence end put a
claim into a sealed record that its own evidence contradicts, and in a report
about a source-binding defect the difference between a sentence and a prefix is
the subject matter.
