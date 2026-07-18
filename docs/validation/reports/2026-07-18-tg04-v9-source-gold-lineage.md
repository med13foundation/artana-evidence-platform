# TG04 V9 Source-Gold Lineage

## Purpose

This receipt freezes the V9 source, acceptable scientific event structures,
and source provenance before any V9 Artana or Luna execution. It does not claim
human-expert validation or authorize trusted-graph promotion.

## Frozen Source

V9 is source unit 7 from `PMID-8622948`:

> Exogenous IL-2, which restitutes the proliferative response of the
> anti-CD3- and anti-CD28-treated Rel-/- T cells, restores production of IL-5,
> TNF-alpha, and IFN-gamma, but not IL-3 and GM-CSF expression to approximately
> normal levels.

The content-blind selector found four eligible hidden candidates and selected
the lowest SHA-256 rank after excluding every document used in V1 through V8.

## Scientific Contract

The canonical sealed BioNLP graph contains twelve events and six links:

- one source-asserted controller for restored proliferation;
- one controlled proliferation target;
- five source-asserted `POSITIVE_REGULATION` controllers sharing `restores`;
- five controlled `GENE_EXPRESSION` targets, one for each cytokine;
- null-result semantics on the IL-3 and GM-CSF controllers, matching M1 and M2.

Controlled targets are not independent source assertions. They use the closed
categorical combination `CONTROLLED_TARGET`, `UNSCOPED`, and `UNASSERTED` and
must be linked to a source-asserted controller. The relative pronoun `which`
must resolve to `Exogenous IL-2`.

Twelve complete projections preserve two source-valid proliferation trigger
spans and four scientifically equivalent cytokine representations. The three
supported cytokines may be one grouped multi-theme expression event or three
atomic controlled targets; the two null cytokines may likewise be grouped or
atomic. Two direct alternatives preserve five atomic outer events without
nested targets. Two BioNLP-topology projections preserve five atomic outer
`POSITIVE_REGULATION` events, five expression targets, and five one-to-one
links, with `NULL_RESULT` polarity for IL-3 and GM-CSF. Every projection requires
all five cytokine themes. Cause and
treatment alternatives are attached locally to each event. Partial matches may
not be assembled across projections, exactly one representation family must be
recovered, and unmatched trusted claims fail closed.

## Independent Review

Twelve adversarial reviews were completed without Artana V9 output.
They rejected synthetic atomic controllers, self-referential controlled
targets, missing anaphoric identity, optional assertion scope, mixed scope and
polarity categories, orphan controller or target declarations, and a benchmark
that incorrectly forced atomic cytokine targets. The latest scientific review
also found the missing corpus-native projection and a false-pass path for a
contradictory extra trusted claim. The execution review independently blocked a
live call until report replay, reservation identity, schema repair, and archive
preflight are tamper-resistant. A later source-only review caught that the first
"corpus-native" form was still flattened and that mixed complete alternatives
could pass; both defects are now explicit requirements of this receipt.
Two fresh reviewers then reproduced the wrong-extra-link and repair-identity
counterexamples against the corrected tree. Both returned GO to freeze V9 for
one pre-registered live diagnostic. This GO does not qualify Artana or authorize
trusted-graph promotion.

The resulting immutable hashes are:

- expert graph: `d10955c29c243c95b7e089c10866d453bbf6992e79abd18753b2192b525e832a`
- projection set: `9163b0d185bdafdc093d158ec0a5b4da0e37d950904d998d822084d04f455915`

## Source Verification

The corpus source was checked against PubMed PMID 8622948, PMCID PMC39621,
and DOI `10.1073/pnas.93.8.3405`. PubMed identifies the record as a journal
article with non-U.S. government research support and contains no correction
or retraction metadata.

All frozen offsets use the whitespace-normalized importer text. Raw BioNLP
offsets differ where source newlines are normalized; the normalized source text
and every sealed span are validated together before selection.

## Scope

- Artana V9 execution attempted: no.
- Luna V9 output available to reviewers: no.
- Numeric LLM scoring used: no.
- Human-expert gold established: no.
- Trusted-graph promotion authorized: no.
- Luna repeat 1 authorized: only after code gates and a fresh adversarial
  preregistration review pass.
