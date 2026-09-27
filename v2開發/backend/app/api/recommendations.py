from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.accounts import connection
from app.core.security import current_user

router = APIRouter(prefix="/api/restaurants")


class RecommendationEvent(BaseModel):
    run_id: int = Field(gt=0, le=9223372036854775807)
    restaurant_id: int = Field(gt=0, le=9223372036854775807)
    event_type: Literal["impression", "open_detail", "open_map", "favorite", "visited", "not_interested"]
    value: float | None = Field(default=None, ge=0, le=1)


@router.post("/recommendation-events", status_code=201)
def recommendation_event(data: RecommendationEvent, request: Request, c=Depends(connection)):
    user = current_user(c, request)
    rank = c.execute(text("""
        SELECT i.rank FROM public.recommendation_runs r
        JOIN public.recommendation_items i USING(recommendation_run_id)
        WHERE r.recommendation_run_id=:run AND r.user_id=:user AND i.restaurant_id=:restaurant
    """), {"run": data.run_id, "user": user["user_id"], "restaurant": data.restaurant_id}).scalar()
    if rank is None:
        raise HTTPException(404, "找不到這位使用者的該次推薦結果")
    recent = c.execute(text("""
        SELECT count(*) FROM public.user_restaurant_events
        WHERE user_id=:u AND created_at>now()-interval '1 minute'
    """), {"u": user["user_id"]}).scalar()
    if recent >= 120:
        raise HTTPException(429, "互動紀錄過於頻繁，請稍後再試")
    event_id = c.execute(text("""
        INSERT INTO public.user_restaurant_events
            (user_id,restaurant_id,recommendation_run_id,event_type,rank_at_time,value)
        VALUES(:u,:restaurant,:run,:event,:rank,:value) RETURNING event_id
    """), {"u": user["user_id"], "restaurant": data.restaurant_id, "run": data.run_id,
          "event": data.event_type, "rank": rank, "value": data.value}).scalar()
    return {"status": "recorded", "event_id": str(event_id)}
