import sys
from pathlib import Path
from uuid import uuid4

from src.database.session import SessionLocal
from src.models.database.data_source_activation import (
    ActivationScopeEnum,
    DataSourceActivationModel,
    PermissionLevelEnum,
)
from src.models.database.user import UserModel

# Ensure we can import from src
sys.path.append(str(Path.cwd()))


def enable_pubmed():
    session = SessionLocal()
    try:
        # Get admin user
        admin = session.query(UserModel).filter_by(email="admin@artana.org").first()
        if not admin:
            print("Admin user not found.")
            users = session.query(UserModel).all()
            print(f"Found {len(users)} users:")
            for u in users:
                print(f"- {u.email}")
            return

        # Check if rule exists
        existing = (
            session.query(DataSourceActivationModel)
            .filter_by(catalog_entry_id="pubmed", scope=ActivationScopeEnum.GLOBAL)
            .first()
        )

        if existing:
            print("PubMed global rule already exists.")
            existing.permission_level = PermissionLevelEnum.AVAILABLE
        else:
            print("Creating PubMed global rule.")
            new_rule = DataSourceActivationModel(
                id=str(uuid4()),
                catalog_entry_id="pubmed",
                scope=ActivationScopeEnum.GLOBAL,
                permission_level=PermissionLevelEnum.AVAILABLE,
                updated_by=str(admin.id),
            )
            session.add(new_rule)

        session.commit()
        print("PubMed enabled globally.")
    except Exception as e:
        print(f"Error enabling PubMed: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    enable_pubmed()
