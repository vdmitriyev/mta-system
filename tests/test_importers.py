import gzip

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect

from app import importers
from app.importers import DATASETS, import_dataset_task, import_kind
from app.importers.adventureworks_custom import importer_adventureworks_custom as aw
from app.importers.airbnb import importer_airbnb_csv as airbnb
from app.importers.flights import importer_flights as flights
from app.tasks import TaskError
from tests.conftest import add_postgresql, add_user


@pytest.fixture
def target(tmp_path):
    """SQLite database in place of the PostgreSQL database of a user"""

    return f"sqlite:///{tmp_path / 'target.db'}"


def tables(uri) -> dict:
    engine = create_engine(uri)
    with engine.connect() as connection:
        return {
            name: connection.exec_driver_sql(f'SELECT count(*) FROM "{name}"').scalar()
            for name in inspect(engine).get_table_names()
        }


def test_flights_import(target):
    flights.run_import(target)
    result = tables(target)
    assert list(result) == ["flights"]
    assert result["flights"] > 100


def test_flights_import_twice_fails(target):
    flights.run_import(target)
    with pytest.raises(ValueError, match="already exists"):
        flights.run_import(target)


def test_upper_case_to_underscore():
    assert aw.upper_case_to_underscore("DimDate") == "dim_date"
    assert aw.upper_case_to_underscore("date") == "date"
    assert aw.upper_case_to_underscore("_Hidden") == "__hidden"


def test_adventureworks_import(target, tmp_path, monkeypatch):
    data_dir = tmp_path / "aw"
    data_dir.mkdir()
    (data_dir / "DimCurrency.csv").write_text(
        "CurrencyKey,CurrencyName\n1,Euro\n2,Dollar\n"
    )
    (data_dir / "DimProduct.csv").write_text("ProductKey|ProductName\n1|Bike\n")
    monkeypatch.setattr(
        aw,
        "TABLES",
        [
            ("DimCurrency.csv", "dim_currency", ","),
            ("DimProduct.csv", "dim_product", "|"),
        ],
    )

    aw.run_import(target, data_dir=data_dir)
    assert tables(target) == {"dim_currency": 2, "dim_product": 1}
    engine = create_engine(target)
    columns = [c["name"] for c in inspect(engine).get_columns("dim_currency")]
    assert columns == ["currency_key", "currency_name"]


def test_adventureworks_reports_the_first_error(target, tmp_path, monkeypatch):
    data_dir = tmp_path / "aw"
    data_dir.mkdir()
    (data_dir / "DimCurrency.csv").write_text("CurrencyKey\n1\n")
    monkeypatch.setattr(
        aw,
        "TABLES",
        [("Missing.csv", "missing", ","), ("DimCurrency.csv", "dim_currency", ",")],
    )
    with pytest.raises(FileNotFoundError, match="Missing.csv"):
        aw.run_import(target, data_dir=data_dir)
    assert tables(target) == {"dim_currency": 1}


def test_adventureworks_archive_has_all_tables():
    from zipfile import ZipFile

    with ZipFile(aw.CUR_DIR / "data.zip") as archive:
        names = set(archive.namelist())
    assert {csv_name for csv_name, _table, _sep in aw.TABLES} <= names


class FakeDownload:
    def __init__(self, status_code=200, content=b"id,name\n1,a\n2,b\n"):
        self.status_code = status_code
        self.content = content

    def iter_content(self, chunk_size=1):
        yield self.content


def test_airbnb_import(target, tmp_path, monkeypatch):
    requested = []

    def fake_get(url, **kwargs):
        requested.append(url)
        if url.endswith(".gz"):
            return FakeDownload(content=gzip.compress(b"ID,Name\n1,a\n"))
        return FakeDownload()

    monkeypatch.setattr(airbnb, "DATA_DIR", tmp_path / "airbnb")
    monkeypatch.setattr(airbnb.requests, "get", fake_get)

    airbnb.run_import(target, date_to_download="2024-01-01")
    assert len(requested) == len(airbnb.FILES)
    assert all("/2024-01-01/" in url for url in requested)
    result = tables(target)
    assert result["airbnb_listings_berlin_summary"] == 2
    assert result["airbnb_listings_berlin_full"] == 1
    assert set(result) == {table for _path, table in airbnb.FILES}


