"""BC5CDR loading for the issue #217 claim-identity merge measurement.

BC5CDR (BioCreative V Chemical-Disease Relation) is NCBI-authored and carries a
PUBLIC DOMAIN NOTICE: "The National Library of Medicine and the U.S. Government
have not placed any restriction on its use or reproduction." It is therefore
*not* a restricted corpus in the sense of
``scripts/validation/RESTRICTED_CORPORA.md`` — no licence forbids redistributing
it. It is still not committed here, and neither is any sentence of it: these
modules emit MeSH ids, counts, digests and entity labels, and never a span.

The corpus is not fetched automatically. Point ``ARTANA_BC5CDR_CORPUS`` at a
directory holding the three ``CDR_*.PubTator.txt`` files, or drop them in
``.corpus-cache/bc5cdr/`` (git-ignored). The PubTator distribution is at
https://ftp.ncbi.nlm.nih.gov/pub/lu/CDR/ and the digests this measurement ran
against are recorded in ``MANIFEST.txt`` next to this file.
"""

from __future__ import annotations

import collections
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_ENV_VAR = "ARTANA_BC5CDR_CORPUS"
CORPUS_GLOB = "CDR_*.PubTator.txt"
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS_DIR = REPO_ROOT / ".corpus-cache" / "bc5cdr"

# PubTator column layout. A relation line is
#   pmid \t CID \t chemical-mesh \t disease-mesh
# and an annotation line is
#   pmid \t start \t end \t text \t type \t concept-id
PUBTATOR_RELATION_MIN_PARTS = 4
PUBTATOR_ANNOTATION_MIN_PARTS = 6
RELATION_CHEMICAL_COLUMN = 2
RELATION_DISEASE_COLUMN = 3
ANNOTATION_TEXT_COLUMN = 3
ANNOTATION_CONCEPT_COLUMN = 5

MentionCounts = dict[str, "collections.Counter[str]"]
CidFacts = dict[tuple[str, str], set[str]]


class CorpusUnavailableError(RuntimeError):
    """Raised when BC5CDR is not on disk, naming the remedy rather than a path."""


@dataclass(frozen=True)
class Document:
    """One BC5CDR abstract and the surface strings its annotations use."""

    pmid: str
    title: str
    abstract: str
    mentions: MentionCounts = field(default_factory=dict)

    @property
    def text(self) -> str:
        """Title and abstract joined the way the sweep's span heuristic reads them."""
        return f"{self.title} {self.abstract}"

    def label_for(self, mesh: str) -> str | None:
        """This document's most frequent surface string for ``mesh``.

        Ties break lexicographically, deterministically. This is the *resolved*
        label rule: it is what the persistence-path fallback fingerprints, and
        it is not what the frame branch hashes. See the report.
        """
        counter = self.mentions.get(mesh)
        if not counter:
            return None
        return max(counter.items(), key=lambda kv: (kv[1], [-ord(c) for c in kv[0]]))[0]


@dataclass(frozen=True)
class Corpus:
    """Parsed BC5CDR: documents, gold CID facts, and the file digests."""

    documents: dict[str, Document]
    cid_facts: CidFacts
    digests: dict[str, str]


def corpus_root(explicit: str | None = None) -> Path:
    """Resolve the BC5CDR directory, or say exactly how to supply one."""
    candidates = [
        Path(explicit) if explicit else None,
        Path(os.environ[CORPUS_ENV_VAR]) if os.environ.get(CORPUS_ENV_VAR) else None,
        DEFAULT_CORPUS_DIR,
    ]
    for candidate in candidates:
        if candidate and any(candidate.glob(CORPUS_GLOB)):
            return candidate
    raise CorpusUnavailableError(
        "BC5CDR not found. Expected the three CDR_*.PubTator.txt files in "
        f"{DEFAULT_CORPUS_DIR}, or set {CORPUS_ENV_VAR} to a directory holding "
        "them. The distribution is at https://ftp.ncbi.nlm.nih.gov/pub/lu/CDR/ "
        "and the digests this measurement ran against are in MANIFEST.txt.",
    )


def load(explicit_root: str | None = None) -> Corpus:
    """Parse every ``CDR_*.PubTator.txt`` under the resolved corpus root."""
    root = corpus_root(explicit_root)
    documents: dict[str, Document] = {}
    cid: CidFacts = collections.defaultdict(set)
    digests: dict[str, str] = {}

    for path in sorted(root.glob(CORPUS_GLOB)):
        raw = path.read_bytes()
        digests[path.name] = hashlib.sha256(raw).hexdigest()
        for block in raw.decode("utf-8").split("\n\n"):
            document = _parse_block(block, cid)
            if document is not None:
                documents[document.pmid] = document
    return Corpus(documents=documents, cid_facts=dict(cid), digests=digests)


def _parse_block(block: str, cid: CidFacts) -> Document | None:
    block = block.strip()
    if not block:
        return None
    pmid: str | None = None
    title = abstract = ""
    mentions: MentionCounts = collections.defaultdict(collections.Counter)
    for line in block.split("\n"):
        if "|t|" in line:
            pmid, _, title = line.split("|", 2)
        elif "|a|" in line:
            _, _, abstract = line.split("|", 2)
        else:
            _parse_tabbed_line(line, cid, mentions)
    if pmid is None:
        return None
    return Document(pmid=pmid, title=title, abstract=abstract, mentions=dict(mentions))


def _parse_tabbed_line(line: str, cid: CidFacts, mentions: MentionCounts) -> None:
    parts = line.split("\t")
    if len(parts) >= PUBTATOR_RELATION_MIN_PARTS and parts[1] == "CID":
        fact = (parts[RELATION_CHEMICAL_COLUMN], parts[RELATION_DISEASE_COLUMN])
        cid[fact].add(parts[0])
        return
    if len(parts) >= PUBTATOR_ANNOTATION_MIN_PARTS and parts[1].isdigit():
        for mesh in parts[ANNOTATION_CONCEPT_COLUMN].split("|"):
            mentions[mesh][parts[ANNOTATION_TEXT_COLUMN]] += 1
