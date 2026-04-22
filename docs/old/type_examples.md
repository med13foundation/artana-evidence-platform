# Type Safety Examples and Usage Patterns

This document demonstrates how to effectively use the comprehensive type safety system implemented in the Artana Resource Library.

## Table of Contents

1. [Typed Test Fixtures](#typed-test-fixtures)
2. [Mock Repository Patterns](#mock-repository-patterns)
3. [API Response Validation](#api-response-validation)
4. [Domain Service Testing](#domain-service-testing)
5. [Space-Scoped Discovery Patterns](#space-scoped-discovery-patterns)
6. [External API Integration](#external-api-integration)
7. [Publishing Pipeline Types](#publishing-pipeline-types)
8. [Property-Based Testing](#property-based-testing)
9. [JSON Packaging Helpers](#json-packaging-helpers)
10. [Unified Storage Types](#unified-storage-types)
11. [Discovery Presets](#discovery-presets)

## Typed Test Fixtures

### Basic Test Gene Creation

```python
from tests.test_types.fixtures import (
    TEST_GENE_MED13,
    TEST_GENE_TP53,
    create_test_gene,
)

# Create a custom test gene
test_gene = create_test_gene(
    gene_id="CUSTOM001",
    symbol="CUSTOM",
    name="Custom Test Gene",
    chromosome="X",
    start_position=1000000,
    end_position=1100000,
    ensembl_id="ENSG00000123456",
)

# Use predefined test genes
med13_gene = TEST_GENE_MED13
tp53_gene = TEST_GENE_TP53
```

### Using Typed Test Data in Tests

```python
import pytest
from tests.test_types.fixtures import create_test_gene
from tests.test_types.mocks import create_mock_gene_service

def test_gene_service_functionality() -> None:
    """Test gene service with typed fixtures."""
    # Arrange: Create typed test data
    test_gene = create_test_gene(
        gene_id="TEST123",
        symbol="TEST",
        name="Test Gene"
    )

    # Create service with mock repository
    service = create_mock_gene_service([test_gene])

    # Act: Test service functionality
    gene = service.get_gene_by_symbol("TEST")

    # Assert: Verify typed results
    assert gene is not None
    assert gene.gene_id == "TEST123"
    assert gene.symbol == "TEST"
    assert gene.name == "Test Gene"
```

## Mock Repository Patterns

### Creating Type-Safe Mock Repositories

```python
from tests.test_types.mocks import MockGeneRepository
from tests.test_types.fixtures import TEST_GENE_MED13, TEST_GENE_TP53

# Create mock repository with test data
test_genes = [TEST_GENE_MED13, TEST_GENE_TP53]
mock_repo = MockGeneRepository(test_genes)

# Use in domain service
from src.domain.services.gene_domain_service import GeneDomainService
service = GeneDomainService(mock_repo)

# Mock tracks all calls for verification
gene = service.get_gene_by_symbol("MED13")
mock_repo.get_gene_by_symbol.assert_called_once_with("MED13")
```

### Factory Functions for Mock Services

```python
from tests.test_types.fixtures import TEST_GENE_MED13, TEST_VARIANT_PATHOGENIC
from tests.test_types.mocks import create_mock_gene_service, create_mock_variant_service

def test_gene_variant_relationship() -> None:
    """Test relationship between genes and variants."""
    # Create typed mock services
    gene_service = create_mock_gene_service([TEST_GENE_MED13])
    variant_service = create_mock_variant_service([TEST_VARIANT_PATHOGENIC])

    # Test interactions between services
    gene = gene_service.get_gene_by_symbol("MED13")
    variant = variant_service.get_variant_by_id(1)

    # Verify relationships
    assert gene is not None
    assert variant is not None
    assert variant.gene_identifier == gene.symbol
```

## Space-Scoped Discovery Patterns

Space-scoped discovery relies on dedicated fixtures and mocks so tests never have to hand-roll UUIDs or duplicate repository plumbing.

### Fixtures for Space Sessions & Permissions

```python
from uuid import uuid4

from tests.test_types.fixtures import (
    create_test_space_discovery_session,
    create_test_space_source_permissions,
)

def test_session_fixture_defaults() -> None:
    space_id = uuid4()
    session = create_test_space_discovery_session(
        space_id,
        owner_id=uuid4(),
        selected_sources=["clinvar"],
    )
    assert session.research_space_id == space_id
    assert "clinvar" in session.selected_sources

def test_permission_fixtures() -> None:
    permissions = create_test_space_source_permissions()
    available = [perm for perm in permissions if perm.permission_level == "available"]
    blocked = [perm for perm in permissions if perm.permission_level == "blocked"]
    assert len(available) == 1
    assert len(blocked) == 1
```

### Mocking `SpaceDataDiscoveryService`

```python
from uuid import uuid4

from src.domain.entities.data_discovery_session import QueryParameters
from tests.test_types.data_discovery_fixtures import create_test_source_catalog_entry
from tests.test_types.mocks import create_mock_space_discovery_service

def test_catalog_is_filtered_per_space() -> None:
    space_id = uuid4()
    catalog_entry = create_test_source_catalog_entry(entry_id="clinvar")
    service, base_service = create_mock_space_discovery_service(
        space_id,
        catalog_entries=[catalog_entry],
    )

    entries = service.get_catalog()

    base_service.get_source_catalog.assert_called_once_with(
        None,
        None,
        research_space_id=space_id,
    )
    assert [entry.id for entry in entries] == ["clinvar"]

def test_sessions_cannot_leak_across_spaces() -> None:
    space_id = uuid4()
    other_space_id = uuid4()
    service, _ = create_mock_space_discovery_service(space_id)
    other_service, _ = create_mock_space_discovery_service(other_space_id)

    first = service.create_session(
        owner_id=uuid4(),
        name="Cardiac sweep",
        parameters=QueryParameters(gene_symbol="MED13L"),
    )
    second = other_service.create_session(
        owner_id=uuid4(),
        name="Neuro sweep",
        parameters=QueryParameters(gene_symbol="MED12"),
    )

    assert first.research_space_id != second.research_space_id
```

## API Response Validation

### Validating External API Responses

```python
from src.infrastructure.validation.api_response_validator import APIResponseValidator
from src.type_definitions.external_apis import ClinVarSearchResponse, ClinVarSearchValidationResult

# Example ClinVar API response validation
def validate_clinvar_response(response_data: Dict[str, Any]) -> ClinVarSearchResponse | None:
    """Validate ClinVar API response with comprehensive error reporting."""
    validation_result: ClinVarSearchValidationResult = APIResponseValidator.validate_clinvar_search_response(response_data)

    if not validation_result["is_valid"]:
        # Log detailed validation issues
        for issue in validation_result["issues"]:
            logger.warning(
                f"Validation issue in {issue['field']}: {issue['message']} "
                f"(severity: {issue['severity']})"
            )

        # Check data quality score
        quality_score = validation_result["data_quality_score"]
        if quality_score < 0.5:
            logger.error(f"Low quality ClinVar response (score: {quality_score})")
            return None

    sanitized = validation_result["sanitized_data"]
    if sanitized is None:
        logger.error("Sanitized ClinVar payload missing despite a valid response")
        return None

    return sanitized
```

Reference responses are stored in `tests/fixtures/api_samples/` and can be refreshed with:

```bash
python scripts/regenerate_clinvar_samples.py
```

### Runtime Type Safety for External APIs

```python
from src.type_definitions.external_apis import ClinVarSearchResponse

def process_clinvar_search_response(raw_response: Dict[str, Any]) -> List[str]:
    """Process ClinVar search response with type safety."""
    # Validate response structure
    validation = APIResponseValidator.validate_clinvar_search_response(raw_response)

    if not validation["is_valid"]:
        raise ValueError(f"Invalid ClinVar response: {validation['issues']}")

    typed_response: ClinVarSearchResponse | None = validation["sanitized_data"]
    if typed_response is None:
        raise ValueError("ClinVar validation passed but returned no sanitized data")

    # Access fields with full IDE support and type checking
    return typed_response["esearchresult"]["idlist"]
```

## Domain Service Testing

### Testing Derived Properties Calculation

```python
from src.domain.services.gene_domain_service import GeneDomainService
from src.domain.entities.gene import Gene
from tests.test_types.fixtures import TEST_GENE_MED13
from tests.test_types.mocks import create_mock_gene_service

def test_gene_derived_properties() -> None:
    """Test calculation of gene-derived properties."""
    # Create gene entity from test data
    gene = Gene(
        gene_id=TEST_GENE_MED13.gene_id,
        symbol=TEST_GENE_MED13.symbol,
        name=TEST_GENE_MED13.name,
        gene_type=TEST_GENE_MED13.gene_type,
        chromosome=TEST_GENE_MED13.chromosome,
        start_position=TEST_GENE_MED13.start_position,
        end_position=TEST_GENE_MED13.end_position,
        ensembl_id=TEST_GENE_MED13.ensembl_id,
        ncbi_gene_id=TEST_GENE_MED13.ncbi_gene_id,
        uniprot_id=TEST_GENE_MED13.uniprot_id,
    )

    # Create service
    service = create_mock_gene_service([TEST_GENE_MED13])

    # Calculate derived properties
    context = {"analysis_depth": "comprehensive"}
    derived_props = service.calculate_derived_properties(gene, context)

    # Verify typed derived properties
    assert isinstance(derived_props, dict)
    # Properties include: functional_regions, expression_data, conservation_score, etc.
```

### Type-Safe Update Operations

```python
from src.type_definitions.common import GeneUpdate
from tests.test_types.fixtures import TEST_GENE_MED13
from tests.test_types.mocks import create_mock_gene_service

def test_gene_update_with_type_safety() -> None:
    """Test gene updates using type-safe update structures."""
    service = create_mock_gene_service([TEST_GENE_MED13])

    # Create typed update structure
    updates: GeneUpdate = {
        "name": "Updated Mediator Complex Subunit 13",
        "description": "Enhanced description with additional details",
        "ensembl_id": "ENSG00000108510.v2",
    }

    # Update gene with type safety
    updated_gene = service.update_gene(1, updates)

    # Verify type-safe updates
    assert updated_gene.name == "Updated Mediator Complex Subunit 13"
    assert updated_gene.description == "Enhanced description with additional details"
    assert updated_gene.ensembl_id == "ENSG00000108510.v2"
```

## External API Integration

### Type-Safe API Client Usage

```python
from src.infrastructure.ingest.clinvar_ingestor import ClinVarIngestor
from src.type_definitions.external_apis import ClinVarSearchResponse, ClinVarSearchValidationResult

class TypedClinVarIngestor(ClinVarIngestor):
    """ClinVar ingestor with enhanced type safety."""

    async def _search_variants_typed(self, gene_symbol: str, **kwargs) -> List[str]:
        """Search variants with type-safe response handling."""
        response = await self._make_request("GET", "esearch.fcgi", params={
            "db": "clinvar",
            "term": f"{gene_symbol}[gene]",
            "retmode": "json",
            "retmax": kwargs.get("max_results", 1000),
        })

        data = response.json()

        # Validate and type response
        validation: ClinVarSearchValidationResult = APIResponseValidator.validate_clinvar_search_response(data)
        if not validation["is_valid"]:
            logger.warning(f"ClinVar validation failed: {validation['issues']}")
            # Fallback to untyped processing
            return data.get("esearchresult", {}).get("idlist", [])

        # Use typed response
        typed_response = validation["sanitized_data"]
        if typed_response is None:
            return data.get("esearchresult", {}).get("idlist", [])
        return typed_response["esearchresult"]["idlist"]
```

### Error Handling with Type Safety

```python
from src.type_definitions.external_apis import APIResponseValidationResult, ValidationIssue

def handle_api_validation_errors(validation: APIResponseValidationResult) -> None:
    """Handle API validation errors with detailed reporting."""
    if validation["is_valid"]:
        return

    # Categorize issues by severity
    errors = [issue for issue in validation["issues"] if issue["severity"] == "error"]
    warnings = [issue for issue in validation["issues"] if issue["severity"] == "warning"]

    if errors:
        error_messages = [f"{e['field']}: {e['message']}" for e in errors]
        raise ValueError(f"Critical API validation errors: {', '.join(error_messages)}")

    if warnings:
        warning_messages = [f"{w['field']}: {w['message']}" for w in warnings]
        logger.warning(f"API validation warnings: {', '.join(warning_messages)}")

    # Check data quality
    quality_score = validation["data_quality_score"]
    if quality_score < 0.7:
        logger.warning(f"Low quality API response (score: {quality_score:.2f})")
```

## Publishing Pipeline Types

### Type-Safe Zenodo Publishing

```python
from src.infrastructure.publishing.zenodo.client import ZenodoClient
from src.type_definitions.external_apis import ZenodoMetadata, ZenodoDepositResponse
from tests.test_types.fixtures import create_test_publication

async def publish_research_package() -> str:
    """Publish research package with type safety."""
    # Create Zenodo client
    client = ZenodoClient(access_token="your-token", sandbox=True)

    # Create typed metadata
    metadata: ZenodoMetadata = {
        "title": "MED13 Gene Variants and Phenotypes Dataset",
        "description": "Comprehensive dataset of MED13 genetic variants and associated phenotypes",
        "creators": [
            {"name": "Research Team", "affiliation": "Medical Research Institute"}
        ],
        "keywords": ["MED13", "genetics", "variants", "phenotypes"],
        "license": "CC-BY-4.0",
        "publication_date": "2024-01-15",
        "access_right": "open",
        "subjects": [
            {"term": "Genetics", "identifier": "http://id.loc.gov/authorities/subjects/sh85053800"}
        ],
        "version": "1.0.0",
        "language": "eng",
    }

    # Publish with type safety
    deposit: ZenodoDepositResponse = await client.create_deposit(metadata)
    published = await client.publish_deposit(deposit["id"])

    return published["doi"]
```

### Release Management with Types

```python
from src.infrastructure.publishing.versioning.release_manager import ReleaseManager
from src.type_definitions.external_apis import ZenodoMetadata

async def create_typed_release() -> str:
    """Create a release with comprehensive type safety."""
    release_manager = ReleaseManager(
        package_name="med13-dataset",
        storage=storage_service,
        uploader=zenodo_uploader,
        doi_service=doi_service,
        versioner=versioner,
    )

    # Prepare typed Zenodo metadata
    zenodo_metadata: ZenodoMetadata = {
        "title": "MED13 Research Dataset v2.1.0",
        "description": "Latest release of MED13 genetic and phenotypic data",
        "creators": [
            {"name": "MED13 Consortium", "orcid": "0000-0000-0000-0000"}
        ],
        "keywords": ["genomics", "rare disease", "MED13", "intellectual disability"],
        "license": "CC-BY-4.0",
        "publication_date": "2024-01-15",
        "access_right": "open",
    }

    # Create release with type safety
    release_info = await release_manager.create_release(
        package_path=Path("./data/package"),
        version="2.1.0",
        release_notes="Added new MED13 variants and improved phenotype annotations",
        metadata=zenodo_metadata,
    )

    return release_info["doi"]
```

## Property-Based Testing

Hypothesis is part of the default development toolchain and is used to encode invariants for value objects and domain services.

```python
from hypothesis import given, strategies as st
from src.domain.services.gene_domain_service import GeneDomainService
from src.domain.value_objects.identifiers import GeneIdentifier

identifier_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
identifier_text = st.text(alphabet=list(identifier_chars), min_size=1, max_size=12)
service = GeneDomainService()

@st.composite
def gene_identifier_inputs(draw):
    symbol = draw(identifier_text)
    gene_id = draw(identifier_text)
    return GeneIdentifier(gene_id=gene_id, symbol=symbol)

@given(identifier=gene_identifier_inputs())
def test_normalize_gene_identifiers(identifier: GeneIdentifier) -> None:
    """Gene identifiers are always uppercased and never empty."""
    normalized = service.normalize_gene_identifiers(identifier)
    assert normalized.symbol == normalized.symbol.upper()
    assert normalized.gene_id == normalized.gene_id.upper()
```

The production property suite lives in `tests/unit/domain/test_gene_identifier_properties.py`. Add similar generators for other entities whenever you need to guarantee cross-field constraints that would otherwise require numerous example-based tests.

## JSON Packaging Helpers

Packaging modules now rely on `JSONObject` and `list_of_objects` helpers to keep RO-Crate metadata type-safe.

```python
from src.type_definitions.common import JSONObject
from src.type_definitions.json_utils import list_of_objects

def build_rocrate_metadata(
    data_files: list[JSONObject],
    provenance: JSONObject | None = None,
) -> JSONObject:
    file_entities: list[JSONObject] = []
    for file_info in data_files:
        path = file_info.get("path")
        if not isinstance(path, str):
            raise ValueError("file_info.path must be a string")

        entity: JSONObject = {
            "@id": path,
            "@type": "File",
            "name": file_info.get("name") or path,
        }
        file_entities.append(entity)

    if provenance:
        for source in list_of_objects(provenance.get("sources")):
            file_entities.append(
                {
                    "@type": "DataDownload",
                    "name": source.get("name"),
                    "contentUrl": source.get("url"),
                },
            )

    return {
        "@context": {"@vocab": "https://schema.org/"},
        "@graph": file_entities,
    }
```

See `src/application/packaging/rocrate/builder.py` and `src/application/packaging/provenance/metadata.py` for full implementations that avoid `typing.Any` while still modelling flexible JSON payloads.

## Unified Storage Types

The storage platform uses a discriminated union `StorageProviderConfigModel` to enforce valid configurations for each provider type, avoiding generic dictionaries.

### Type-Safe Configuration Creation

```python
from uuid import uuid4
from src.domain.entities.storage_configuration import StorageConfiguration
from src.type_definitions.storage import (
    LocalFilesystemConfig,
    StorageProviderName,
    StorageProviderCapability,
    StorageUseCase,
)

def create_local_storage_config() -> StorageConfiguration:
    """Create a strictly typed local filesystem configuration."""

    # Config model specific to LocalFS
    provider_config = LocalFilesystemConfig(
        base_path="/data/med13/raw",
        create_if_missing=True,
        max_capacity_gb=100
    )

    return StorageConfiguration(
        id=uuid4(),
        name="Primary Raw Storage",
        provider=StorageProviderName.LOCAL_FS,
        config=provider_config,  # Validated against discriminated union
        supported_capabilities=(
            StorageProviderCapability.READ,
            StorageProviderCapability.WRITE,
        ),
        default_use_cases=(
            StorageUseCase.RAW_SOURCE,
        )
    )
```

## Discovery Presets

Discovery presets use strict schema validation for `AdvancedQueryParameters` to ensure reproducible searches.

### Creating Valid Presets

```python
from uuid import uuid4
from src.domain.entities.discovery_preset import (
    DiscoveryPreset,
    DiscoveryProvider,
    PresetScope
)
from src.domain.entities.data_discovery_session import AdvancedQueryParameters

def create_pubmed_preset() -> DiscoveryPreset:
    """Create a typed discovery preset."""

    # Parameters are validated against the Pydantic model
    params = AdvancedQueryParameters(
        term="MED13[Title/Abstract] AND variants",
        min_date="2023-01-01",
        max_date="2024-01-01",
        max_results=50,
        article_types=["Journal Article", "Clinical Trial"]
    )

    return DiscoveryPreset(
        id=uuid4(),
        owner_id=uuid4(),
        provider=DiscoveryProvider.PUBMED,
        scope=PresetScope.USER,
        name="Recent MED13 Clinical Trials",
        parameters=params
    )
```

## Best Practices

### 1. Always Use Typed Fixtures in Tests

```python
# ✅ Good: Use typed fixtures
def test_with_typed_fixtures() -> None:
    test_gene = create_test_gene()
    service = create_mock_gene_service([test_gene])
    # ... test logic

# ❌ Bad: Use plain dictionaries
def test_with_plain_dicts() -> None:
    gene_dict = {"gene_id": "TEST", "symbol": "TEST"}
    # ... harder to maintain and type-check
```

### 2. Validate External API Responses

```python
# ✅ Good: Always validate API responses
def process_api_data(raw_data: Dict[str, Any]) -> ProcessedData:
    validation = APIResponseValidator.validate_api_response(raw_data)
    if not validation["is_valid"]:
        handle_validation_errors(validation["issues"])
    sanitized = validation["sanitized_data"]
    if sanitized is None:
        raise ValueError("Validated API response missing sanitized payload")
    return process_validated_data(sanitized)

# ❌ Bad: Skip validation
def process_api_data(raw_data: Dict[str, Any]) -> ProcessedData:
    # Risk of runtime errors from malformed data
    return process_data(raw_data)
```

### 3. Use Type-Safe Update Operations

```python
# ✅ Good: Use typed update structures
def update_gene() -> None:
    updates: GeneUpdate = {
        "name": "New Name",
        "description": "New description"
    }
    service.update_gene(gene_id, updates)

# ❌ Bad: Use plain dictionaries
def update_gene() -> None:
    updates = {
        "name": "New Name",
        "description": "New description"
    }
    service.update_gene(gene_id, updates)  # No type checking
```

### 4. Leverage Mock Verification

```python
# ✅ Good: Verify mock interactions
def test_service_calls() -> None:
    mock_repo = MockGeneRepository([test_gene])
    service = GeneDomainService(mock_repo)

    gene = service.get_gene_by_symbol("TEST")

    # Verify correct method called with correct arguments
    mock_repo.get_gene_by_symbol.assert_called_once_with("TEST")
    assert gene.symbol == "TEST"

# ❌ Bad: No verification of interactions
def test_service_calls() -> None:
    service = create_mock_gene_service([test_gene])
    gene = service.get_gene_by_symbol("TEST")
    assert gene.symbol == "TEST"  # No verification of how service works
```

These examples demonstrate how the comprehensive type safety system enables more reliable, maintainable, and testable code throughout the Artana Resource Library.
