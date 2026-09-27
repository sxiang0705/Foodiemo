"""Apply the reviewed admin-console migration only after a matching verified backup."""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import paramiko
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    backups = (ROOT / "backups").resolve()
    folder = (ROOT / args.backup_dir).resolve()
    if not folder.is_relative_to(backups):
        raise RuntimeError("Backup path outside backups")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8-sig"))
    if (manifest.get("source") != "project_db" or not manifest.get("counts_match")
            or not manifest.get("schema_matches")):
        raise RuntimeError("Unverified backup")
    dump = folder / "project_db.dump"
    if hashlib.sha256(dump.read_bytes()).hexdigest() != manifest.get("sha256"):
        raise RuntimeError("Backup checksum mismatch")

    load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
    if os.environ.get("DB_NAME") != "project_db":
        raise RuntimeError("Unexpected target database")
    ssh = paramiko.SSHClient()
    ssh.load_host_keys(str(ROOT / ".local" / "known_hosts"))
    ssh.connect(os.environ["SSH_HOST"], port=int(os.getenv("SSH_PORT", "22")),
                username=os.environ["SSH_USER"], password=os.environ["DB_PASSWORD"],
                look_for_keys=False, allow_agent=False, timeout=10)

    def run(command, data=b""):
        stdin, stdout, stderr = ssh.exec_command("sudo -S -p '' -u postgres " + command, timeout=120)
        stdin.write(os.environ["DB_PASSWORD"] + "\n")
        stdin.flush()
        if data:
            stdin.channel.sendall(data)
        stdin.channel.shutdown_write()
        out, err = stdout.read(), stderr.read()
        if stdout.channel.recv_exit_status():
            (ROOT / ".local" / "migration-error.log").write_bytes(err)
            raise RuntimeError("Remote migration failed; see ignored .local/migration-error.log")
        return out

    def sql(query):
        return run("psql -X -v ON_ERROR_STOP=1 -At -d project_db", query.encode()).decode().strip()

    try:
        if run("pg_dump --version").decode().strip() != "pg_dump (PostgreSQL) 9.5.25":
            raise RuntimeError("Unexpected PostgreSQL tool version")
        version = sql("SELECT version_num FROM public.alembic_version;")
        if version == "0007_admin_console":
            print("0007 already applied; no changes")
            return
        if version != "0006_usernames":
            raise RuntimeError("Expected 0006_usernames before 0007")
        schema = run("pg_dump --schema-only --no-owner --no-privileges --schema=public "
                     "--exclude-table=public.alembic_version --dbname=project_db")
        if schema != (folder / "schema.sql").read_bytes():
            raise RuntimeError("Schema changed since backup; create a new backup")
        for table, count in manifest.get("source_counts", {}).items():
            ident = '"' + table.replace('"', '""') + '"'
            if int(sql("SELECT count(*) FROM public." + ident + ";")) != count:
                raise RuntimeError("Data counts changed; create a new backup")
        print("Verified: project_db at 0006, matching backup checksum, restored schema, and row counts", flush=True)
        if not args.apply:
            print("Read-only preflight complete. Add --apply to run the transaction.")
            return

        spec = importlib.util.spec_from_file_location("migration", ROOT / "migrations/versions/0007_admin_console.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        role = '"' + os.environ["DB_USER"].replace('"', '""') + '"'
        query = ("BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='30s';\n" + module.DDL)
        query += "\nGRANT SELECT,INSERT,UPDATE,DELETE ON public.content_reports,public.admin_audit_logs TO " + role + ";"
        query += "\nGRANT USAGE,SELECT ON SEQUENCE public.content_reports_report_id_seq,public.admin_audit_logs_audit_id_seq TO " + role + ";"
        query += "\nUPDATE public.alembic_version SET version_num='0007_admin_console' WHERE version_num='0006_usernames'; COMMIT;"
        sql(query)
        if sql("SELECT version_num FROM public.alembic_version;") != "0007_admin_console":
            raise RuntimeError("Post-check revision failed")
        for table in ("content_reports", "admin_audit_logs"):
            if sql("SELECT to_regclass('public." + table + "');") not in (table, "public." + table):
                raise RuntimeError("Post-check table failed: " + table)
        if sql("SELECT count(*) FROM public.users WHERE account_status NOT IN ('active','suspended');") != "0":
            raise RuntimeError("Post-check account statuses failed")
        print("Applied 0007 transactionally; report/audit grants and schema checks verified")
    finally:
        ssh.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Migration stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
