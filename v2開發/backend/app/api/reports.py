from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.accounts import connection
from app.core.security import current_user

router = APIRouter(prefix="/api")


class ReportCreate(BaseModel):
    target_type: Literal["user", "record", "comment"]
    target_id: int = Field(gt=0, le=9223372036854775807)
    reason_code: Literal["spam", "harassment", "inappropriate", "privacy", "other"]
    details: str = Field(default="", max_length=2000)


@router.post("/reports", status_code=201)
def create_report(data: ReportCreate, request: Request, c=Depends(connection)):
    user = current_user(c, request)
    if data.target_type == "user":
        exists = c.execute(text(
            "SELECT 1 FROM public.users WHERE user_id=:id AND email_verified"
        ), {"id": data.target_id}).scalar()
        if not exists:
            raise HTTPException(404, "找不到檢舉對象")
        if data.target_id == user["user_id"]:
            raise HTTPException(422, "不能檢舉自己的帳號")
    elif data.target_type == "record":
        exists = c.execute(text(
            "SELECT 1 FROM public.records WHERE record_id=:id"
        ), {"id": data.target_id}).scalar()
        if not exists:
            raise HTTPException(404, "找不到檢舉貼文")
    else:
        exists = c.execute(text(
            "SELECT 1 FROM public.platform_comments WHERE comment_id=:id"
        ), {"id": data.target_id}).scalar()
        if not exists:
            raise HTTPException(404, "找不到檢舉留言")

    recent_count = c.execute(text(
        "SELECT count(*) FROM public.content_reports "
        "WHERE reporter_id=:u AND created_at > now()-interval '1 hour'"
    ), {"u": user["user_id"]}).scalar()
    if recent_count >= 10:
        raise HTTPException(429, "檢舉次數過多，請稍後再試")

    duplicate = c.execute(text(
        "SELECT 1 FROM public.content_reports WHERE reporter_id=:u AND target_type=:t "
        "AND target_id=:id AND status IN ('pending','reviewing') LIMIT 1"
    ), {"u": user["user_id"], "t": data.target_type, "id": data.target_id}).scalar()
    if duplicate:
        raise HTTPException(409, "你已經檢舉過這個內容，案件仍在處理中")

    report_id = c.execute(text(
        "INSERT INTO public.content_reports(reporter_id,target_type,target_id,reason_code,details) "
        "VALUES(:u,:t,:id,:reason,:details) RETURNING report_id"
    ), {"u": user["user_id"], "t": data.target_type, "id": data.target_id,
        "reason": data.reason_code, "details": data.details.strip()}).scalar()
    return {"status": "submitted", "report_id": str(report_id)}
