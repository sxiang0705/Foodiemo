"""Stage-1 mappings from the inventory. No startup create_all or schema changes."""
from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, SmallInteger, Text, Time
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
