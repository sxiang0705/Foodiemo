from sqlalchemy import func, or_, select
from app.models.restaurants import BusinessHour, Restaurant, Review


def summary(row):
    return dict(id=str(row.restaurant_id), name=row.title, address=row.address,
                category=row.category, review_count=row.review_count)


class RestaurantRepository:
    def __init__(self, session):
        self.session = session

    def list(self, page, page_size, q, category):
        filters = []
        if q:
            # Treat %, _ and / as literal user input, not wildcard syntax.
            filters.append(or_(Restaurant.title.icontains(q, autoescape=True),
                               Restaurant.address.icontains(q, autoescape=True)))
        if category:
            filters.append(Restaurant.category == category)
        total = self.session.scalar(select(func.count()).select_from(Restaurant).where(*filters))
        rows = self.session.scalars(select(Restaurant).where(*filters)
            .order_by(Restaurant.restaurant_id).offset((page - 1) * page_size).limit(page_size))
        return dict(items=[summary(row) for row in rows], total=total, page=page, page_size=page_size)

    def detail(self, restaurant_id):
        row = self.session.get(Restaurant, restaurant_id)
        if row is None:
            return None
        hours = self.session.scalars(select(BusinessHour)
            .where(BusinessHour.restaurant_id == restaurant_id)
            .order_by(BusinessHour.weekday, BusinessHour.open_time, BusinessHour.business_hour_id))
        return dict(**summary(row), phone=row.phone, website=row.website,
                    latitude=row.latitude, longitude=row.longitude,
                    business_hours=[dict(weekday=h.weekday, open_time=h.open_time,
                        close_time=h.close_time, is_closed=h.is_closed) for h in hours])

    def reviews(self, restaurant_id, page, page_size):
        if self.session.get(Restaurant, restaurant_id) is None:
            return None
        condition = Review.restaurant_id == restaurant_id
        total = self.session.scalar(select(func.count()).select_from(Review).where(condition))
        rows = self.session.scalars(select(Review).where(condition).order_by(Review.reviews_id)
            .offset((page - 1) * page_size).limit(page_size))
        return dict(items=[dict(id=str(r.reviews_id), text=r.raw_text) for r in rows],
                    total=total, page=page, page_size=page_size)
