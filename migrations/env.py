from alembic import context

from app import models  # noqa: F401  (registers the tables)
from app.config import get_settings
from app.database import Base, get_engine, init_engine

target_metadata = Base.metadata


def run_migrations_offline():
    """Writes the SQL of the migrations, without a database connection"""

    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = get_engine() or init_engine(get_settings().database_url)
    with engine.connect() as connection:
        # SQLite can change tables only in "batch" mode
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
