"""Backup project_db and verify a restore in a NEW isolated database.
Existing databases are never overwritten. SSH known host must be enrolled first.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import sys
from datetime import datetime, timezone
import paramiko
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-db-password-for-ssh", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    password = os.environ["DB_PASSWORD"] if args.use_db_password_for_ssh else getpass.getpass("SSH / sudo password: ")
    ssh = paramiko.SSHClient()
    ssh.load_host_keys(str(ROOT / ".local" / "known_hosts"))
    ssh.connect(os.environ["SSH_HOST"], port=int(os.getenv("SSH_PORT", "22")),
                username=os.environ["SSH_USER"], password=password,
                look_for_keys=False, allow_agent=False, timeout=10)

    def run(command, data=b""):
        stdin, stdout, stderr = ssh.exec_command("sudo -S -p '' -u postgres " + command, timeout=120)
        stdin.write(password + "\n")
        stdin.flush()
        if data:
            stdin.channel.sendall(data)
        stdin.channel.shutdown_write()
        output = stdout.read()
        errors = stderr.read()
        if stdout.channel.recv_exit_status():
            (ROOT / ".local" / "remote-error.log").write_bytes(errors)
            raise RuntimeError("Remote command failed; see ignored .local/remote-error.log")
        return output

    def sql(query, database="postgres"):
        return run("psql -X -v ON_ERROR_STOP=1 -At -d " + shlex.quote(database), query.encode())

    try:
        version = run("pg_dump --version").decode().strip()
        if version != "pg_dump (PostgreSQL) 9.5.25":
            raise RuntimeError("Verify tool version before continuing")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = ROOT / "backups" / stamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup = run("pg_dump --format=custom --dbname=project_db")
        (backup_dir / "project_db.dump").write_bytes(backup)
        schema = run("pg_dump --schema-only --no-owner --no-privileges --schema=public --exclude-table=public.alembic_version --dbname=project_db")
        (backup_dir / "schema.sql").write_bytes(schema)
        (ROOT / "migrations").mkdir(exist_ok=True)
        baseline = ROOT / "migrations" / "baseline.sql"
        if not baseline.exists():
            baseline.write_bytes(schema)
        elif baseline.read_bytes() != schema:
            raise RuntimeError("Existing baseline differs; review instead of overwriting history")
        restore_db = "foodiemo_v2_restore_" + stamp
        sql(f'CREATE DATABASE "{restore_db}" TEMPLATE template0;')
        sql(f'REVOKE ALL ON DATABASE "{restore_db}" FROM PUBLIC;')
        run(f"pg_restore --exit-on-error --single-transaction --dbname={restore_db}", backup)
        tables = sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;", "project_db").decode().splitlines()
        def counts(db):
            return {t: int(sql('SELECT count(*) FROM public."' + t.replace('"', '""') + '";', db)) for t in tables}
        source_counts, restored_counts = counts("project_db"), counts(restore_db)
        restored_schema = run("pg_dump --schema-only --no-owner --no-privileges --schema=public --exclude-table=public.alembic_version --dbname=" + restore_db)
        if source_counts != restored_counts or schema != restored_schema:
            raise RuntimeError("Restore mismatch; inspect locally")
        manifest = {"created_utc": stamp, "source": "project_db", "restore_database": restore_db,
                    "tool": version, "sha256": hashlib.sha256(backup).hexdigest(),
                    "table_count": len(tables), "counts_match": True, "schema_matches": True,
                    "source_counts": source_counts, "restored_counts": restored_counts}
        (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Backup and isolated restore verified: " + str(backup_dir), flush=True)
        exists = sql("SELECT datname FROM pg_database WHERE datname='foodiemo_v2_test';")
        if exists.strip():
            print("Test database already exists; unchanged.")
            return
        test_password = secrets.token_urlsafe(32)
        sql("CREATE ROLE foodiemo_v2_test_owner LOGIN PASSWORD '" + test_password + "' NOSUPERUSER NOCREATEDB NOCREATEROLE;")
        sql("CREATE DATABASE foodiemo_v2_test OWNER foodiemo_v2_test_owner TEMPLATE template0;")
        sql("REVOKE ALL ON DATABASE foodiemo_v2_test FROM PUBLIC; COMMENT ON DATABASE foodiemo_v2_test IS 'foodiemo-v2-isolated';")
        sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT ALL ON SCHEMA public TO foodiemo_v2_test_owner;", "foodiemo_v2_test")
        test_env = (f"APP_ENV=test\nDB_HOST={os.environ['DB_HOST']}\nDB_PORT={os.environ['DB_PORT']}\n"
            f"DB_NAME=foodiemo_v2_test\nDB_USER=foodiemo_v2_test_owner\nDB_PASSWORD={test_password}\n"
            f"TEST_EXPECTED_HOST={os.environ['DB_HOST']}\nTEST_EXPECTED_PORT={os.environ['DB_PORT']}\n"
            "TEST_ALLOW_WRITE=foodiemo-v2-isolated\n")
        (ROOT / ".env.test").write_text(test_env, encoding="utf-8")
        (ROOT / "test-uploads").mkdir(exist_ok=True)
        print("Isolated test database, dedicated role and ignored .env.test created.")
    finally:
        ssh.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Backup/provision failed: " + type(exc).__name__ + ". Check local logs and permissions.", file=sys.stderr)
        sys.exit(1)
