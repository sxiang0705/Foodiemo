from alembic import context
from app.core.config import Settings
from app.core.database import build_engine
from app.core.safety import assert_test_target, assert_test_connection

config = context.config
if context.is_offline_mode():
    raise RuntimeError("Offline migrations disabled: target identity must be verified")

connection = config.attributes.get("connection")
if connection is not None:
    context.configure(connection=connection, target_metadata=None, version_table_schema="public")
    with context.begin_transaction():
        context.run_migrations()
else:
    settings = Settings.from_env()
    assert_test_target(settings)
    engine = build_engine(settings, readonly=False)
    with engine.begin() as connection:
        assert_test_connection(connection, settings)
        context.configure(connection=connection, target_metadata=None, version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
