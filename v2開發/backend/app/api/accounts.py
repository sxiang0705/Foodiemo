"""Original account endpoints backed by PostgreSQL; all identities come from cookies."""
import hmac,json,re,secrets
from datetime import date
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,field_validator
from sqlalchemy import text
from app.core.security import (COOKIE,digest,password_hash,password_valid,code_hash,
    make_token,current_user,check_email,user_payload,set_session)
router=APIRouter(prefix="/api")

def connection(request:Request):
    request.state.created_files=[]
    engine=(request.app.state.read_engine if request.method in ("GET","HEAD","OPTIONS")
            else request.app.state.write_engine)
    try:
        with engine.begin() as c:yield c
    except BaseException:
        for path in request.state.created_files:
            try:path.unlink(missing_ok=True)
            except OSError:pass
        raise
    else:
        from app.core.storage import collect_files
        try:
            if request.method not in ("GET","HEAD","OPTIONS"):collect_files(request.app)
        except Exception:pass  # Committed references are safe; retry garbage collection on the next request.
def require_secret(request):
    secret=request.app.state.settings.app_secret
    if len(secret)<32:raise HTTPException(503,"帳號服務尚未完成安全設定")
    return secret
def failed(status,message):return JSONResponse({"detail":message},status_code=status)
class EmailInput(BaseModel):
    email:str=Field(min_length=3,max_length=254)
    @field_validator("email")
    @classmethod
    def valid_email(cls,v):
        v=v.strip().lower()
        if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}",v):raise ValueError("Email 格式不正確")
        return v
class Register(EmailInput):
    name:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=8,max_length=128)
    phone:str=Field(default="",max_length=30)
    dob:date|None=None
class Login(EmailInput):
    password:str=Field(min_length=1,max_length=128)
class SendCode(EmailInput):
    purpose:Literal["signup","reset_password"]
class Verify(SendCode):
    code:str=Field(pattern=r"^\d{4}$")
class Reset(BaseModel):
    new_password:str=Field(min_length=8,max_length=128)
    reset_token:str=Field(min_length=32,max_length=128)
    email:str|None=None

def user_by_email(c,email,lock=False):
    return c.execute(text("SELECT * FROM public.users WHERE lower(email)=:e"+(" FOR UPDATE" if lock else "")),{"e":email}).mappings().first()
def send_challenge(c,request,user,purpose):
    secret=require_secret(request)
    existing=c.execute(text("SELECT *,sent_at>now()-interval '60 seconds' AS too_soon, "
        "window_start>now()-interval '1 hour' AS in_window FROM public.email_challenges "
        "WHERE user_id=:u AND purpose=:p FOR UPDATE"),{"u":user["user_id"],"p":purpose}).mappings().first()
    if existing and (existing["too_soon"] or (existing["in_window"] and existing["send_count"]>=6)):
        raise HTTPException(429,"驗證信請稍後再試")
    code=f"{secrets.randbelow(10000):04d}"
    values={"u":user["user_id"],"p":purpose,"h":code_hash(secret,user["email"].lower(),purpose,code)}
    if existing:
        c.execute(text("UPDATE public.email_challenges SET code_hash=:h,expires_at=now()+interval '10 minutes',attempts=0,"
          "send_count=CASE WHEN window_start>now()-interval '1 hour' THEN send_count+1 ELSE 1 END,"
          "window_start=CASE WHEN window_start>now()-interval '1 hour' THEN window_start ELSE now() END,sent_at=now() "
          "WHERE user_id=:u AND purpose=:p"),values)
    else:
        c.execute(text("INSERT INTO public.email_challenges(user_id,purpose,code_hash,expires_at) VALUES(:u,:p,:h,now()+interval '10 minutes')"),values)
    try:request.app.state.mailer.send(user["email"],code,purpose)
    except Exception:raise HTTPException(503,"驗證信尚未寄出，請確認寄信設定或稍後重試") from None

@router.post("/register")
def register(data:Register,request:Request,c=Depends(connection)):
    require_secret(request)
    if not data.name.strip():raise HTTPException(422,"請填寫名稱")
    if data.dob and data.dob>date.today():raise HTTPException(422,"生日不能晚於今天")
    c.execute(text("SELECT pg_advisory_xact_lock(hashtext(:e))"),{"e":data.email})
    if user_by_email(c,data.email):raise HTTPException(409,"此 Email 已註冊，請登入或重設密碼")
    user=c.execute(text("INSERT INTO public.users(user_name,email,password_hash,phone,birthday) VALUES(:n,:e,:p,:ph,:d) RETURNING *"),
      {"n":data.name.strip(),"e":data.email,"p":password_hash(data.password),"ph":data.phone,"d":data.dob}).mappings().one()
    send_challenge(c,request,user,"signup")
    return {"email":user["email"],"name":user["user_name"],"status":"verification_required"}

@router.post("/send_email_code")
def send_code(data:SendCode,request:Request,c=Depends(connection)):
    require_secret(request)
    user=user_by_email(c,data.email,True)
    if user and ((data.purpose=="signup" and not user["email_verified"]) or
                 (data.purpose=="reset_password" and user["email_verified"])):
        send_challenge(c,request,user,data.purpose)
    return {"status":"ok","message":"若帳號符合條件，驗證信已寄出"}

