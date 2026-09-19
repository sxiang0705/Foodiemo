"""Private chat between users who have accepted a friend relationship."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text

from app.api.accounts import connection
from app.core.security import current_user

router = APIRouter(prefix="/api")


def _person(row):
    return {
        "id": str(row["user_id"]),
        "name": row["user_name"] or "",
        "email": row["email"],
        "avatar_url": "/api/avatars/" + str(row["user_id"]) if row["avatar_path"] else None,
    }


def _friend(c, me: int, other: int):
    row = c.execute(
        text(
            """SELECT u.user_id,u.user_name,u.email,u.avatar_path
               FROM public.users u
               WHERE u.user_id=:other AND u.email_verified
                 AND EXISTS (
                   SELECT 1 FROM public.friend_requests fr
                   WHERE fr.status='accepted'
                     AND LEAST(fr.requester_id,fr.addressee_id)=LEAST(:me,:other)
                     AND GREATEST(fr.requester_id,fr.addressee_id)=GREATEST(:me,:other)
                 )"""
        ),
        {"me": me, "other": other},
    ).mappings().first()
    return row


def _require_friend(c, me: int, other: int):
    if me == other:
        raise HTTPException(422, "不能與自己聊天")
    row = _friend(c, me, other)
    if not row:
        raise HTTPException(403, "只有已接受好友可以聊天")
    return row


def _message(row):
    return {
        "id": str(row["message_id"]),
        "sender_id": str(row["sender_id"]),
        "recipient_id": str(row["recipient_id"]),
        "text": row["body"],
        "created_at": row["created_at"].isoformat() if isinstance(row["created_at"], datetime) else row["created_at"],
    }


@router.get("/chats/{friend_id}/messages")
def list_messages(
    request: Request,
    friend_id: int = Path(gt=0),
    after_id: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    c=Depends(connection),
):
    user = current_user(c, request)
    friend = _require_friend(c, user["user_id"], friend_id)
    rows = c.execute(
        text(
            """SELECT message_id,sender_id,recipient_id,body,created_at
               FROM public.chat_messages
               WHERE ((sender_id=:me AND recipient_id=:other)
                   OR (sender_id=:other AND recipient_id=:me))
                 AND message_id>:after
               ORDER BY message_id ASC LIMIT :limit"""
        ),
        {"me": user["user_id"], "other": friend_id, "after": after_id, "limit": limit},
    ).mappings().all()
    return {"friend": _person(friend), "messages": [_message(row) for row in rows]}


class ChatMessage(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("留言不可為空白")
        return value


@router.post("/chats/{friend_id}/messages")
def send_message(
    request: Request,
    data: ChatMessage,
    friend_id: int = Path(gt=0),
    c=Depends(connection),
):
    user = current_user(c, request)
    _require_friend(c, user["user_id"], friend_id)
    row = c.execute(
        text(
            """INSERT INTO public.chat_messages(sender_id,recipient_id,body)
               VALUES(:sender,:recipient,:body)
               RETURNING message_id,sender_id,recipient_id,body,created_at"""
        ),
        {"sender": user["user_id"], "recipient": friend_id, "body": data.text},
    ).mappings().one()
    return {"message": _message(row)}



