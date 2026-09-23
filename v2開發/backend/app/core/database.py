from sqlalchemy import create_engine


def build_engine(settings, *, readonly=True):
    # Read requests use this engine; mutations use an explicitly writable engine.
    options = "-c statement_timeout=5000 -c lock_timeout=3000 -c timezone=UTC"
    if readonly:
        options += " -c default_transaction_read_only=on"
    return create_engine(settings.url, pool_pre_ping=True, pool_size=5,
                         max_overflow=5, pool_timeout=5, hide_parameters=True,
                         connect_args={"connect_timeout": 5, "options": options},
                         execution_options={"isolation_level": "REPEATABLE READ" if readonly else "READ COMMITTED"})