@router.post("/verify_email_code")
def verify(data:Verify,request:Request,c=Depends(connection)):
    secret=require_secret(request)
    user=user_by_email(c,data.email,True)
    if not user:return failed(400,"驗證碼不正確或已失效")
    challenge=c.execute(text("SELECT *,expires_at>now() AS valid FROM public.email_challenges WHERE user_id=:u AND purpose=:p FOR UPDATE"),
        {"u":user["user_id"],"p":data.purpose}).mappings().first()
    if not challenge or not challenge["valid"] or challenge["attempts"]>=5:return failed(400,"驗證碼不正確或已失效")
    if not hmac.compare_digest(challenge["code_hash"],code_hash(secret,data.email,data.purpose,data.code)):
        c.execute(text("UPDATE public.email_challenges SET attempts=attempts+1 WHERE user_id=:u AND purpose=:p"),
            {"u":user["user_id"],"p":data.purpose})
        return failed(400,"驗證碼不正確或已失效")
    c.execute(text("DELETE FROM public.email_challenges WHERE user_id=:u AND purpose=:p"),{"u":user["user_id"],"p":data.purpose})
    if data.purpose=="reset_password":
        return {"reset_token":make_token(c,user["user_id"],"reset")}
    c.execute(text("UPDATE public.users SET email_verified=true WHERE user_id=:u"),{"u":user["user_id"]})
    response=JSONResponse(user_payload(c,user))
    set_session(response,make_token(c,user["user_id"],"session"),request.app.state.settings.environment=="production")
    return response

@router.post("/login")
def login(data:Login,request:Request,c=Depends(connection)):
    require_secret(request)
    key=digest(data.email)
    c.execute(text("INSERT INTO public.login_limits(key_hash) VALUES(:k) ON CONFLICT DO NOTHING"),{"k":key})
    limit=c.execute(text("SELECT *,window_start>now()-interval '15 minutes' AS active FROM public.login_limits WHERE key_hash=:k FOR UPDATE"),{"k":key}).mappings().one()
    if limit["active"] and limit["attempts"]>=10:return failed(429,"嘗試次數過多，請稍後登入")
    c.execute(text("UPDATE public.login_limits SET attempts=CASE WHEN window_start>now()-interval '15 minutes' THEN attempts+1 ELSE 1 END,"
        "window_start=CASE WHEN window_start>now()-interval '15 minutes' THEN window_start ELSE now() END WHERE key_hash=:k"),{"k":key})
    user=user_by_email(c,data.email)
    if not user or not password_valid(data.password,user["password_hash"]):return failed(401,"Email 或密碼不正確")
    if not user["email_verified"]:return failed(403,"請先完成 Email 驗證")
    c.execute(text("DELETE FROM public.login_limits WHERE key_hash=:k"),{"k":key})
    c.execute(text("UPDATE public.users SET last_login_at=now() WHERE user_id=:u"),{"u":user["user_id"]})
    response=JSONResponse(user_payload(c,user))
    set_session(response,make_token(c,user["user_id"],"session"),request.app.state.settings.environment=="production")
    return response

@router.post("/reset_password")
def reset(data:Reset,c=Depends(connection)):
    token=c.execute(text("SELECT * FROM public.auth_tokens WHERE token_hash=:t AND purpose='reset' AND expires_at>now() FOR UPDATE"),
        {"t":digest(data.reset_token)}).mappings().first()
    if not token:raise HTTPException(400,"重設連結已失效，請重新申請")
    c.execute(text("UPDATE public.users SET password_hash=:h WHERE user_id=:u"),{"h":password_hash(data.new_password),"u":token["user_id"]})
    c.execute(text("DELETE FROM public.auth_tokens WHERE user_id=:u"),{"u":token["user_id"]})
    response=JSONResponse({"status":"success"});response.delete_cookie(COOKIE,path="/")
    return response

@router.post("/logout")
def logout(request:Request,c=Depends(connection)):
    c.execute(text("DELETE FROM public.auth_tokens WHERE token_hash=:t"),{"t":digest(request.cookies.get(COOKIE,""))})
    response=JSONResponse({"status":"success"});response.delete_cookie(COOKIE,path="/")
    return response

@router.get("/me")
def me(request:Request,c=Depends(connection)):
    user=current_user(c,request)
    payload=user_payload(c,user)
    pref=c.execute(text("SELECT version,answers FROM public.user_preferences WHERE user_id=:u"),{"u":user["user_id"]}).mappings().first()
    payload["preferences"]=dict(pref) if pref else None
    return payload

OPTIONS={"staple":["飯","麵"],"diet":["葷食","素食"],"cuisine":["中式","美式"],
         "flavor":["清淡","重口味"],"style":["餐廳","街頭美食"],"social":["獨享","多人分享"]}
class Preferences(BaseModel):
    version:int=1
    answers:dict[str,str]
@router.put("/preferences")
def preferences(data:Preferences,request:Request,c=Depends(connection)):
    user=current_user(c,request)
    if data.version!=1 or set(data.answers)!=set(OPTIONS) or any(v not in OPTIONS[k] for k,v in data.answers.items()):
        raise HTTPException(422,"偏好選項或版本不正確")
    c.execute(text("INSERT INTO public.user_preferences(user_id,version,answers) VALUES(:u,:v,CAST(:a AS jsonb)) "
        "ON CONFLICT(user_id) DO UPDATE SET version=excluded.version,answers=excluded.answers,updated_at=now()"),
        {"u":user["user_id"],"v":data.version,"a":json.dumps(data.answers,ensure_ascii=False)})
    return {"status":"success","version":data.version,"answers":data.answers}
