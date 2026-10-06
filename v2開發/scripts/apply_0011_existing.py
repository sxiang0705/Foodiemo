"""Safely add and import curated restaurant/food image links after a verified backup."""
import argparse
import csv
import getpass
import hashlib
import importlib.util
import json
import os
import shlex
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import paramiko
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0011_restaurant_image_links"
PREVIOUS_REVISION = "0010_restaurant_tags"
FIELDS = {"restaurant_id", "title", "restaurant_image_url", "food_image_url"}
MAX_ID = 9223372036854775807


def read_source(path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or set(reader.fieldnames) != FIELDS:
            raise RuntimeError("Unexpected columns in restaurant image CSV")
        rows = list(reader)
    if not rows or any(None in row for row in rows):
        raise RuntimeError("Restaurant image CSV is empty or malformed")
    ids, urls = set(), set()
    for row in rows:
        value = (row.get("restaurant_id") or "").strip()
        if not value.isdigit() or not 1 <= int(value) <= MAX_ID:
            raise RuntimeError("A restaurant_id is missing or outside the positive bigint range")
        restaurant_id = int(value)
        if restaurant_id in ids:
            raise RuntimeError("Duplicate restaurant_id in image CSV")
        ids.add(restaurant_id)
        if not (row.get("title") or "").strip():
            raise RuntimeError("A restaurant title is empty")
        if not row.get("restaurant_image_url") and not row.get("food_image_url"):
            raise RuntimeError(f"Restaurant {restaurant_id} has no image URL")
        for key in ("restaurant_image_url", "food_image_url"):
            url = (row.get(key) or "").strip()
            if not url:
                continue
            try:
                parsed = urlsplit(url)
                valid = (parsed.scheme == "https" and bool(parsed.hostname)
                         and parsed.username is None and parsed.password is None
                         and parsed.port in (None, 443) and len(url) <= 2048
                         and not any(ch.isspace() for ch in url))
            except ValueError:
                valid = False
            if not valid:
                raise RuntimeError(f"Restaurant {restaurant_id} has an invalid or non-HTTPS URL")
            if url in urls:
                raise RuntimeError("Repeated image URL in source CSV")
            urls.add(url)
        row["restaurant_id"] = str(restaurant_id)
        row["title"] = row["title"].strip()
        row["restaurant_image_url"] = (row.get("restaurant_image_url") or "").strip()
        row["food_image_url"] = (row.get("food_image_url") or "").strip()
    return rows


def stage_source(rows):
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False)
    try:
        writer = csv.DictWriter(handle, fieldnames=("restaurant_id", "title", "restaurant_image_url", "food_image_url"),
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        handle.close()
        return Path(handle.name)
    except Exception:
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True,
                        help="Verified path under v2開發/backups, e.g. backups/20261007_120000")
    parser.add_argument("--image-csv", type=Path, default=ROOT / "data" / "restaurant_image_links.csv")
    parser.add_argument("--target-db", default="project_db",
                        help="project_db or the isolated restore database named in the backup manifest")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--use-db-password-for-ssh", action="store_true")
    args = parser.parse_args()

    backups = (ROOT / "backups").resolve()
    backup_dir = (ROOT / args.backup_dir).resolve()
    if not backup_dir.is_relative_to(backups):
        raise RuntimeError("Backup path outside v2開發/backups")
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    dump = backup_dir / "project_db.dump"
    if (manifest.get("source") != "project_db" or not manifest.get("counts_match")
            or not manifest.get("schema_matches") or not dump.is_file()
            or hashlib.sha256(dump.read_bytes()).hexdigest() != manifest.get("sha256")):
        raise RuntimeError("Backup is missing, unverified, or has a checksum mismatch")
    if manifest.get("restore_database") == "project_db":
        raise RuntimeError("Backup manifest points to the live database")
    if args.target_db not in {"project_db", manifest.get("restore_database")}:
        raise RuntimeError("Target must be project_db or the isolated restore database from this backup")
    if args.target_db != "project_db" and not args.target_db.startswith("foodiemo_v2_restore_"):
        raise RuntimeError("Refusing to modify a database that is not the isolated restore")

    rows = read_source(args.image_csv)
    restaurant_image_count = sum(bool(row["restaurant_image_url"]) for row in rows)
    food_image_count = sum(bool(row["food_image_url"]) for row in rows)
    expected_restaurants = int(manifest.get("source_counts", {}).get("restaurant_rows", -1))
    if expected_restaurants != len(rows):
        raise RuntimeError("Image CSV row count does not match backed-up restaurant_rows")

    load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
    if os.environ.get("DB_NAME") != "project_db":
        raise RuntimeError("Unexpected configured source database")
    password = os.environ["DB_PASSWORD"] if args.use_db_password_for_ssh else getpass.getpass("SSH / sudo password: ")
    stage = stage_source(rows)
    remote_path = "/tmp/foodiemo_images_" + uuid4().hex + ".csv"
    ssh = paramiko.SSHClient()

    def run(command, data=b""):
        stdin, stdout, stderr = ssh.exec_command("sudo -S -p '' -u postgres " + command, timeout=180)
        stdin.write(password + "\n")
        stdin.flush()
        if data:
            stdin.channel.sendall(data)
        stdin.channel.shutdown_write()
        output, errors = stdout.read(), stderr.read()
        if stdout.channel.recv_exit_status():
            (ROOT / ".local" / "migration-error.log").write_bytes(errors)
            raise RuntimeError("Remote import failed; see ignored .local/migration-error.log")
        return output

    def sql(query):
        return run("psql -X -v ON_ERROR_STOP=1 -At -d " + shlex.quote(args.target_db),
                   query.encode("utf-8")).decode().strip()

    try:
        ssh.load_host_keys(str(ROOT / ".local" / "known_hosts"))
        ssh.connect(os.environ["SSH_HOST"], port=int(os.getenv("SSH_PORT", "22")),
                    username=os.environ["SSH_USER"], password=password,
                    look_for_keys=False, allow_agent=False, timeout=10)
        if run("pg_dump --version").decode().strip() != "pg_dump (PostgreSQL) 9.5.25":
            raise RuntimeError("Unexpected PostgreSQL tool version")
        if sql("SELECT version_num FROM public.alembic_version;") != PREVIOUS_REVISION:
            raise RuntimeError(f"Expected migration {PREVIOUS_REVISION}; target has another version")
        existing_columns = sql("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' "
                               "AND table_name='restaurant_rows' AND column_name IN "
                               "('restaurant_image_url','food_image_url');")
        if existing_columns != "0":
            raise RuntimeError("Image URL columns already exist; inspect target before retrying")
        schema = run("pg_dump --schema-only --no-owner --no-privileges --schema=public "
                     "--exclude-table=public.alembic_version --dbname=" + shlex.quote(args.target_db))
        if schema != (backup_dir / "schema.sql").read_bytes():
            raise RuntimeError("Schema changed since backup; create a fresh backup")
        for table, count in manifest.get("source_counts", {}).items():
            ident = '"' + table.replace('"', '""') + '"'
            if int(sql("SELECT count(*) FROM public." + ident + ";")) != int(count):
                raise RuntimeError("Table counts changed since backup; create a fresh backup")

        sftp = ssh.open_sftp()
        try:
            sftp.put(str(stage), remote_path)
            sftp.chmod(remote_path, 0o644)
        finally:
            sftp.close()

        source_checks = "\n".join(
            "IF (SELECT count(*) FROM public.\"{0}\") <> {1} THEN "
            "RAISE EXCEPTION 'source table count changed since backup'; END IF;".format(
                table.replace('"', '""'), int(count))
            for table, count in manifest.get("source_counts", {}).items()
        )
        check_and_stage = f"""CREATE TEMP TABLE restaurant_image_import_stage (
 restaurant_id bigint, title text, restaurant_image_url text, food_image_url text
) ON COMMIT DROP;
COPY restaurant_image_import_stage FROM '{remote_path}' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
DO $$ BEGIN
 IF (SELECT count(*) FROM restaurant_image_import_stage) <> {len(rows)} THEN
   RAISE EXCEPTION 'image CSV row count mismatch'; END IF;
 IF (SELECT count(*) FROM public.restaurant_rows) <> {expected_restaurants}
    OR EXISTS (SELECT restaurant_id FROM public.restaurant_rows EXCEPT SELECT restaurant_id FROM restaurant_image_import_stage)
    OR EXISTS (SELECT restaurant_id FROM restaurant_image_import_stage EXCEPT SELECT restaurant_id FROM public.restaurant_rows) THEN
   RAISE EXCEPTION 'restaurant ID set differs from the curated image CSV'; END IF;
 IF EXISTS (SELECT 1 FROM restaurant_image_import_stage s JOIN public.restaurant_rows r USING (restaurant_id)
            WHERE s.title IS DISTINCT FROM r.title) THEN
   RAISE EXCEPTION 'restaurant title does not match the curated image CSV'; END IF;
 IF EXISTS (SELECT 1 FROM restaurant_image_import_stage
            WHERE (restaurant_image_url IS NULL OR restaurant_image_url = '')
              AND (food_image_url IS NULL OR food_image_url = ''))
    OR EXISTS (SELECT 1 FROM restaurant_image_import_stage
               WHERE (restaurant_image_url IS NOT NULL AND restaurant_image_url !~ '^https://[^[:space:]]+$')
                  OR (food_image_url IS NOT NULL AND food_image_url !~ '^https://[^[:space:]]+$')) THEN
   RAISE EXCEPTION 'invalid or missing HTTPS image URL'; END IF;
 IF EXISTS (SELECT image_url FROM (
      SELECT restaurant_image_url AS image_url FROM restaurant_image_import_stage WHERE restaurant_image_url IS NOT NULL AND restaurant_image_url <> ''
      UNION ALL
      SELECT food_image_url FROM restaurant_image_import_stage WHERE food_image_url IS NOT NULL AND food_image_url <> ''
    ) urls GROUP BY image_url HAVING count(*) > 1) THEN
   RAISE EXCEPTION 'duplicate image URL in import staging'; END IF;
END $$;
"""
        if args.apply:
            spec = importlib.util.spec_from_file_location(
                "migration", ROOT / "migrations" / "versions" / "0011_restaurant_image_links.py")
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            ddl = ";\n".join(migration.DDL) + ";\n"
            sql_script = f"""BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='180s';
DO $$ BEGIN
{source_checks}
END $$;
{check_and_stage}
{ddl}
UPDATE public.restaurant_rows r
 SET restaurant_image_url=NULLIF(s.restaurant_image_url,''),
     food_image_url=NULLIF(s.food_image_url,'')
 FROM restaurant_image_import_stage s WHERE r.restaurant_id=s.restaurant_id;
DO $$ BEGIN
 IF (SELECT count(*) FROM public.restaurant_rows WHERE restaurant_image_url IS NOT NULL) <> {restaurant_image_count}
    OR (SELECT count(*) FROM public.restaurant_rows WHERE food_image_url IS NOT NULL) <> {food_image_count} THEN
   RAISE EXCEPTION 'post-import image count mismatch'; END IF;
END $$;
UPDATE public.alembic_version SET version_num='{REVISION}' WHERE version_num='{PREVIOUS_REVISION}';
DO $$ BEGIN
 IF (SELECT version_num FROM public.alembic_version) <> '{REVISION}' THEN
   RAISE EXCEPTION 'could not advance Alembic version'; END IF;
END $$;
COMMIT;
"""
        else:
            sql_script = "BEGIN;\n" + check_and_stage + "ROLLBACK;\n"
        run("psql -X -v ON_ERROR_STOP=1 -At -d " + shlex.quote(args.target_db), sql_script.encode("utf-8"))
        if not args.apply:
            print(f"Read-only preflight passed for {args.target_db}: {len(rows)} restaurant IDs/titles match; "
                  f"{restaurant_image_count} restaurant images, {food_image_count} food-image URLs; no duplicates.")
            print("Add --apply to update the isolated restore first, then repeat against project_db after verification.")
            return

        version = sql("SELECT version_num FROM public.alembic_version;")
        counts = sql("SELECT count(*)||'|'||count(restaurant_image_url)||'|'||count(food_image_url) "
                     "FROM public.restaurant_rows;")
        expected = f"{expected_restaurants}|{restaurant_image_count}|{food_image_count}"
        if version != REVISION or counts != expected:
            raise RuntimeError("Post-import migration revision or image counts do not match expected values")
        print(f"Applied {REVISION} to {args.target_db}; verified restaurant rows|restaurant images|food images = {counts}.")
    finally:
        stage.unlink(missing_ok=True)
        try:
            ssh.exec_command("rm -f -- " + shlex.quote(remote_path), timeout=10)
        except Exception:
            pass
        ssh.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Image migration stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
