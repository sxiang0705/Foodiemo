"""Friend search, requests and accepted relationships."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from app.api.accounts import connection
from app.core.security import current_user

router=APIRouter(prefix="/api")

def _avatar(user_id, avatar_path):
    return "/api/avatars/"+str(user_id) if avatar_path else None

def _person(row):
    return {"id":str(row["user_id"]),"name":row["user_name"] or "","email":row["email"],"avatar_url":_avatar(row["user_id"],row["avatar_path"])}

def _relationship(c,me,other):
    if c.execute(text("""SELECT 1 FROM public.friend_requests
        WHERE status='accepted' AND LEAST(requester_id,addressee_id)=LEAST(:me,:other)
          AND GREATEST(requester_id,addressee_id)=GREATEST(:me,:other)"""),{"me":me,"other":other}).scalar():
        return "accepted"
    row=c.execute(text("""SELECT requester_id FROM public.friend_requests
        WHERE status='pending' AND ((requester_id=:me AND addressee_id=:other)
          OR (requester_id=:other AND addressee_id=:me))
        ORDER BY created_at DESC LIMIT 1"""),{"me":me,"other":other}).mappings().first()
    if not row:return "none"
    return "pending_outgoing" if row["requester_id"]==me else "pending_incoming"

@router.get("/friends")
def friends(request:Request,c=Depends(connection)):
    user=current_user(c,request);me=user["user_id"]
    accepted=c.execute(text("""SELECT u.user_id,u.user_name,u.email,u.avatar_path,fr.responded_at
        FROM public.friend_requests fr
        JOIN public.users u ON u.user_id=CASE WHEN fr.requester_id=:me THEN fr.addressee_id ELSE fr.requester_id END
        WHERE fr.status='accepted' AND (fr.requester_id=:me OR fr.addressee_id=:me)
        ORDER BY u.user_name,u.user_id"""),{"me":me}).mappings().all()
    incoming=c.execute(text("""SELECT fr.request_id,fr.created_at,u.user_id,u.user_name,u.email,u.avatar_path
        FROM public.friend_requests fr JOIN public.users u ON u.user_id=fr.requester_id
        WHERE fr.addressee_id=:me AND fr.status='pending'
        ORDER BY fr.created_at DESC,fr.request_id DESC"""),{"me":me}).mappings().all()
    outgoing=c.execute(text("""SELECT fr.request_id,fr.created_at,u.user_id,u.user_name,u.email,u.avatar_path
        FROM public.friend_requests fr JOIN public.users u ON u.user_id=fr.addressee_id
        WHERE fr.requester_id=:me AND fr.status='pending'
        ORDER BY fr.created_at DESC,fr.request_id DESC"""),{"me":me}).mappings().all()
    def request_item(row,kind):
        item=_person(row);item.update({"request_id":str(row["request_id"]),"created_at":row["created_at"].isoformat(),"direction":kind});return item
    return {"friends":[dict(_person(row),friend_since=row["responded_at"].isoformat() if row["responded_at"] else None) for row in accepted],
            "incoming":[request_item(row,"incoming") for row in incoming],
            "outgoing":[request_item(row,"outgoing") for row in outgoing]}

@router.get("/friends/search")
def search_friends(request:Request,q:str=Query("",min_length=2,max_length=80),c=Depends(connection)):
    user=current_user(c,request);query=q.strip().replace("/","//").replace("%","/%").replace("_","/_")
    rows=c.execute(text("""SELECT user_id,user_name,email,avatar_path FROM public.users
        WHERE email_verified AND user_id<>:me
          AND (user_name ILIKE :q ESCAPE '/' OR email ILIKE :q ESCAPE '/')
        ORDER BY user_name,user_id LIMIT 20"""),{"me":user["user_id"],"q":"%"+query+"%"}).mappings().all()
    return {"items":[dict(_person(row),relationship=_relationship(c,user["user_id"],row["user_id"])) for row in rows]}

class FriendRequest(BaseModel):
    user_id:int=Field(gt=0)

@router.post("/friends/requests")
def create_request(data:FriendRequest,request:Request,c=Depends(connection)):
    user=current_user(c,request);me=user["user_id"];other=data.user_id
    if me==other:raise HTTPException(422,"不能對自己提出好友請求")
    target=c.execute(text("SELECT user_id FROM public.users WHERE user_id=:u AND email_verified"),{"u":other}).scalar()
    if not target:raise HTTPException(404,"找不到可加入的帳號")
    low,high=sorted((me,other));pair=f"{low}:{high}"
    c.execute(text("SELECT pg_advisory_xact_lock(hashtext(:pair))"),{"pair":pair})
    status=c.execute(text("""SELECT status,request_id,requester_id FROM public.friend_requests
        WHERE LEAST(requester_id,addressee_id)=:low AND GREATEST(requester_id,addressee_id)=:high
          AND status IN ('pending','accepted') ORDER BY CASE WHEN status='accepted' THEN 0 ELSE 1 END,created_at DESC LIMIT 1"""),{"low":low,"high":high}).mappings().first()
    if status and status["status"]=='accepted':raise HTTPException(409,"你們已經是好友")
    if status and status["requester_id"]==me:return {"status":"success","request_id":str(status["request_id"]),"state":"pending"}
    if status:raise HTTPException(409,"對方已向你提出好友請求，請到最新消息批准")
    rid=c.execute(text("INSERT INTO public.friend_requests(requester_id,addressee_id,status) VALUES(:me,:other,'pending') RETURNING request_id"),{"me":me,"other":other}).scalar()
    return {"status":"success","request_id":str(rid),"state":"pending"}

@router.post("/friends/requests/{request_id}/approve")
def approve_request(request_id:int,request:Request,c=Depends(connection)):
    user=current_user(c,request)
    row=c.execute(text("""SELECT request_id,requester_id,addressee_id FROM public.friend_requests
        WHERE request_id=:r AND addressee_id=:me AND status='pending' FOR UPDATE"""),{"r":request_id,"me":user["user_id"]}).mappings().first()
    if not row:raise HTTPException(404,"找不到待批准的好友請求")
    c.execute(text("UPDATE public.friend_requests SET status='accepted',responded_at=now() WHERE request_id=:r"),{"r":request_id})
    return {"status":"success","state":"accepted","friend_id":str(row["requester_id"])}

@router.post("/friends/requests/{request_id}/reject")
def reject_request(request_id:int,request:Request,c=Depends(connection)):
    user=current_user(c,request)
    changed=c.execute(text("""UPDATE public.friend_requests SET status='rejected',responded_at=now()
        WHERE request_id=:r AND addressee_id=:me AND status='pending'"""),{"r":request_id,"me":user["user_id"]}).rowcount
    if not changed:raise HTTPException(404,"找不到待處理的好友請求")
    return {"status":"success","state":"rejected"}
