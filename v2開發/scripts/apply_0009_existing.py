"""Add restaurant price ranges and safely synchronize the supplied CSV snapshot."""
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
REVISION = "0009_restaurant_price_range"
PREVIOUS_REVISION = "0008_email_less_first_admin"
PRICE_RANGES = {
    "150 元以下", "151–300 元", "301–600 元", "601–1000 元", "1001 元以上"
}
RESTAURANT_FIELDS = {
    "restaurant_id", "googleMaps_id", "title", "lng", "lat", "reviewsCount",
    "created_at", "address", "website", "categoryName", "phone", "topic_avg",
    "price_range",
}
REVIEW_FIELDS = {"reviews_id", "created_at", "raw_text", "cleaned_features", "restaurant_id"}


def read_csv(path, expected_fields):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or set(reader.fieldnames) != expected_fields:
            raise RuntimeError(f"Unexpected CSV columns in {path.name}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise RuntimeError(f"Malformed CSV row in {path.name}")
    return rows


def validate_sources(restaurant_path, review_path):
    restaurants = read_csv(restaurant_path, RESTAURANT_FIELDS)
    reviews = read_csv(review_path, REVIEW_FIELDS)
    if not restaurants or not reviews:
        raise RuntimeError("Both CSV files must contain data rows")

    restaurant_ids = set()
    google_ids = set()
    prices = Counter()
    blank_review_counts = 0
    for row in restaurants:
        restaurant_id = (row.get("restaurant_id") or "").strip()
        google_id = (row.get("googleMaps_id") or "").strip()
        if not restaurant_id.isdigit() or not google_id or not (row.get("title") or "").strip():
            raise RuntimeError("A restaurant row has a missing or invalid identity")
        if restaurant_id in restaurant_ids or google_id in google_ids:
            raise RuntimeError("Duplicate restaurant_id or googleMaps_id in CSV")
        restaurant_ids.add(restaurant_id)
        google_ids.add(google_id)
        price = (row.get("price_range") or "").strip()
        if price and price not in PRICE_RANGES:
            raise RuntimeError("Unexpected price_range category in CSV")
        prices[price or "<blank>"] += 1
        if not (row.get("reviewsCount") or "").strip():
            blank_review_counts += 1

    review_ids = set()
    review_restaurant_ids = set()
    for row in reviews:
        review_id = (row.get("reviews_id") or "").strip()
        restaurant_id = (row.get("restaurant_id") or "").strip()
        if not review_id.isdigit() or review_id in review_ids:
            raise RuntimeError("Missing or duplicate reviews_id in CSV")
        if not restaurant_id.isdigit() or not (row.get("raw_text") or "").strip():
            raise RuntimeError("A review row has a missing restaurant_id or blank raw_text")
        review_ids.add(review_id)
        review_restaurant_ids.add(restaurant_id)
    if not review_restaurant_ids.issubset(restaurant_ids):
        raise RuntimeError("A review references a restaurant absent from restaurant_rows.csv")

    return restaurants, reviews, {
        "restaurant_rows": len(restaurants),
        "reviews_rows": len(reviews),
        "price_range_values": dict(prices),
        "blank_reviewsCount_rows": blank_review_counts,
        "distinct_review_restaurants": len(review_restaurant_ids),
    }


def write_stage_files(restaurants, reviews):
    restaurant_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False)
    review_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", suffix=".csv", delete=False)
    try:
        restaurant_writer = csv.writer(restaurant_file, lineterminator="\n")
        restaurant_writer.writerow(["restaurant_id", "googleMaps_id", "title", "lng", "lat", "reviewsCount",
                                    "created_at", "address", "website", "categoryName", "phone", "topic_avg", "price_range"])
        for row in restaurants:
            restaurant_writer.writerow([(row.get(field) or "").strip() for field in
                ["restaurant_id", "googleMaps_id", "title", "lng", "lat", "reviewsCount",
                 "created_at", "address", "website", "categoryName", "phone", "topic_avg", "price_range"]])
        review_writer = csv.writer(review_file, lineterminator="\n")
        review_writer.writerow(["restaurant_id", "created_at", "raw_text", "cleaned_features"])
        for row in reviews:
            review_writer.writerow([row["restaurant_id"].strip(), row["created_at"].strip(),
                                    row["raw_text"], row.get("cleaned_features") or ""])
        restaurant_file.close()
        review_file.close()
        return Path(restaurant_file.name), Path(review_file.name)
    except Exception:
        restaurant_file.close()
        review_file.close()
        Path(restaurant_file.name).unlink(missing_ok=True)
        Path(review_file.name).unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--restaurant-csv", type=Path, default=Path.home() / "Downloads" / "restaurant_rows.csv")
    parser.add_argument("--reviews-csv", type=Path, default=Path.home() / "Downloads" / "reviews_rows.csv")
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

    load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
    if os.environ.get("DB_NAME") != "project_db":
        raise RuntimeError("Unexpected target database")
    restaurants, reviews, source_summary = validate_sources(args.restaurant_csv, args.reviews_csv)
    restaurant_stage, review_stage = write_stage_files(restaurants, reviews)

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
        return run("psql -X -v ON_ERROR_STOP=1 -At -d project_db", query.encode("utf-8")).decode().strip()

    try:
        ssh.load_host_keys(str(ROOT / ".local" / "known_hosts"))
        ssh.connect(os.environ["SSH_HOST"], port=int(os.getenv("SSH_PORT", "22")),
                    username=os.environ["SSH_USER"], password=os.environ["DB_PASSWORD"],
                    look_for_keys=False, allow_agent=False, timeout=10)
        if run("pg_dump --version").decode().strip() != "pg_dump (PostgreSQL) 9.5.25":
            raise RuntimeError("Unexpected PostgreSQL tool version")
        version = sql("SELECT version_num FROM public.alembic_version;")
        if version not in {PREVIOUS_REVISION, REVISION}:
            raise RuntimeError(f"Expected migration {PREVIOUS_REVISION} or {REVISION}; found {version}")
        schema = run("pg_dump --schema-only --no-owner --no-privileges --schema=public "
                     "--exclude-table=public.alembic_version --dbname=project_db")
        if schema != (backup_dir / "schema.sql").read_bytes():
            raise RuntimeError("Schema changed since backup; create a fresh backup")
        for table, count in manifest.get("source_counts", {}).items():
            ident = '"' + table.replace('"', '""') + '"'
            if int(sql("SELECT count(*) FROM public." + ident + ";")) != count:
                raise RuntimeError("Data counts changed since backup; create a fresh backup")
        print("Verified: live project_db matches the backup schema, checksum, and row counts", flush=True)
        print(json.dumps(source_summary, ensure_ascii=False), flush=True)
        if not args.apply:
            print("Read-only preflight complete. Add --apply to add price_range and synchronize the CSV data.")
            return

        remote_tag = uuid4().hex
        remote_restaurants = f"/tmp/foodiemo_restaurants_{remote_tag}.csv"
        remote_reviews = f"/tmp/foodiemo_reviews_{remote_tag}.csv"
        remote_files = [remote_restaurants, remote_reviews]
        sftp = ssh.open_sftp()
        try:
            sftp.put(str(restaurant_stage), remote_restaurants)
            sftp.chmod(remote_restaurants, 0o644)
            sftp.put(str(review_stage), remote_reviews)
            sftp.chmod(remote_reviews, 0o644)
        finally:
            sftp.close()

        restaurant_count = len(restaurants)
        review_count = len(reviews)
        ddl = ""
        if version == PREVIOUS_REVISION:
            spec = importlib.util.spec_from_file_location(
                "migration", ROOT / "migrations" / "versions" / "0009_restaurant_price_range.py")
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            ddl = migration.DDL + "\n"

        sql_script = f"""BEGIN;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='180s';
{ddl}CREATE TEMP TABLE restaurant_refresh_stage (
 restaurant_id text, "googleMaps_id" text, title text, lng text, lat text,
 "reviewsCount" text, created_at text, address text, website text,
 "categoryName" text, phone text, topic_avg text, price_range text
) ON COMMIT DROP;
COPY restaurant_refresh_stage FROM '{remote_restaurants}' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
CREATE TEMP TABLE review_refresh_stage (
 restaurant_id bigint NOT NULL, created_at timestamptz NOT NULL,
 raw_text text NOT NULL, cleaned_features text
) ON COMMIT DROP;
COPY review_refresh_stage FROM '{remote_reviews}' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
DO $$
BEGIN
 IF (SELECT count(*) FROM restaurant_refresh_stage) <> {restaurant_count} THEN
   RAISE EXCEPTION 'restaurant CSV row count changed during import';
 END IF;
 IF EXISTS (SELECT 1 FROM restaurant_refresh_stage GROUP BY restaurant_id HAVING count(*) <> 1)
    OR EXISTS (SELECT 1 FROM restaurant_refresh_stage GROUP BY "googleMaps_id" HAVING count(*) <> 1) THEN
   RAISE EXCEPTION 'duplicate restaurant identity in staged CSV';
 END IF;
 IF (SELECT count(*) FROM public.restaurant_rows) <> {restaurant_count}
    OR EXISTS (SELECT restaurant_id::bigint, "googleMaps_id" FROM restaurant_refresh_stage
               EXCEPT SELECT restaurant_id, "googleMaps_id" FROM public.restaurant_rows)
    OR EXISTS (SELECT restaurant_id, "googleMaps_id" FROM public.restaurant_rows
               EXCEPT SELECT restaurant_id::bigint, "googleMaps_id" FROM restaurant_refresh_stage) THEN
   RAISE EXCEPTION 'restaurant IDs or Google Maps identities changed; refusing replacement';
 END IF;
 IF EXISTS (
   SELECT 1 FROM restaurant_refresh_stage s
   JOIN public.restaurant_rows r ON r.restaurant_id=s.restaurant_id::bigint
   WHERE NULLIF(btrim(r.title), '') IS DISTINCT FROM NULLIF(btrim(s.title), '')
      OR r.lng IS DISTINCT FROM NULLIF(s.lng, '')::double precision
      OR r.lat IS DISTINCT FROM NULLIF(s.lat, '')::double precision
      OR r."reviewsCount" IS DISTINCT FROM COALESCE(NULLIF(s."reviewsCount", '')::integer, r."reviewsCount")
      OR r.created_at IS DISTINCT FROM NULLIF(s.created_at, '')::timestamptz
      OR NULLIF(btrim(r.address), '') IS DISTINCT FROM NULLIF(btrim(s.address), '')
      OR NULLIF(btrim(r.website), '') IS DISTINCT FROM NULLIF(btrim(s.website), '')
      OR NULLIF(btrim(r."categoryName"), '') IS DISTINCT FROM NULLIF(btrim(s."categoryName"), '')
      OR NULLIF(btrim(r.phone), '') IS DISTINCT FROM NULLIF(btrim(s.phone), '')
      OR NULLIF(btrim(r.topic_avg), '') IS DISTINCT FROM NULLIF(btrim(s.topic_avg), '')
 ) THEN
   RAISE EXCEPTION 'restaurant source fields changed; review before applying';
 END IF;
 IF EXISTS (SELECT 1 FROM restaurant_refresh_stage WHERE NULLIF(price_range, '') IS NOT NULL
            AND price_range NOT IN ('150 元以下','151–300 元','301–600 元','601–1000 元','1001 元以上')) THEN
   RAISE EXCEPTION 'unexpected price_range category';
 END IF;
 IF (SELECT count(*) FROM review_refresh_stage) <> {review_count}
    OR EXISTS (SELECT 1 FROM review_refresh_stage s LEFT JOIN public.restaurant_rows r
               ON r.restaurant_id=s.restaurant_id WHERE r.restaurant_id IS NULL) THEN
   RAISE EXCEPTION 'review count or restaurant reference validation failed';
 END IF;
END $$;
UPDATE public.restaurant_rows r
 SET price_range=NULLIF(s.price_range, '')
 FROM restaurant_refresh_stage s
 WHERE r.restaurant_id=s.restaurant_id::bigint;
CREATE TEMP TABLE current_review_ranked ON COMMIT DROP AS
 SELECT reviews_id, restaurant_id, raw_text,
        row_number() OVER (PARTITION BY restaurant_id, md5(raw_text) ORDER BY reviews_id) AS rn
 FROM public.reviews_rows;
CREATE TEMP TABLE incoming_review_ranked ON COMMIT DROP AS
 SELECT restaurant_id, created_at, raw_text, cleaned_features,
        row_number() OVER (PARTITION BY restaurant_id, md5(raw_text) ORDER BY created_at, raw_text) AS rn
 FROM review_refresh_stage;
CREATE TEMP TABLE review_rows_to_delete ON COMMIT DROP AS
 SELECT old.reviews_id
 FROM current_review_ranked old
 LEFT JOIN incoming_review_ranked new
   ON new.restaurant_id=old.restaurant_id AND md5(new.raw_text)=md5(old.raw_text)
  AND new.rn=old.rn AND new.raw_text=old.raw_text
 WHERE new.restaurant_id IS NULL;
CREATE TEMP TABLE review_rows_to_insert ON COMMIT DROP AS
 SELECT new.restaurant_id, new.created_at, new.raw_text, new.cleaned_features
 FROM incoming_review_ranked new
 LEFT JOIN current_review_ranked old
   ON old.restaurant_id=new.restaurant_id AND md5(old.raw_text)=md5(new.raw_text)
  AND old.rn=new.rn AND old.raw_text=new.raw_text
 WHERE old.reviews_id IS NULL;
DELETE FROM public.reviews_rows r USING review_rows_to_delete d WHERE r.reviews_id=d.reviews_id;
SELECT setval('public.reviews_rows_reviews_id_seq', GREATEST(
  (SELECT COALESCE(MAX(reviews_id), 1) FROM public.reviews_rows),
  (SELECT last_value FROM public.reviews_rows_reviews_id_seq)
), true);
INSERT INTO public.reviews_rows (restaurant_id, created_at, raw_text, cleaned_features)
 SELECT restaurant_id, created_at, raw_text, cleaned_features FROM review_rows_to_insert;
DO $$
BEGIN
 IF (SELECT count(*) FROM public.restaurant_rows) <> {restaurant_count}
    OR (SELECT count(*) FROM public.reviews_rows) <> {review_count} THEN
   RAISE EXCEPTION 'post-sync row count mismatch';
 END IF;
 IF EXISTS (SELECT 1 FROM (
   SELECT restaurant_id, raw_text, count(*) AS n FROM public.reviews_rows GROUP BY restaurant_id, raw_text
 ) current_rows FULL OUTER JOIN (
   SELECT restaurant_id, raw_text, count(*) AS n FROM review_refresh_stage GROUP BY restaurant_id, raw_text
 ) incoming_rows USING (restaurant_id, raw_text)
 WHERE COALESCE(current_rows.n, 0) <> COALESCE(incoming_rows.n, 0)) THEN
   RAISE EXCEPTION 'post-sync review content does not match CSV';
 END IF;
 IF (SELECT count(*) FROM public.restaurant_rows WHERE price_range IS NOT NULL) < 1 THEN
   RAISE EXCEPTION 'price_range values were not applied';
 END IF;
END $$;
"""
        if version == PREVIOUS_REVISION:
            sql_script += (f"UPDATE public.alembic_version SET version_num='{REVISION}' "
                           f"WHERE version_num='{PREVIOUS_REVISION}';\n")
        sql_script += "COMMIT;\n"
        run("psql -X -v ON_ERROR_STOP=1 -At -d project_db", sql_script.encode("utf-8"))

        final_version = sql("SELECT version_num FROM public.alembic_version;")
        final_counts = sql("SELECT (SELECT count(*) FROM public.restaurant_rows)||'|'||"
                           "(SELECT count(*) FROM public.reviews_rows)||'|'||"
                           "(SELECT count(*) FROM public.restaurant_rows WHERE price_range IS NOT NULL)||'|'||"
                           "(SELECT count(*) FROM public.restaurant_rows WHERE price_range IS NULL);")
        if final_version != REVISION:
            raise RuntimeError("Post-check migration revision failed")
        expected_counts = f"{restaurant_count}|{review_count}|{restaurant_count-source_summary['price_range_values'].get('<blank>',0)}|{source_summary['price_range_values'].get('<blank>',0)}"
        if final_counts != expected_counts:
            raise RuntimeError("Post-check table counts or price_range values failed")
        print(f"Applied {REVISION}; kept restaurant identities, synchronized review text by content, and preserved unchanged review IDs")
        print(f"Verified restaurant_rows|reviews_rows|priced|unpriced = {final_counts}")
    finally:
        for path in (restaurant_stage, review_stage):
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
