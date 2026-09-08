"""Exact public schema exported from project_db PostgreSQL 9.5.25 on 2026-09-08.
Includes all 14 tables, sequences, foreign keys, indexes, checks and triggers.
"""
from pathlib import Path
from alembic import op
from sqlalchemy import inspect

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    connection = op.get_bind()
    existing = set(inspect(connection).get_table_names(schema="public")) - {"alembic_version"}
    if existing:
        raise RuntimeError("Non-empty schema: verify and stamp baseline; never recreate existing tables")
    ddl = (Path(__file__).resolve().parents[1] / "baseline.sql").read_text(encoding="utf-8-sig")
    # psycopg2 executes the complete dump, including dollar-quoted trigger functions.
    connection.exec_driver_sql(ddl)

def downgrade():
    raise RuntimeError("Baseline rollback is backup restore into a NEW isolated DB; automatic data deletion is disabled")