def test_airbnb_download_is_reused(tmp_path, monkeypatch):
    monkeypatch.setattr(airbnb, "DATA_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(
        airbnb.requests, "get", lambda url, **k: calls.append(url) or FakeDownload()
    )
    first = airbnb.download("http://x/data/file.csv")
    second = airbnb.download("http://x/data/file.csv")
    assert first == second and len(calls) == 1
    assert pd.read_csv(first).shape == (2, 2)
    airbnb.download("http://x/data/file.csv", force_download=True)
    assert len(calls) == 2


def test_airbnb_download_error(target, tmp_path, monkeypatch):
    monkeypatch.setattr(airbnb, "DATA_DIR", tmp_path)
    monkeypatch.setattr(airbnb.requests, "get", lambda url, **k: FakeDownload(404))
    assert airbnb.download("http://x/file.csv") is None
    with pytest.raises(Exception, match="download"):
        airbnb.run_import(target)


def test_import_kind():
    assert import_kind("flights") == "import:flights"
    assert set(DATASETS) == {"flights", "airbnb", "adventureworks"}


def test_import_task_uses_the_database_of_the_user(db, student, monkeypatch):
    add_postgresql(db, student)
    seen = []

    class FakeModule:
        @staticmethod
        def run_import(uri):
            seen.append(uri)

    monkeypatch.setattr(importers.importlib, "import_module", lambda name: FakeModule)
    message = import_dataset_task(db, student.itid, "flights")
    assert message == "Flights was imported into your PostgreSQL database"
    assert seen == [
        "postgresql+psycopg2://bicourse_user_01:pg-secret-11@localhost:5432/bicourse_db_01"
    ]


def test_import_task_without_database(db, student):
    with pytest.raises(TaskError, match="no PostgreSQL database"):
        import_dataset_task(db, student.itid, "flights")


def test_import_task_shows_the_first_line_of_the_error(db, student, monkeypatch):
    add_postgresql(db, student)

    class FakeModule:
        @staticmethod
        def run_import(uri):
            raise ValueError("Table 'flights' already exists.\nlong SQL text")

    monkeypatch.setattr(importers.importlib, "import_module", lambda name: FakeModule)
    with pytest.raises(TaskError) as error:
        import_dataset_task(db, student.itid, "flights")
    assert (
        str(error.value) == "Flights was not imported: Table 'flights' already exists."
    )


def test_import_task_shows_only_the_name_of_a_missing_file(
    db, student, monkeypatch, tmp_path
):
    add_postgresql(db, student)
    missing = tmp_path / "secret" / "folder" / "tutorial_flights.zip"
    monkeypatch.setattr(flights, "DATA_FILE", missing)
    with pytest.raises(TaskError) as error:
        import_dataset_task(db, student.itid, "flights")
    assert (
        str(error.value)
        == "Flights was not imported: file not found: tutorial_flights.zip"
    )


def test_adventureworks_missing_file_shows_only_its_name(
    db, student, monkeypatch, tmp_path
):
    add_postgresql(db, student)
    data_dir = tmp_path / "aw"
    data_dir.mkdir()
    monkeypatch.setattr(aw, "TABLES", [("DimDate.csv", "dim_date", ",")])
    real_run_import = aw.run_import
    monkeypatch.setattr(
        aw, "run_import", lambda uri: real_run_import(uri, data_dir=data_dir)
    )
    with pytest.raises(TaskError) as error:
        import_dataset_task(db, student.itid, "adventureworks")
    assert str(error.value) == (
        "AdventureWorks was not imported: file not found: DimDate.csv"
    )
    assert str(tmp_path) not in str(error.value)


def test_all_importer_modules_exist():
    import importlib

    for _title, module_name in DATASETS.values():
        assert callable(importlib.import_module(module_name).run_import)


def test_another_user_cannot_be_imported_for(db, student):
    other = add_user(db, email="other@uni.example", number=3)
    add_postgresql(db, other, number=3)
    with pytest.raises(TaskError):
        import_dataset_task(db, student.itid, "flights")
