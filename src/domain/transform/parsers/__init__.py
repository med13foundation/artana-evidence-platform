"""
Data parsers for different biomedical data sources.

Parsers extract structured information from raw data formats (XML, JSON, OBO)
and convert them into standardized Python objects for further processing.
"""

from .clinvar_parser import ClinVarParser
from .hpo_parser import HPOParser
from .pubmed_parser import PubMedParser
from .uniprot_parser import UniProtParser

__all__ = ["ClinVarParser", "HPOParser", "PubMedParser", "UniProtParser"]
