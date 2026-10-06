"""Safely create and load the restaurant tag tables from the supplied CSVs."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
import shlex
import sys
import tempfile
from collections import Counter
from pathlib import Path
from uuid import uuid4

import paramiko
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0010_restaurant_tags"
PREVIOUS_REVISION = "0009_restaurant_price_range"
ALLOWED_CATEGORIES = {"cuisine", "food_type", "amenity", "feature", "occasion", "time_period"}
TAG_FIELDS = {"tag_id", "tag_name", "category", "is_active"}
LINK_FIELDS = {"restaurant_id", "tag_id"}


def read_csv(path, expected_fields):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or set(reader.fieldnames) != expected_fields:
            raise RuntimeError(f"Unexpected CSV columns in {path.name}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise RuntimeError(f"Malformed CSV row in {path.name}")
    return rows


def validate_sources(tags_path, links_path):
    tags = read_csv(tags_path, TAG_FIELDS)
    links = read_csv(links_path, LINK_FIELDS)
    if not tags or not links:
        raise RuntimeError("Both tag CSV files must contain data rows")

    tag_ids = set()
    category_names = set()
    category_counts = Counter()
    for row in tags:
        tag_id = (row.get("tag_id") or "").strip()
        tag_name = (row.get("tag_name") or "").strip()
        category = (row.get("category") or "").strip()
        active = (row.get("is_active") or "").strip().lower()
        if not tag_id.isdigit() or int(tag_id) <= 0 or int(tag_id) > 2147483647:
            raise RuntimeError("A tag_id is missing or outside the positive integer range")
        if int(tag_id) in tag_ids:
            raise RuntimeError("Duplicate tag_id in tags_rows.csv")
        if not tag_name or category not in ALLOWED_CATEGORIES:
            raise RuntimeError("A tag has an empty name or an unsupported category")
        if active not in {"true", "false"}:
            raise RuntimeError("is_active must contain true or false")
        if (category, tag_name) in category_names:
            raise RuntimeError("Duplicate tag_name within a category")
        tag_ids.add(int(tag_id))
        category_names.add((category, tag_name))
        category_counts[category] += 1

    link_pairs = set()
    restaurant_ids = set()
    for row in links:
        restaurant_id = (row.get("restaurant_id") or "").strip()
        tag_id = (row.get("tag_id") or "").strip()
        if not restaurant_id.isdigit() or int(restaurant_id) <= 0 or int(restaurant_id) > 9223372036854775807:
            raise RuntimeError("A restaurant_id is missing or outside the positive bigint range")
        if not tag_id.isdigit() or int(tag_id) <= 0 or int(tag_id) not in tag_ids:
            raise RuntimeError("restaurant_tags_rows.csv contains a missing or unknown tag_id")
        pair = (int(restaurant_id), int(tag_id))
        if pair in link_pairs:
            raise RuntimeError("Duplicate restaurant_id/tag_id pair in restaurant_tags_rows.csv")
        link_pairs.add(pair)
        restaurant_ids.add(int(restaurant_id))

    return tags, links, {
        "tags_rows": len(tags),
        "tag_categories": dict(sorted(category_counts.items())),
        "restaurant_tags_rows": len(links),
        "restaurants_with_tags": len(restaurant_ids),
        "tagged_restaurant_ids": sorted(restaurant_ids),
    }


def write_stage_files(tags, links):
    tag_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False)
    link_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False)
    try:
        tag_writer = csv.writer(tag_file, lineterminator="\n")
        tag_writer.writerow(["tag_id", "tag_name", "category", "is_active"])
        for row in tags:
            tag_writer.writerow([
                row["tag_id"].strip(), row["tag_name"].strip(), row["category"].strip(),
                row["is_active"].strip().lower(),
            ])
        link_writer = csv.writer(link_file, lineterminator="\n")
        link_writer.writerow(["restaurant_id", "tag_id"])
        for row in links:
            link_writer.writerow([row["restaurant_id"].strip(), row["tag_id"].strip()])
        tag_file.close()
        link_file.close()
        return Path(tag_file.name), Path(link_file.name)
    except Exception:
        tag_file.close()
        link_file.close()
        Path(tag_file.name).unlink(missing_ok=True)
        Path(link_file.name).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--tags-csv", type=Path, default=Path.home() / "Downloads" / "tags_rows.csv")
    parser.add_argument("--restaurant-tags-csv", type=Path,
                        default=Path.home() / "Downloads" / "restaurant_tags_rows.csv")
    parser.add_argument("--target-db", default="project_db",
                        help="project_db or the isolated restore database named in the backup manifest")
    parser.add_argument("--apply", action="store_true")
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

    load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
    if os.environ.get("DB_NAME") != "project_db":
        raise RuntimeError("Unexpected target database")
    tags, links, summary = validate_sources(args.tags_csv, args.restaurant_tags_csv)
    tag_stage, link_stage = write_stage_files(tags, links)
    ssh = paramiko.SSHClient()
    remote_files = []

    def run(command, data=b""):
        stdin, stdout, stderr = ssh.exec_command("sudo -S -p '' -u postgres " + command, timeout=180)
        stdin.write(os.environ["DB_PASSWORD"] + "\n")
        stdin.flush()
        if data:
            stdin.channel.sendall(data)
        stdin.channel.shutdown_write()
        output, errors = stdout.read(), stderr.read()
        if stdout.channel.recv_exit_status():
            (ROOT / ".local" / "migration-error.log").write_bytes(errors)
            raise RuntimeError("Remote migration failed; see ignored .local/migration-error.log")
        return output

    def sql(query):
        return run("psql -X -v ON_ERROR_STOP=1 -At -d " + shlex.quote(args.target_db),
                   query.encode("utf-8")).decode().strip()

    try:
        ssh.load_host_keys(str(ROOT / ".local" / "known_hosts"))
        ssh.connect(os.environ["SSH_HOST"], port=int(os.getenv("SSH_PORT", "22")),
                    username=os.environ["SSH_USER"], password=os.environ["DB_PASSWORD"],
                    look_for_keys=False, allow_agent=False, timeout=10)
        if run("pg_dump --version").decode().strip() != "pg_dump (PostgreSQL) 9.5.25":
            raise RuntimeError("Unexpected PostgreSQL tool version")
        version = sql("SELECT version_num FROM public.alembic_version;")
        if version != PREVIOUS_REVISION:
            raise RuntimeError(f"Expected migration {PREVIOUS_REVISION}; found {version}")
        if sql("SELECT COALESCE(to_regclass('public.tags_rows')::text, '') || '|' || "
               "COALESCE(to_regclass('public.restaurant_tags_rows')::text, '');") != "|":
            raise RuntimeError("Tag tables already exist; inspect before importing")

        schema = run("pg_dump --schema-only --no-owner --no-privileges --schema=public "
                     "--exclude-table=public.alembic_version --dbname=" + shlex.quote(args.target_db))
        if schema != (backup_dir / "schema.sql").read_bytes():
            raise RuntimeError("Schema changed since backup; create a fresh backup")
        for table, count in manifest.get("source_counts", {}).items():
            ident = '"' + table.replace('"', '""') + '"'
            if int(sql("SELECT count(*) FROM public." + ident + ";")) != count:
                raise RuntimeError("Table counts changed since backup; create a fresh backup")
        print(f"Verified: {args.target_db} matches the backup schema, checksum, and row counts", flush=True)
        print(json.dumps({k: v for k, v in summary.items() if k != "tagged_restaurant_ids"},
                         ensure_ascii=False), flush=True)
        if not args.apply:
            print("Read-only preflight complete. Add --apply to create and populate both tag tables.")
            return

        remote_tag = uuid4().hex
        remote_tags = f"/tmp/foodiemo_tags_{remote_tag}.csv"
        remote_links = f"/tmp/foodiemo_restaurant_tags_{remote_tag}.csv"
        remote_files = [remote_tags, remote_links]
        sftp = ssh.open_sftp()
        try:
            sftp.put(str(tag_stage), remote_tags)
            sftp.chmod(remote_tags, 0o644)
            sftp.put(str(link_stage), remote_links)
            sftp.chmod(remote_links, 0o644)
        finally:
            sftp.close()

        spec = importlib.util.spec_from_file_location(
            "migration", ROOT / "migrations" / "versions" / "0010_restaurant_tags.py")
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        ddl = ";\n".join(migration.DDL) + ";\n"
        source_count_checks = "\n".join(
            "IF (SELECT count(*) FROM public.\"{0}\") <> {1} THEN "
            "RAISE EXCEPTION 'source table count changed since backup: {0}'; END IF;".format(
                table.replace('"', '""'), int(count))
            for table, count in manifest.get("source_counts", {}).items()
        )
        tag_count = len(tags)
        link_count = len(links)
        restaurant_ids = ",".join(str(value) for value in summary["tagged_restaurant_ids"])
        sql_script = f"""BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='180s';
