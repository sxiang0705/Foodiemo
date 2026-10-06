"""Stage-1 mappings from the inventory. No startup create_all or schema changes."""
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, PrimaryKeyConstraint, SmallInteger, Text, Time, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Restaurant(Base):
    __tablename__ = "restaurant_rows"
    __table_args__ = {"schema": "public"}
    restaurant_id = Column(BigInteger, primary_key=True)
    google_maps_id = Column("googleMaps_id", Text, nullable=False)
    title = Column(Text, nullable=False)
    longitude = Column("lng", Float)
    latitude = Column("lat", Float)
    review_count = Column("reviewsCount", Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    address = Column(Text)
    website = Column(Text)
    category = Column("categoryName", Text)
    phone = Column(Text)
    topic_avg = Column(Text)
    price_range = Column(Text)
    restaurant_image_url = Column(Text)
    food_image_url = Column(Text)


class BusinessHour(Base):
    __tablename__ = "business_hours"
    __table_args__ = {"schema": "public"}
    business_hour_id = Column(BigInteger, primary_key=True)
    restaurant_id = Column(BigInteger, ForeignKey("public.restaurant_rows.restaurant_id"), nullable=False)
    weekday = Column(SmallInteger, nullable=False)
    open_time = Column(Time)
    close_time = Column(Time)
    is_closed = Column(Boolean, nullable=False)
    source = Column(Text)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class Review(Base):
    __tablename__ = "reviews_rows"
    __table_args__ = {"schema": "public"}
    reviews_id = Column(BigInteger, primary_key=True)
    restaurant_id = Column(BigInteger, ForeignKey("public.restaurant_rows.restaurant_id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    raw_text = Column(Text, nullable=False)
    cleaned_features = Column(Text)


class Tag(Base):
    __tablename__ = "tags_rows"
    __table_args__ = (
        CheckConstraint("tag_id > 0", name="tags_rows_tag_id_check"),
        CheckConstraint("btrim(tag_name) <> ''", name="tags_rows_tag_name_check"),
        CheckConstraint(
            "category IN ('cuisine', 'food_type', 'amenity', 'feature', 'occasion', 'time_period')",
            name="tags_rows_category_check",
        ),
        UniqueConstraint("category", "tag_name", name="tags_rows_category_tag_name_key"),
        {"schema": "public"},
    )
    tag_id = Column(Integer, primary_key=True)
    tag_name = Column(Text, nullable=False)
    category = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class RestaurantTag(Base):
    __tablename__ = "restaurant_tags_rows"
    __table_args__ = (
        PrimaryKeyConstraint("restaurant_id", "tag_id", name="restaurant_tags_rows_pkey"),
        Index("ix_restaurant_tags_rows_tag_restaurant", "tag_id", "restaurant_id"),
        {"schema": "public"},
    )
    restaurant_id = Column(
        BigInteger,
        ForeignKey("public.restaurant_rows.restaurant_id", ondelete="CASCADE", name="restaurant_tags_rows_restaurant_id_fkey"),
        nullable=False,
    )
    tag_id = Column(
        Integer,
        ForeignKey("public.tags_rows.tag_id", ondelete="CASCADE", name="restaurant_tags_rows_tag_id_fkey"),
        nullable=False,
    )
