import json
import base64
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Depends,HTTPException,Request,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
from sqlalchemy import text
from app.api.accounts import connection
from app.core.security import current_user,check_email,user_payload
from app.core.storage import store_image,file_path,schedule_delete
router=APIRouter(prefix="/api")
TAIPEI=timezone(timedelta(hours=8))
def owned(c,request,id):
    user=current_user(c,request)
    row=c.execute(text("SELECT * FROM public.records WHERE record_id=:id AND user_id=:u FOR UPDATE"),{"id":id,"u":user["user_id"]}).mappings().first()
    if not row:raise HTTPException(404,"找不到紀錄")
    return user,row
def accessible(c,request,id):
    user=current_user(c,request)
    row=c.execute(text("""SELECT r.* FROM public.records r
        WHERE r.record_id=:id AND (r.user_id=:u OR (r.moderation_status='visible' AND EXISTS
          (SELECT 1 FROM public.record_mentions rm WHERE rm.record_id=r.record_id AND rm.user_id=:u)))"""),{"id":id,"u":user["user_id"]}).mappings().first()
    if not row: raise HTTPException(404,"找不到紀錄")
    return user,row
def _cursor_encode(row):
    payload=json.dumps([row["create_time"].isoformat(),str(row["record_id"])],separators=(",",":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")

def _cursor_decode(cursor):
    try:
        payload=base64.urlsafe_b64decode(cursor+"="*((-len(cursor))%4))
        created_text,record_text=json.loads(payload)
        if not isinstance(created_text,str) or not isinstance(record_text,str) or len(record_text)>19:raise ValueError()
        created_at=datetime.fromisoformat(created_text)
        record_id=int(record_text)
        if record_id<=0 or record_id>9223372036854775807:raise ValueError()
        return created_at,record_id
    except (ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError):
        raise HTTPException(422,"分頁游標不正確") from None

def posts(c,rows,viewer_id=None,include_comments=False):
    if not rows:return []
    ids=[int(row["record_id"]) for row in rows]
    authors={int(r["user_id"]):r for r in c.execute(text("""SELECT r.record_id,u.user_id,u.user_name,u.avatar_path
        FROM public.records r JOIN public.users u USING(user_id) WHERE r.record_id=ANY(:ids)"""),{"ids":ids}).mappings()}
    photos={}
    for photo in c.execute(text("SELECT record_id,photo_id FROM public.photos WHERE record_id=ANY(:ids) ORDER BY record_id,sort_order,photo_id"),{"ids":ids}).mappings():
        photos.setdefault(int(photo["record_id"]),[]).append(photo)
    mentions={}
    for mention in c.execute(text("""SELECT m.record_id,u.user_id,u.user_name FROM public.record_mentions m
        JOIN public.users u USING(user_id) WHERE m.record_id=ANY(:ids) ORDER BY m.record_id,u.user_id"""),{"ids":ids}).mappings():
        mentions.setdefault(int(mention["record_id"]),[]).append(mention)
    comment_counts={int(r["record_id"]):int(r["count"]) for r in c.execute(text("""SELECT record_id,count(*) AS count
        FROM public.platform_comments WHERE record_id=ANY(:ids) AND NOT is_deleted AND NOT moderation_hidden
        GROUP BY record_id"""),{"ids":ids}).mappings()}
    like_stats={int(r["record_id"]):r for r in c.execute(text("""SELECT record_id,count(*) AS likes,
        COALESCE(bool_or(user_id=:viewer),false) AS is_liked FROM public.record_likes
        WHERE record_id=ANY(:ids) GROUP BY record_id"""),{"ids":ids,"viewer":viewer_id}).mappings()}
    comments={}
    if include_comments:
        for comment in c.execute(text("""SELECT c.record_id,c.text,c.create_time,u.user_id,u.user_name,u.avatar_path
            FROM public.platform_comments c JOIN public.users u USING(user_id)
            WHERE c.record_id=ANY(:ids) AND NOT c.is_deleted AND NOT c.moderation_hidden
            ORDER BY c.create_time,c.comment_id"""),{"ids":ids}).mappings():
            comments.setdefault(int(comment["record_id"]),[]).append(dict(user=comment["user_name"],text=comment["text"],
                avatar="/api/avatars/"+str(comment["user_id"]) if comment["avatar_path"] else None,
                timestamp=comment["create_time"].isoformat()))
    result=[]
    for row in rows:
        record_id=int(row["record_id"]);author=authors[int(row["user_id"])];record_photos=photos.get(record_id,[])
        record_mentions=mentions.get(record_id,[]);urls=["/api/photos/"+str(photo["photo_id"]) for photo in record_photos]
        viewer_is_tagged=bool(viewer_id and any(int(item["user_id"])==int(viewer_id) for item in record_mentions))
        is_owner=bool(viewer_id and int(row["user_id"])==int(viewer_id));stats=like_stats.get(record_id,{"likes":0,"is_liked":False})
        value=dict(id=str(record_id),imageUrls=urls,urls=urls,url=urls[0] if urls else None,
            timestamp=int(row["create_time"].timestamp()*1000),date=row["create_time"].astimezone(TAIPEI).date().isoformat(),
            caption=row["text"] or "",location=row["location_text"] or "",restaurant_id=str(row["restaurant_id"]) if row["restaurant_id"] else None,
            mentions=[dict(id=str(item["user_id"]),name=item["user_name"]) for item in record_mentions],
            username=author["user_name"],userAvatar="/api/avatars/"+str(row["user_id"]) if author["avatar_path"] else None,
            likes=int(stats["likes"]),isLiked=bool(stats["is_liked"]),commentCount=comment_counts.get(record_id,0),
            isOwner=is_owner,isTagged=viewer_is_tagged,canEdit=is_owner)
        if include_comments:value["comments"]=comments.get(record_id,[])
        result.append(value)
    return result

def post(c,row,viewer_id=None,include_comments=False):
    return posts(c,[row],viewer_id,include_comments)[0]
@router.get("/get_memories")
def memories(request:Request,email:str="",scope:str=Query("own",pattern="^(own|memories|social)$"),
             limit:int|None=Query(None,ge=1,le=50),cursor:str=Query("",max_length=256),c=Depends(connection)):
    user=current_user(c,request);check_email(user,email)
    if cursor and limit is None:raise HTTPException(422,"使用游標時必須指定每頁筆數")
    before=_cursor_decode(cursor) if cursor else None
    cursor_clause=" AND (r.create_time,r.record_id)<(:before_time,:before_id)" if before else ""
    params={"u":user["user_id"]}
    if before:params.update(before_time=before[0],before_id=before[1])
    if limit is not None:params["fetch_limit"]=limit+1
    if scope in {"memories", "social"}:
        query="""SELECT DISTINCT r.*
            FROM public.records r
            LEFT JOIN public.record_mentions rm ON rm.record_id=r.record_id AND rm.user_id=:u
            WHERE (r.user_id=:u OR (r.moderation_status='visible' AND rm.user_id IS NOT NULL))"""+cursor_clause+" ORDER BY r.create_time DESC,r.record_id DESC"
    else:
        query="SELECT r.* FROM public.records r WHERE r.user_id=:u"+cursor_clause+" ORDER BY r.create_time DESC,r.record_id DESC"
    if limit is not None:query+=" LIMIT :fetch_limit"
    rows=c.execute(text(query),params).mappings().all()
    has_more=limit is not None and len(rows)>limit
    if has_more:rows=rows[:limit]
    items=posts(c,rows,user["user_id"])
    if limit is None:return items
    return {"items":items,"next_cursor":_cursor_encode(rows[-1]) if has_more and rows else None,"has_more":has_more}
@router.get("/get_post/{record_id}")
def get_post(record_id:int,request:Request,c=Depends(connection)):
    user,row=accessible(c,request,record_id);return post(c,row,user["user_id"],include_comments=True)
def ids_json(value,limit=10):
    try:
        data=json.loads(value or "[]")
        if not isinstance(data,list) or len(data)>limit or len(set(data))!=len(data):raise ValueError()
        result=[int(x) for x in data]
        if any(x<=0 or x>9223372036854775807 for x in result):raise ValueError()
        return result
    except (ValueError,TypeError):raise HTTPException(422,"選擇資料格式不正確") from None
@router.post("/upload_memory_post")
@router.post("/update_post")
async def save_post(request:Request,c=Depends(connection)):
    user=current_user(c,request)
    form=await request.form(max_files=10,max_fields=24)
    check_email(user,str(form.get("email","")))
    updating=request.url.path.endswith("/update_post")
    row=None
    if updating:
        try:id=int(form.get("post_id",""))
        except ValueError:raise HTTPException(422,"紀錄 ID 不正確") from None
        _,row=owned(c,request,id)
    mentions=ids_json(form.get("mention_ids","[]"))
    initial_comment=str(form.get("initial_comment","")).strip()
    if len(initial_comment)>2000:raise HTTPException(422,"留言需為 2000 字元以內")
    for uid in mentions:
        accepted_friend=c.execute(text("""SELECT 1 FROM public.users target WHERE target.user_id=:other
            AND (target.email_verified OR target.email_auth_exempt) AND target.account_status='active'
            AND EXISTS (SELECT 1 FROM public.friend_requests fr WHERE fr.status='accepted'
              AND ((fr.requester_id=:me AND fr.addressee_id=:other) OR (fr.requester_id=:other AND fr.addressee_id=:me)))"""),
            {"me":user["user_id"],"other":uid}).scalar()
        if uid==user["user_id"] or not accepted_friend:
            raise HTTPException(422,"只能標註已接受的有效好友")
    location=None;restaurant_id=None
    photo_location_text=str(form.get("photo_location_text","")).strip()
    if len(photo_location_text)>200:raise HTTPException(422,"照片位置資訊過長")
    if form.get("restaurant_id"):
        try:restaurant_id=int(form["restaurant_id"])
        except ValueError:raise HTTPException(422,"地點格式不正確") from None
        location=c.execute(text("SELECT title FROM public.restaurant_rows WHERE restaurant_id=:r"),{"r":restaurant_id}).scalar()
        if location is None:raise HTTPException(422,"找不到選取的地點")
    elif photo_location_text:
        location=photo_location_text
    old=c.execute(text("SELECT photo_id,storage_path FROM public.photos WHERE record_id=:r ORDER BY sort_order,photo_id"),{"r":row["record_id"]}).mappings().all() if row else []
    old_urls={"/api/photos/"+str(p["photo_id"]):p for p in old}
    files=form.getlist("files")
    if any(not hasattr(f,"file") for f in files):raise HTTPException(422,"照片格式不正確")
    try:
        order=json.loads(form.get("photo_order","null"))
        if order is None:order=[{"new":i} for i in range(len(files))]
        if not isinstance(order,list) or not 1<=len(order)<=10:raise ValueError()
        old_used=set();new_used=set()
        for entry in order:
            if not isinstance(entry,dict) or len(entry)!=1:raise ValueError()
            if "existing" in entry:
                url=entry["existing"]
                if url not in old_urls or url in old_used:raise ValueError()
                old_used.add(url)
            elif "new" in entry:
                idx=entry["new"]
                if type(idx) is not int or not 0<=idx<len(files) or idx in new_used:raise ValueError()
                new_used.add(idx)
            else:raise ValueError()
        if new_used!=set(range(len(files))):raise ValueError()
    except (ValueError,TypeError):raise HTTPException(422,"照片順序或保留照片不正確") from None
    # Validate selection/ownership before writing any file.
    new_keys=[store_image(request,f) for f in files]
    values={"u":user["user_id"],"r":restaurant_id,"l":location}
    if row:
        record_id=row["record_id"]
        c.execute(text("UPDATE public.records SET restaurant_id=:r,location_text=:l WHERE record_id=:id"),dict(values,id=record_id))
    else:
        record_id=c.execute(text("INSERT INTO public.records(user_id,restaurant_id,location_text,is_public,text) VALUES(:u,:r,:l,false,'') RETURNING record_id"),values).scalar()
    for url,p in old_urls.items():
        if url not in old_used:
            c.execute(text("DELETE FROM public.photos WHERE photo_id=:p"),{"p":p["photo_id"]});schedule_delete(c,p["storage_path"])
    for position,entry in enumerate(order):
        if "existing" in entry:
            c.execute(text("UPDATE public.photos SET sort_order=:s WHERE photo_id=:p"),{"s":position,"p":old_urls[entry["existing"]]["photo_id"]})
        else:
            c.execute(text("INSERT INTO public.photos(record_id,storage_path,sort_order) VALUES(:r,:p,:s)"),{"r":record_id,"p":new_keys[entry["new"]],"s":position})
    c.execute(text("DELETE FROM public.record_mentions WHERE record_id=:r"),{"r":record_id})
    for uid in mentions:c.execute(text("INSERT INTO public.record_mentions(record_id,user_id) VALUES(:r,:u)"),{"r":record_id,"u":uid})
    if initial_comment:
        c.execute(text("INSERT INTO public.platform_comments(record_id,user_id,text) VALUES(:r,:u,:t)"),{"r":record_id,"u":user["user_id"],"t":initial_comment})
    return {"status":"success","id":str(record_id)}

@router.post("/posts/{record_id}/like")
def like_record(record_id:int,request:Request,c=Depends(connection)):
    user,_=accessible(c,request,record_id)
    c.execute(text("INSERT INTO public.record_likes(record_id,user_id) VALUES(:r,:u) ON CONFLICT (record_id,user_id) DO NOTHING"),{"r":record_id,"u":user["user_id"]})
    return {"status":"success","liked":True}

@router.delete("/posts/{record_id}/like")
def unlike_record(record_id:int,request:Request,c=Depends(connection)):
    user,_=accessible(c,request,record_id)
    c.execute(text("DELETE FROM public.record_likes WHERE record_id=:r AND user_id=:u"),{"r":record_id,"u":user["user_id"]})
    return {"status":"success","liked":False}

@router.delete("/posts/{record_id}/mention")
def remove_mention(record_id:int,request:Request,c=Depends(connection)):
    """Allow a mentioned member to remove only their own tag from a post."""
    user=current_user(c,request)
    record=c.execute(text("SELECT user_id FROM public.records WHERE record_id=:r"),{"r":record_id}).mappings().first()
    if not record: raise HTTPException(404,"找不到紀錄")
    if int(record["user_id"]) == int(user["user_id"]):
        raise HTTPException(422,"貼文作者不能用取消標記取代編輯")
    deleted=c.execute(text("DELETE FROM public.record_mentions WHERE record_id=:r AND user_id=:u RETURNING record_id"),{"r":record_id,"u":user["user_id"]}).scalar()
    if deleted is None: raise HTTPException(404,"你目前沒有被標記在這則貼文")
    return {"status":"success","record_id":str(record_id),"untagged":True}

@router.delete("/delete_single_photo")
def delete_photo(post_id:int,photo_url:str,request:Request,email:str="",c=Depends(connection)):
    user,_=owned(c,request,post_id);check_email(user,email)
    photo=c.execute(text("SELECT photo_id,storage_path FROM public.photos WHERE record_id=:r AND '/api/photos/'||photo_id::text=:url"),{"r":post_id,"url":photo_url}).mappings().first()
    if not photo:raise HTTPException(404,"找不到照片")
    c.execute(text("DELETE FROM public.photos WHERE photo_id=:p"),{"p":photo["photo_id"]});schedule_delete(c,photo["storage_path"])
    if not c.execute(text("SELECT 1 FROM public.photos WHERE record_id=:r LIMIT 1"),{"r":post_id}).scalar():
        c.execute(text("DELETE FROM public.records WHERE record_id=:r"),{"r":post_id})
    return {"status":"success"}
@router.delete("/posts/{record_id}")
def delete_record(record_id:int,request:Request,c=Depends(connection)):
    owned(c,request,record_id)
    for key in c.execute(text("SELECT storage_path FROM public.photos WHERE record_id=:r"),{"r":record_id}).scalars():schedule_delete(c,key)
    c.execute(text("DELETE FROM public.records WHERE record_id=:r"),{"r":record_id})
    return {"status":"success"}
@router.get("/photos/{photo_id}")
def photo_file(photo_id:int,request:Request,c=Depends(connection)):
    user=current_user(c,request)
    key=c.execute(text("""SELECT p.storage_path
        FROM public.photos p JOIN public.records r USING(record_id)
        WHERE p.photo_id=:p AND (r.user_id=:u OR (r.moderation_status='visible' AND EXISTS
          (SELECT 1 FROM public.record_mentions rm WHERE rm.record_id=r.record_id AND rm.user_id=:u)))"""),{"p":photo_id,"u":user["user_id"]}).scalar()
    if not key:raise HTTPException(404,"找不到照片")
    path=file_path(request.app.state.storage_root,key)
    if not path.is_file():raise HTTPException(404,"找不到照片")
    return FileResponse(path,media_type="image/jpeg")
@router.get("/locations")
def locations(request:Request,q:str=Query("",max_length=100),c=Depends(connection)):
    current_user(c,request)
    query=q.strip().replace("/","//").replace("%","/%").replace("_","/_")
    rows=c.execute(text('SELECT restaurant_id,title,address FROM public.restaurant_rows WHERE title ILIKE :q ESCAPE \'/\' OR address ILIKE :q ESCAPE \'/\' ORDER BY title,restaurant_id LIMIT 30'),{"q":"%"+query+"%"}).mappings()
    return {"items":[dict(id=str(r["restaurant_id"]),name=r["title"],address=r["address"]) for r in rows]}
@router.get("/members")
def members(request:Request,q:str=Query("",max_length=80),c=Depends(connection)):
    user=current_user(c,request)
    query=q.strip().replace("/","//").replace("%","/%").replace("_","/_")
    rows=c.execute(text("""SELECT DISTINCT u.user_id,u.user_name,u.username
        FROM public.friend_requests fr
        JOIN public.users u ON u.user_id=CASE WHEN fr.requester_id=:u THEN fr.addressee_id ELSE fr.requester_id END
        WHERE fr.status='accepted' AND (fr.requester_id=:u OR fr.addressee_id=:u)
          AND (u.email_verified OR u.email_auth_exempt) AND u.account_status='active'
          AND (:q='' OR u.username ILIKE :q ESCAPE '/' OR u.user_name ILIKE :q ESCAPE '/')
        ORDER BY u.user_name,u.user_id LIMIT 30"""),{"u":user["user_id"],"q":"%"+query+"%" if query else ""}).mappings()
    return {"items":[dict(id=str(r["user_id"]),name=r["user_name"],username=r["username"]) for r in rows]}
class Comment(BaseModel):
    photo_id:str
    user_email:str=""
    user_name:str=""
    text:str=Field(min_length=1,max_length=2000)
@router.post("/add_comment")
def comment(data:Comment,request:Request,c=Depends(connection)):
    try:id=int(data.photo_id)
    except ValueError:raise HTTPException(422,"紀錄 ID 不正確") from None
    user,_=accessible(c,request,id);check_email(user,data.user_email)
    if not data.text.strip():raise HTTPException(422,"留言不能空白")
    c.execute(text("INSERT INTO public.platform_comments(record_id,user_id,text) VALUES(:r,:u,:t)"),{"r":id,"u":user["user_id"],"t":data.text.strip()})
    return {"status":"success"}
@router.post("/update_profile_name")
async def update_name(request:Request,c=Depends(connection)):
    user=current_user(c,request);form=await request.form();check_email(user,str(form.get("email","")))
    name=str(form.get("name","")).strip()
    if not 1<=len(name)<=80:raise HTTPException(422,"名稱需為 1 至 80 字元")
    c.execute(text("UPDATE public.users SET user_name=:n WHERE user_id=:u"),{"n":name,"u":user["user_id"]})
    return {"status":"success","name":name}
@router.post("/upload_avatar")
async def avatar(request:Request,c=Depends(connection)):
    user=current_user(c,request,True);form=await request.form(max_files=1,max_fields=3);check_email(user,str(form.get("email","")))
    file=form.get("file")
    if not hasattr(file,"file"):raise HTTPException(422,"請選擇照片")
    key=store_image(request,file)
    c.execute(text("UPDATE public.users SET avatar_path=:p WHERE user_id=:u"),{"p":key,"u":user["user_id"]})
    schedule_delete(c,user["avatar_path"])
    return {"status":"success","avatar_url":"/api/avatars/"+str(user["user_id"])}
@router.get("/avatars/{user_id}")
def avatar_file(user_id:int,request:Request,c=Depends(connection)):
    current_user(c,request)
    key=c.execute(text("SELECT avatar_path FROM public.users WHERE user_id=:u AND email_verified"),{"u":user_id}).scalar()
    if not key:raise HTTPException(404,"找不到頭像")
    path=file_path(request.app.state.storage_root,key)
    if not path.is_file():raise HTTPException(404,"找不到頭像")
    return FileResponse(path,media_type="image/jpeg")
@router.get("/check_vip/{email}")
def vip(email:str,request:Request,c=Depends(connection)):
    user=current_user(c,request);check_email(user,email)
    return {"is_vip":user_payload(c,user)["is_premium"]}
@router.post("/upgrade_premium")
def upgrade(request:Request,email:str="",c=Depends(connection)):
    user=current_user(c,request,True);check_email(user,email)
    # Demo entitlement has no billing period and no real charge.
    if not user_payload(c,user)["is_premium"]:
        trade="demo-"+str(user["user_id"])
        membership=c.execute(text("INSERT INTO public.memberships(user_id,trade_no,price,payment_provider,end_date) VALUES(:u,:t,0,'demo',NULL) RETURNING membership_id"),{"u":user["user_id"],"t":trade}).scalar()
        c.execute(text("INSERT INTO public.payment_transactions(user_id,membership_id,provider,provider_transaction_id,amount,status,paid_at,raw_payload) VALUES(:u,:m,'demo',:t,0,'paid',now(),CAST(:payload AS jsonb))"),{"u":user["user_id"],"m":membership,"t":trade,"payload":json.dumps({"simulated":True})})
    return {"status":"success","is_vip":True,"simulated":True}
