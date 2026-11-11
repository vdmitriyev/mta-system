from alembic import command
from sqlalchemy import create_engine, inspect

from app.cli.database import alembic_config
from app.database import Base, get_db, get_engine, init_engine, session_scope
from app.models import CONTAINER_SERVICES, SERVICE_MODELS, Users
from tests.conftest import add_user


def test_to_dict(db):
    user = add_user(db)
    data = user.to_dict()
    assert data["email"] == user.email
    assert set(data) == {column.name for column in Users.__table__.columns}


def test_defaults_of_a_user(db):
    user = add_user(db)
    db.refresh(user)
    assert user.active is True
    assert user.deleted is False
    assert user.created_at is not None


def test_service_models_have_user_and_state_columns():
    assert set(CONTAINER_SERVICES) <= set(SERVICE_MODELS)
    for name, model in SERVICE_MODELS.items():
        columns = model.__table__.columns
        assert model.__tablename__ == f"{name}_service"
        assert {"user_id", "created", "deleted"} <= set(columns.keys())
    for name in CONTAINER_SERVICES:
        assert f"{name}_docker_port" in SERVICE_MODELS[name].__table__.columns


def test_get_db_closes_the_session(app):
    generator = get_db()
    session = next(generator)
    assert session.execute(Users.__table__.select()).all() == []
    generator.close()


def test_init_engine_creates_the_folder_and_uses_wal(tmp_path):
    engine = init_engine(f"sqlite:///{tmp_path / 'new' / 'folder' / 'app.db'}")
    with engine.connect() as connection:
        mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode == "wal"
    assert (tmp_path / "new" / "folder").is_dir()
    assert get_engine() is engine


def test_sessions_do_not_expire_objects_after_commit(db):
    user = add_user(db)
    with session_scope() as other:
        loaded = other.get(Users, user.itid)
    assert loaded.email == user.email


def test_migrations_create_the_tables_of_the_models(settings, tmp_path):
    init_engine(settings.database_url)
    command.upgrade(alembic_config(), "head")

    migrated = inspect(get_engine())
    tables = set(migrated.get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)

    reference = create_engine(f"sqlite:///{tmp_path / 'reference.db'}")
    Base.metadata.create_all(reference)
    expected = inspect(reference)
    for table in tables:
        migrated_columns = {c["name"] for c in migrated.get_columns(table)}
        expected_columns = {c["name"] for c in expected.get_columns(table)}
        assert migrated_columns == expected_columns, table


def test_migrations_can_go_back(settings):
    init_engine(settings.database_url)
    command.upgrade(alembic_config(), "head")
    # the revision before the table service_settings
    command.downgrade(alembic_config(), "8c1d2e7a4b90")
    assert "service_settings" not in inspect(get_engine()).get_table_names()
    command.upgrade(alembic_config(), "head")
    assert "service_settings" in inspect(get_engine()).get_table_names()
