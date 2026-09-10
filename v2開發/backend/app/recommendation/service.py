"""Original three-card contract with an interchangeable, read-only provider."""
import base64
import binascii
import math
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode
from sqlalchemy import select
from app.models.restaurants import Restaurant

MAX_ID = 9223372036854775807

def decode_cursor(cursor):
    if not cursor:
        return 0
    try:
        raw = base64.b64decode(cursor, altchars=b"-_", validate=True).decode("ascii")
        version, value = raw.split(":")
        if version != "1" or not value.isdigit() or not 0 <= int(value) <= MAX_ID:
            raise ValueError
        if encode_cursor(int(value)) != cursor:
            raise ValueError
        return int(value)
    except (ValueError, UnicodeError, binascii.Error):
        raise ValueError("Invalid recommendation cursor") from None

def encode_cursor(value):
    return base64.urlsafe_b64encode(f"1:{value}".encode()).decode()

@dataclass(frozen=True)
class RecommendationContext:
    count: int = 3
    after_id: int = 0
    # Stage 2/5 will supply verified server identity and stored preferences.
    user_id: str | None = None
    preferences: dict | None = None

class Provider(Protocol):
    version: str
    def select(self, session, context: RecommendationContext): ...

class RotationProvider:
    version = "rotation-v1"
    def select(self, session, context):
        rows = list(session.scalars(select(Restaurant)
            .where(Restaurant.restaurant_id > context.after_id)
            .order_by(Restaurant.restaurant_id).limit(context.count)))
        if len(rows) < context.count and context.after_id:
            rows += list(session.scalars(select(Restaurant)
                .where(Restaurant.restaurant_id <= context.after_id)
                .order_by(Restaurant.restaurant_id).limit(context.count-len(rows))))
        return rows

def map_link(row):
    # googleMaps_id is not assumed to be a Google Places ID.
    if (row.latitude is not None and row.longitude is not None
        and math.isfinite(row.latitude) and math.isfinite(row.longitude)
        and -90 <= row.latitude <= 90 and -180 <= row.longitude <= 180):
        query = f"{row.latitude},{row.longitude}"
    else:
        query = " ".join(x for x in [row.title, row.address] if x)
    return "https://www.google.com/maps/search/?" + urlencode({"api":"1","query":query}) if query else None

def card(row):
    # No verified photo/rating/price columns; unknown weekday origin is not guessed.
    return dict(id=str(row.restaurant_id), title=row.title, subtitle=row.category,
                img=None, rating=None, hours=None, price=None, address=row.address,
                mapLink=map_link(row), source="postgresql")

def recommend(session, provider, count, cursor):
    context = RecommendationContext(count=count, after_id=decode_cursor(cursor))
    rows = provider.select(session, context)
    ids = [r.restaurant_id for r in rows]
    if len(rows) > count or len(set(ids)) != len(ids) or any(type(i) is not int or not 1 <= i <= MAX_ID for i in ids):
        raise RuntimeError("Provider returned invalid restaurant identities")
    return dict(items=[card(r) for r in rows], source="postgresql",
                algorithm_version=provider.version,
                next_cursor=encode_cursor(ids[-1]) if ids else None)

