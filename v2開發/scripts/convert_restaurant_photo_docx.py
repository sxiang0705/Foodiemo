"""Extract the curated restaurant image URLs from the supplied DOCX into CSV."""
import argparse
import csv
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / "Downloads" / "餐廳圖片連結填寫表_照片不重複_找不到照片則換示意圖.docx"
DEFAULT_OUTPUT = ROOT / "data" / "restaurant_image_links.csv"
NAMESPACE = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
FIELDS = ("restaurant_id", "title", "restaurant_image_url", "food_image_url")
HEADERS = ("餐廳編號", "餐廳名稱", "餐廳圖片連結", "食物圖片連結")


def valid_https(value):
    if not value:
        return True
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443) and not any(ch.isspace() for ch in value))
    except ValueError:
        return False


def read_rows(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    tables = root.findall(".//w:tbl", NAMESPACE)
    if len(tables) != 1:
        raise ValueError("Expected exactly one DOCX table")

    def cells(row):
        return ["".join(node.text or "" for node in cell.findall(".//w:t", NAMESPACE)).strip()
                for cell in row.findall("./w:tc", NAMESPACE)]

    rows = [cells(row) for row in tables[0].findall("./w:tr", NAMESPACE)]
    if not rows or tuple(rows[0]) != HEADERS:
        raise ValueError("DOCX table headers do not match the expected restaurant image columns")
    result = []
    for row in rows[1:]:
        if len(row) != 4:
            raise ValueError("A DOCX row does not contain exactly four columns")
        restaurant_id, title, restaurant_url, food_url = (item.strip() for item in row)
        if not restaurant_id.isdigit() or int(restaurant_id) < 1 or not title:
            raise ValueError("A restaurant row has a missing or invalid ID/title")
        if not valid_https(restaurant_url) or not valid_https(food_url):
            raise ValueError(f"Restaurant {restaurant_id} has an invalid or non-HTTPS image URL")
        if not restaurant_url and not food_url:
            raise ValueError(f"Restaurant {restaurant_id} has no image URL")
        result.append(dict(zip(FIELDS, (str(int(restaurant_id)), title,
                                        restaurant_url or "", food_url or ""))))
    if not result:
        raise ValueError("DOCX contains no restaurant data")
    ids = [row["restaurant_id"] for row in result]
    if len(ids) != len(set(ids)):
        raise ValueError("DOCX contains duplicate restaurant IDs")
    urls = [row[key] for row in result for key in FIELDS[2:] if row[key]]
    duplicates = [url for url, count in Counter(urls).items() if count > 1]
    if duplicates:
        raise ValueError(f"DOCX contains {len(duplicates)} repeated image URL(s); review the source first")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    rows = read_rows(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    restaurant_images = sum(bool(row["restaurant_image_url"]) for row in rows)
    print(f"Wrote {len(rows)} validated rows: {restaurant_images} restaurant images, "
          f"{len(rows) - restaurant_images} food-image-only fallbacks; no duplicate URLs.")
    print(f"CSV: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f"Conversion stopped: {exc}", file=sys.stderr)
        raise SystemExit(1)
