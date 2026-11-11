"""Datasets that users can import into their PostgreSQL database"""

import importlib
import logging

from sqlalchemy.orm import Session

from app.models import PostgreSQLService
from app.tasks import TaskError

logger = logging.getLogger(__name__)

# dataset -> (title, module with run_import(db_connect_uri))
DATASETS = {
    "flights": ("Flights", "app.importers.flights.importer_flights"),
    "airbnb": ("Airbnb", "app.importers.airbnb.importer_airbnb_csv"),
    "adventureworks": (
        "AdventureWorks",
        "app.importers.adventureworks_custom.importer_adventureworks_custom",
    ),
}


def import_kind(dataset: str) -> str:
    """Kind of the background task that imports the dataset"""

    return f"import:{dataset}"


def import_dataset_task(db: Session, user_id: int, dataset: str) -> str:
    """Background task: imports a dataset into the PostgreSQL database of the user"""

    from app.users import postgresql_uri

    title, module_name = DATASETS[dataset]
    entry = (
        db.query(PostgreSQLService)
        .filter(
            PostgreSQLService.user_id == user_id, PostgreSQLService.deleted.is_(False)
        )
        .order_by(PostgreSQLService.itid.desc())
        .first()
    )
    if entry is None:
        raise TaskError("You have no PostgreSQL database")

    try:
        importlib.import_module(module_name).run_import(postgresql_uri(entry))
    except Exception as error:
        logger.exception("Import of %s failed for user %s", dataset, user_id)
        # e.g. "table already exists": the user can act on the first line
        raise TaskError(f"{title} was not imported: {str(error).splitlines()[0][:200]}")
    return f"{title} was imported into your PostgreSQL database"
