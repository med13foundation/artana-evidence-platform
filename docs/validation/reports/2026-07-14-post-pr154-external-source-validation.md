# Post-PR154 External Source Validation

Date: 2026-07-14

Evaluated commit: `12306f981b13dbc6147faaf77ad7ed2fbd858901`

Evaluation branch: `alvaro/evidence-human-simulation-evaluation`

## Executive Verdict

Authoritative internet sources materially improve source trust and explain the
four disagreements from the simulated reviewer exercise. They do not turn the
simulation into human-expert gold.

| Area | Result |
|---|---|
| Unique PubMed records resolved | PASS: 29 of 29 |
| DOI and publication-type identity | PASS: no mismatches |
| Semantic title or abstract drift | PASS: none after Unicode whitespace normalization |
| Retractions | PASS: none found |
| Expressions of concern | PASS: none found |
| Linked corrections | REVIEW: one 2026 erratum for PMID 41138737 |
| Disputed BRCA1 records | Three packet-insufficient; one packet-sufficient select |
| Human-expert equivalence | NOT ESTABLISHED |

This check validates source identity, current integrity signals, and whether
the four disputed packets expose enough facts for a fail-closed decision. It
does not measure model precision because no qualified human gold exists.

## Validation Rules

The validation used the following order:

1. Resolve every unique PMID through the official NCBI PubMed E-utilities API.
2. Match PMID, DOI, publication types, title, and abstract text to the frozen
   source snapshots.
3. Normalize Unicode compatibility characters and whitespace before declaring
   semantic drift. Section-label formatting is compared separately from text.
4. Read PubMed `CommentsCorrectionsList` relationships and fail closed on a
   retraction, expression of concern, or unresolved material correction.
5. For disputed variants, inspect primary full text where available and query
   the official NCBI ClinVar record for current classification.
6. Keep source-level relevance separate from packet sufficiency. Internet facts
   not present in a frozen packet cannot be used to pretend that the packet was
   sufficient.
7. Produce categorical findings and explanations only. Numeric metrics are
   computed deterministically from categorical results after valid human gold
   becomes available.

The live PubMed XML retrieval contained 29 articles and 726,920 bytes. Its
SHA-256 digest was
`20f85f9dea3bc7cefef0733a340b257266ace7f8e2f98bfef2648cedadfbea95`.
Retrieval completed at `2026-07-15T02:33:29Z`.

## Corpus Integrity Result

All 29 unique PMIDs in the expert-pilot supplement manifest resolved to live
PubMed articles. DOI and publication-type lists matched the frozen snapshots.

Raw comparison found two title differences and 18 abstract differences. Every
title and abstract-text difference disappeared after Unicode NFKC and
whitespace normalization. The differences were thin spaces, non-breaking
spaces, and empty-versus-`ABSTRACT` section labels, not changed biomedical
claims. There were zero normalized title-text mismatches and zero normalized
abstract-text mismatches.

No live record had a retraction or expression-of-concern relationship.

### Integrity Signals Requiring Special Handling

