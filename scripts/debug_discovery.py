import sys
from pathlib import Path
from uuid import UUID

from src.application.services.data_discovery_service.catalog_methods import (
    CatalogPermissionMixin,
)
from src.application.services.data_source_activation_service import (
    DataSourceActivationService,
)
from src.database.session import SessionLocal
from src.infrastructure.repositories.data_discovery_repository_impl import (
    SQLAlchemySourceCatalogRepository,
)
from src.infrastructure.repositories.data_source_activation_repository import (
    SqlAlchemyDataSourceActivationRepository,
)
from src.models.database.data_discovery import (
    DataDiscoverySessionModel,
    SourceCatalogEntryModel,
)
from src.models.database.data_source_activation import DataSourceActivationModel

# Ensure we can import from src
sys.path.append(str(Path.cwd()))


# Mock class to use the mixin
class MockService(CatalogPermissionMixin):
    def __init__(self, activation_service, catalog_repo):
        self._activation_service = activation_service
        self._catalog_repo = catalog_repo


def debug():
    session = SessionLocal()
    try:
        print("--- Catalog Entries ---")
        entries = session.query(SourceCatalogEntryModel).all()
        print(f"Total entries: {len(entries)}")
        pubmed = session.query(SourceCatalogEntryModel).filter_by(id="pubmed").first()
        print(f"PubMed: {pubmed.id}, active={pubmed.is_active}")

        print("\n--- Activation Rules ---")
        rules = session.query(DataSourceActivationModel).all()
        for r in rules:
            print(
                f"Rule: {r.catalog_entry_id} {r.scope} {r.permission_level} (Space: {r.research_space_id})",
            )

        print("\n--- Sessions ---")
        sessions = session.query(DataDiscoverySessionModel).all()
        print(f"Total sessions: {len(sessions)}")
        for s in sessions:
            print(
                f"Session: {s.id} Space: {s.research_space_id} Sources: {s.selected_sources}",
            )

        print("\n--- Service Logic Check ---")
        # Simulate the service logic
        activation_repo = SqlAlchemyDataSourceActivationRepository(session)
        activation_service = DataSourceActivationService(activation_repo)
        catalog_repo = SQLAlchemySourceCatalogRepository(session)

        service = MockService(activation_service, catalog_repo)

        # Test with specific space ID from the URL
        space_id_str = "560e9e0b-13bd-4337-a55d-2d3f650e451f"
        space_id = UUID(space_id_str)

        result = service.get_source_catalog(research_space_id=space_id)
        print(f"Service returned {len(result)} entries for space {space_id}")
        for r in result:
            if r.id == "pubmed":
                print("PubMed IS in the result!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    debug()
