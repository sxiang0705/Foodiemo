"""Read-only metadata inventory. No table rows, password hashes or DSNs."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import inspect, text
from app.core.config import Settings
from app.core.database import build_engine


def inventory(engine):
    with engine.connect() as c:
        identity = c.execute(text("SELECT current_database() AS database, "
            "current_setting('server_version') AS version, "
            "current_setting('transaction_read_only') AS readonly, "
            "has_database_privilege(current_database(), 'CREATE') AS can_create_schema" )).mappings().one()
        result = {"identity": dict(identity), "tables": {}}
        inspector = inspect(c)
        for table in inspector.get_table_names(schema="public"):
            result["tables"][table] = {
                "columns": [{"name": x["name"], "type": str(x["type"]),
                    "nullable": x["nullable"], "default": x["default"], "timezone": getattr(x["type"], "timezone", None)}
                    for x in inspector.get_columns(table, schema="public")],
                "pk": inspector.get_pk_constraint(table, schema="public"),
                "foreign_keys": inspector.get_foreign_keys(table, schema="public"),
                "unique": inspector.get_unique_constraints(table, schema="public"),
                "checks": inspector.get_check_constraints(table, schema="public"),
                "indexes": inspector.get_indexes(table, schema="public"),
            }
        result["roles"] = [dict(r) for r in c.execute(text("SELECT rolname, rolcreatedb, rolsuper "
            "FROM pg_roles WHERE rolname=current_user")).mappings()]
        result["table_permissions"] = [dict(r) for r in c.execute(text("SELECT tablename, "
            "has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename), 'SELECT') AS can_select, "
            "has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename), 'INSERT') AS can_insert, "
            "has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename), 'UPDATE') AS can_update, "
            "has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename), 'DELETE') AS can_delete "
            "FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).mappings()]
        return result


if __name__ == "__main__":
    try:
        engine = build_engine(Settings.from_env())
        result = inventory(engine)
        print(json.dumps(result, ensure_ascii=True, indent=2, default=str))
    except Exception as exc:
        print("Read-only inspection failed: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