DO $$ BEGIN
{source_count_checks}
END $$;
{ddl}
CREATE TEMP TABLE tag_import_stage (
 tag_id integer, tag_name text, category text, is_active boolean
) ON COMMIT DROP;
COPY tag_import_stage FROM '{remote_tags}' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
CREATE TEMP TABLE restaurant_tag_import_stage (
 restaurant_id bigint, tag_id integer
) ON COMMIT DROP;
COPY restaurant_tag_import_stage FROM '{remote_links}' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
DO $$
BEGIN
 IF (SELECT count(*) FROM tag_import_stage) <> {tag_count}
    OR (SELECT count(*) FROM restaurant_tag_import_stage) <> {link_count} THEN
   RAISE EXCEPTION 'CSV row count changed during import';
 END IF;
 IF EXISTS (SELECT tag_id FROM tag_import_stage GROUP BY tag_id HAVING count(*) <> 1)
    OR EXISTS (SELECT category, tag_name FROM tag_import_stage GROUP BY category, tag_name HAVING count(*) <> 1)
    OR EXISTS (SELECT restaurant_id, tag_id FROM restaurant_tag_import_stage
               GROUP BY restaurant_id, tag_id HAVING count(*) <> 1) THEN
   RAISE EXCEPTION 'Duplicate tag or restaurant/tag key in staged CSV';
 END IF;
 IF EXISTS (SELECT 1 FROM tag_import_stage
            WHERE tag_id <= 0 OR btrim(tag_name) = ''
               OR category NOT IN ('cuisine','food_type','amenity','feature','occasion','time_period')) THEN
   RAISE EXCEPTION 'Invalid tag values in staged CSV';
 END IF;
 IF EXISTS (SELECT 1 FROM restaurant_tag_import_stage s
            LEFT JOIN tag_import_stage t ON t.tag_id=s.tag_id WHERE t.tag_id IS NULL)
    OR EXISTS (SELECT 1 FROM restaurant_tag_import_stage s
               LEFT JOIN public.restaurant_rows r ON r.restaurant_id=s.restaurant_id
               WHERE r.restaurant_id IS NULL) THEN
   RAISE EXCEPTION 'A tag mapping references a missing tag or restaurant';
 END IF;
 IF (SELECT count(*) FROM public.restaurant_rows WHERE restaurant_id IN ({restaurant_ids}))
      <> {len(summary['tagged_restaurant_ids'])} THEN
   RAISE EXCEPTION 'The restaurant source set changed; tag mapping contains unknown restaurants';
 END IF;