- [PMID 41138737](https://pubmed.ncbi.nlm.nih.gov/41138737/) links to
  [published erratum PMID 41765032](https://pubmed.ncbi.nlm.nih.gov/41765032/).
  PubMed identifies the correction but does not expose its corrected content.
  The article must be marked `erratum_review_required`; the correction should
  not automatically reject the article, but the relation must not be promoted
  as correction-free evidence.
- [PMID 40288678](https://pubmed.ncbi.nlm.nih.gov/40288678/) is the journal
  update of preprint [PMID 39417132](https://pubmed.ncbi.nlm.nih.gov/39417132/).
  The journal article is the canonical source. The relationship is provenance,
  not a negative integrity signal.

## Four BRCA1 Disagreements

The recommendations below apply a fail-closed packet-only rule. Source-level
relevance describes what the complete authoritative sources establish;
`selection / sufficiency` describes what a blinded reviewer can justify from
the frozen packet.

| Record | Authoritative-source finding | Packet-only recommendation | Simulated run aligned |
|---|---|---|---|
| `brca1:pmid:21356067` | The full article reports BRCA1 c.5095C>T in three affected family members. Current ClinVar classifies it pathogenic with expert-panel review. | `abstain / insufficient` | Run A |
| `brca1:pmid:40288678` | The full article directly analyzes BRCA1 pathogenic variants. It reports a tentative higher-risk result for pre-Met128 PTVs and no significant location association, while the abstract emphasizes BRCA2. | `abstain / insufficient` | Run A |
| `brca1:pmid:26344711` | The article reports segregation of BRCA1 c.5141T>G with breast/ovarian cancer. Current ClinVar classifies the variant pathogenic/likely pathogenic with multiple submitters and no conflict. | `abstain / insufficient` | Run B |
| `brca1:pmid:32658311` | The abstract reports a human patient/control study and identifies a BRCA1 exons 17-18 deletion as a common pathogenic variant predisposing to breast cancer. | `select / sufficient` | Run B |

An independent source-only agent then received the complete authoritative
articles rather than the frozen packets. It returned `select / sufficient` for
PMIDs 21356067, 40288678, and 32658311, and `reject / sufficient` for PMID
26344711. That result is a diagnostic stress test, not expert gold. It shows
that packet sufficiency cannot be inferred from a reviewer who was allowed to
read material outside the packet.

The source-only rejection of PMID 26344711 exposes a second policy choice. The
2015 paper itself calls the variant unconfirmed, while current ClinVar classifies
it pathogenic/likely pathogenic using accumulated evidence that includes the
paper. The protocol must state whether relevance is judged as of publication or
using current registry knowledge. Either rule can be implemented, but silently
mixing them will produce unstable labels.

### PMID 21356067

[The primary article](https://pmc.ncbi.nlm.nih.gov/articles/PMC3109589/)
contains the decisive family-level fact that the BRCA1 c.5095C>T variant was
identified in three affected women. The current
[ClinVar variation record](https://www.ncbi.nlm.nih.gov/clinvar/variation/55396/)
classifies BRCA1 c.5095C>T (p.Arg1699Trp) as pathogenic with expert-panel
review.

The frozen abstract calls the variant breast-cancer associated but omits the
decisive family segregation detail. A packet-bound reviewer should abstain and
mark the packet insufficient, not reject the source. A source-enriched packet
would likely make this record selectable.

### PMID 40288678

[The full primary article](https://pmc.ncbi.nlm.nih.gov/articles/PMC12288856/)
shows that the study is not merely a BRCA2 paper. It directly evaluates BRCA1
pathogenic-variant type and location. The full text reports a possible higher
breast-cancer risk for BRCA1 PTVs predicted to cause NMD/re-initiation compared
with other PTVs (`OR=3.1`, `95% CI 1.0-13.5`, `P=0.083`) and says that larger
samples are needed.

Those BRCA1-specific facts are absent from the frozen abstract, which emphasizes
the statistically stronger BRCA2 findings. The current rubric also does not say
whether a null or statistically uncertain direct analysis qualifies. The safe
packet-only result is therefore abstain/insufficient. The next packet version
must include the BRCA1 result and an explicit rule for null or uncertain direct
evidence.

### PMID 26344711

[The primary PubMed record](https://pubmed.ncbi.nlm.nih.gov/26344711/) reports a
single family in which BRCA1 c.5141T>G segregated with five breast/ovarian
cancers, but the 2015 article correctly called the variant clinically
unconfirmed. The current
[ClinVar variation record](https://www.ncbi.nlm.nih.gov/clinvar/variation/55413/)
now classifies the variant pathogenic/likely pathogenic with multiple
submitters and no conflict and cites the family study as supporting evidence.

This is a useful source when enriched with current variant governance. It is
not a sufficient frozen packet for a criterion that explicitly requires a
pathogenic BRCA1 variant, because the packet contains only the older
unconfirmed classification. The fail-closed packet decision is
abstain/insufficient.

### PMID 32658311

[The primary PubMed record](https://pubmed.ncbi.nlm.nih.gov/32658311/) describes
732 breast-cancer patients, 189 colorectal-cancer patients, and 490 cancer-free
elderly controls. Its abstract explicitly identifies the BRCA1 exons 17-18
deletion as a common pathogenic variant predisposing to breast cancer.

That is direct primary human BRCA1 variant/risk evidence under the stated
inclusion criteria, even though the abstract does not provide a formal
variant-specific penetrance estimate. The packet supports select/sufficient.
If an exact penetrance estimate is mandatory rather than preferred, the rubric
must say so explicitly; the current inclusion criteria do not.

## What The External Check Changed

The four disagreements were not random model noise:

- two packets omitted decisive full-text BRCA1 results;
- one packet carried an obsolete, explicitly unconfirmed variant status that
  current ClinVar has resolved;
- one packet contained sufficient direct evidence, but one simulated reviewer
  over-applied the preference for a penetrance estimate;
- one non-disputed CFTR source acquired a linked erratum after the frozen
  snapshot was created.

The internet validation therefore improved the diagnosis of the evaluation
itself. It did not prove either simulated reviewer accurate, and it must not be
used as expert gold.

## Required Product Improvement

Add an authoritative-source validation layer before semantic selection. It
should use allowlisted, domain-appropriate sources rather than unrestricted web
search:

- PubMed/PMC for article identity, bounded text, publication type, and
  correction relationships;
- ClinVar for variant identity, classification, review status, conflicts, and
  version/timeline;
- ClinicalTrials.gov for registered trial identity and status when applicable;
- DOI/publisher metadata only to resolve or inspect a correction that the
  registry identifies.

The layer should emit categorical facts with provenance:

- `source_identity`: `matched`, `mismatched`, or `unresolved`;
- `integrity_status`: `clear`, `erratum_review_required`, `expression_of_concern`,
  `retracted`, or `unresolved`;
- `variant_status`: `pathogenic`, `likely_pathogenic`, `uncertain`, `conflicting`,
  `not_found`, or `not_applicable`;
- `packet_sufficiency`: `sufficient` or `insufficient`;
- literal evidence spans, source URL, record/version identifier, retrieval time,
  and a language explanation.

The agent should reason over those categorical facts and source spans. It must
not invent a numeric confidence or precision score. Deterministic code should
compute all rates, gates, and scorecard values from the categorical outcomes.

Fail-closed behavior should be explicit:

- retraction or expression of concern blocks trusted promotion;
- an unresolved material erratum routes the claim to review;
- a source mismatch, unresolved identity, or conflicting variant status forces
  abstention;
- external facts cannot retroactively change a frozen benchmark packet. A new
  source-complete packet version is required.

## What This Does Not Solve

External source validation does not establish reviewer identity, domain
qualification, independent human judgment, or a valid expert gold set. It also
does not resolve an ambiguous clinical inclusion rule by itself. The system
still needs the reviewer completion/signing workflow and real externally
authenticated experts described in the simulated-user evaluation.

## Final Conclusion

Yes, authoritative internet validation makes the system closer to expert
practice because it catches source drift, correction notices, current variant
classification, missing full-text facts, and packet insufficiency. The useful
design is a provenance-bound source-validation layer plus categorical agent
reasoning, not a general web search and not another model-generated score.

For this 33-record pilot, the external check validates all 29 unique source
identities, finds no retractions or expressions of concern, finds one erratum
requiring review, and characterizes all four simulated disagreements. It still does
not answer the production precision question; only the completed real expert
pilot can do that.
