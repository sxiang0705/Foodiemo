"""Verify a real backup and exact live schema before stamping ONLY the baseline.
Does not upgrade existing application tables. Run inspect/backup first.
"""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import paramiko
from dotenv import load_dotenv
from alembic import command
from alembic.config import Config
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings
from app.core.database import build_engine

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-manifest", type=Path, required=True)
    parser.add_argument("--use-db-password-for-ssh", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", encoding="utf-8-sig")
    settings = Settings.from_env()
    if settings.database != "project_db":
        raise RuntimeError("This entry point is only for the inventoried project_db")
    manifest = json.loads(args.backup_manifest.read_text(encoding="utf-8"))
    backup = args.backup_manifest.parent / "project_db.dump"
    if (manifest["source"] != "project_db" or not manifest["schema_matches"]
            or not manifest["counts_match"] or hashlib.sha256(backup.read_bytes()).hexdigest() != manifest["sha256"]):
        raise RuntimeError("Verified backup required")
    password = settings.password if args.use_db_password_for_ssh else getpass.getpass("SSH / sudo password: ")
    ssh = paramiko.SSHClient()
    ssh.load_host_keys(str(ROOT / ".local" / "known_hosts"))
    ssh.connect(os.environ["SSH_HOST"], port=int(os.getenv("SSH_PORT", "22")),
                username=os.environ["SSH_USER"], password=password, look_for_keys=False, allow_agent=False, timeout=10)
    try:
        stdin, stdout, stderr = ssh.exec_command("sudo -S -p '' -u postgres pg_dump --schema-only --no-owner --no-privileges --schema=public --exclude-table=public.alembic_version --dbname=project_db")
        stdin.write(password + "\n"); stdin.flush(); stdin.channel.shutdown_write()
        schema = stdout.read()
        if stdout.channel.recv_exit_status() or schema != (ROOT / "migrations/baseline.sql").read_bytes():
            raise RuntimeError("Live schema drift; do not stamp")
    finally:
        ssh.close()
    print("Live schema and restored backup verified.")
    if args.apply:
        engine = build_engine(settings, readonly=False)
        with engine.begin() as c:
            if c.execute(text("SELECT current_database()")).scalar() != "project_db":
                raise RuntimeError("Unexpected database")
            if c.execute(text("SELECT to_regclass('public.alembic_version')")).scalar():
                versions = c.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
                if versions != ["0001_baseline"]:
                    raise RuntimeError("Existing migration version differs; never overwrite it")
            # No upgrade path is exposed here; only Alembic version bookkeeping.
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = c
            command.stamp(config, "0001_baseline")
            assert c.execute(text("SELECT version_num FROM public.alembic_version")).scalar() == "0001_baseline"
        engine.dispose()
        print("Existing database baseline stamped; application tables unchanged.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Baseline verification/stamp failed: " + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