END $$;
INSERT INTO public.tags_rows (tag_id, tag_name, category, is_active)
 SELECT tag_id, tag_name, category, is_active FROM tag_import_stage ORDER BY tag_id;
INSERT INTO public.restaurant_tags_rows (restaurant_id, tag_id)
 SELECT restaurant_id, tag_id FROM restaurant_tag_import_stage ORDER BY restaurant_id, tag_id;
SELECT setval('public.tags_rows_tag_id_seq', GREATEST(
 (SELECT COALESCE(MAX(tag_id), 1) FROM public.tags_rows), 1
), true);
DO $$
BEGIN
 IF (SELECT count(*) FROM public.tags_rows) <> {tag_count}
    OR (SELECT count(*) FROM public.restaurant_tags_rows) <> {link_count} THEN
   RAISE EXCEPTION 'Post-import row count mismatch';
 END IF;
 IF EXISTS (SELECT tag_id, tag_name, category, is_active FROM tag_import_stage
            EXCEPT SELECT tag_id, tag_name, category, is_active FROM public.tags_rows)
    OR EXISTS (SELECT tag_id, tag_name, category, is_active FROM public.tags_rows
               EXCEPT SELECT tag_id, tag_name, category, is_active FROM tag_import_stage)
    OR EXISTS (SELECT restaurant_id, tag_id FROM restaurant_tag_import_stage
               EXCEPT SELECT restaurant_id, tag_id FROM public.restaurant_tags_rows)
    OR EXISTS (SELECT restaurant_id, tag_id FROM public.restaurant_tags_rows
               EXCEPT SELECT restaurant_id, tag_id FROM restaurant_tag_import_stage) THEN
   RAISE EXCEPTION 'Imported tag data does not exactly match the CSVs';
 END IF;
 IF (SELECT last_value FROM public.tags_rows_tag_id_seq)
      < (SELECT max(tag_id) FROM public.tags_rows) THEN
   RAISE EXCEPTION 'Tag ID sequence is behind the imported IDs';
 END IF;
