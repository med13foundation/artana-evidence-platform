import sys
from pathlib import Path

from src.database.session import SessionLocal
from src.models.database.data_discovery import SourceCatalogEntryModel
from src.models.database.data_source_activation import (
    DataSourceActivationModel,
)

# Ensure we can import from src
sys.path.append(str(Path.cwd()))


def check_catalog():
    session = SessionLocal()
    try:
        entries = session.query(SourceCatalogEntryModel).all()
        print(f"Found {len(entries)} catalog entries:")

        activations = session.query(DataSourceActivationModel).all()
        print(f"Found {len(activations)} activation rules:")
        for act in activations:
            print(
                f"- Rule for {act.catalog_entry_id}: scope={act.scope}, permission={act.permission_level}",
            )

        for entry in entries:
            if entry.id == "pubmed":
                print(f"- {entry.id}: {entry.name} (Active: {entry.is_active})")

    except Exception as e:
        print(f"Error querying catalog: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    check_catalog()
