from datetime import time
from pydantic import BaseModel


class RestaurantSummary(BaseModel):
    # String IDs preserve PostgreSQL bigint precision in browser JavaScript.
    id: str
    name: str
    address: str | None
    category: str | None
    review_count: int
    photo_url: None = None
    rating: None = None
    price: None = None


class RestaurantPage(BaseModel):
    items: list[RestaurantSummary]
    total: int
    page: int
    page_size: int


class BusinessHourOut(BaseModel):
    weekday: int | None
    open_time: time | None
    close_time: time | None
    is_closed: bool | None


class RestaurantDetail(RestaurantSummary):
    phone: str | None
    website: str | None
    latitude: float | None
    longitude: float | None
    business_hours: list[BusinessHourOut]


class ReviewOut(BaseModel):
    id: str
    text: str
    published_at: None = None
    rating: None = None


class ReviewPage(BaseModel):
    items: list[ReviewOut]
    total: int
    page: int
    page_size: int