END $$;
UPDATE public.alembic_version SET version_num='{REVISION}'
 WHERE version_num='{PREVIOUS_REVISION}';
DO $$ BEGIN
 IF (SELECT version_num FROM public.alembic_version) <> '{REVISION}' THEN
   RAISE EXCEPTION 'Could not advance Alembic version';
 END IF;
END $$;
COMMIT;
"""
        run("psql -X -v ON_ERROR_STOP=1 -At -d " + shlex.quote(args.target_db), sql_script.encode("utf-8"))

        final_version = sql("SELECT version_num FROM public.alembic_version;")
        final_counts = sql("SELECT (SELECT count(*) FROM public.tags_rows)||'|'||"
                           "(SELECT count(*) FROM public.restaurant_tags_rows)||'|'||"
                           "(SELECT count(DISTINCT restaurant_id) FROM public.restaurant_tags_rows)||'|'||"
                           "(SELECT count(*) FROM public.restaurant_rows WHERE restaurant_id NOT IN "
                           "(SELECT DISTINCT restaurant_id FROM public.restaurant_tags_rows));")
        restaurant_count = int(sql("SELECT count(*) FROM public.restaurant_rows;"))
        tagged_restaurants = len(summary["tagged_restaurant_ids"])
        expected_counts = f"{tag_count}|{link_count}|{tagged_restaurants}|{restaurant_count-tagged_restaurants}"
        if final_version != REVISION:
            raise RuntimeError("Post-check migration revision failed")
        if final_counts != expected_counts:
            raise RuntimeError(f"Post-check tag table counts failed: {final_counts}")
        print(f"Applied {REVISION} to {args.target_db}; imported the supplied tag dictionary and mappings.")
        print(f"Verified tags_rows|restaurant_tags_rows|tagged restaurants|untagged restaurants = {final_counts}")
    finally:
        for path in (tag_stage, link_stage):
            path.unlink(missing_ok=True)
        for remote_path in remote_files:
            try:
                ssh.exec_command("rm -f -- " + shlex.quote(remote_path), timeout=10)
            except Exception:
                pass
        ssh.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Migration stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
