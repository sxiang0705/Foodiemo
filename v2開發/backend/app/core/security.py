import hashlib,hmac,secrets
import bcrypt
from fastapi import HTTPException
from sqlalchemy import text

COOKIE="foodiemo_session"
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def password_hash(value):
    if not 8 <= len(value) <= 128:raise HTTPException(422,"密碼需為 8 至 128 字元")
    salt=secrets.token_hex(16)
    key=hashlib.scrypt(value.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return "scrypt$"+salt+"$"+key
def password_valid(value,stored):
    try:
        if not stored or len(value)>128:return False
        if stored.startswith("scrypt$"):
            _,salt,key=stored.split("$")
            actual=hashlib.scrypt(value.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
            return hmac.compare_digest(actual,key)
        if stored.startswith(("$2a$","$2b$")) and len(value.encode())<=72:
            return bcrypt.checkpw(value.encode(),stored.encode())
    except (ValueError,TypeError):pass
    return False
def code_hash(secret,email,purpose,code):
    return hmac.new(secret.encode(),(email+":"+purpose+":"+code).encode(),hashlib.sha256).hexdigest()
def make_token(c,user_id,purpose):
    token=secrets.token_urlsafe(32)
    seconds=604800 if purpose=="session" else 600
    c.execute(text("INSERT INTO public.auth_tokens(token_hash,user_id,purpose,expires_at) VALUES (:t,:u,:p,now()+:s*interval '1 second')"),
              {"t":digest(token),"u":user_id,"p":purpose,"s":seconds})
    return token
def current_user(c,request,lock=False):
    token=request.cookies.get(COOKIE,"")
    user=c.execute(text("SELECT u.* FROM public.users u JOIN public.auth_tokens t ON t.user_id=u.user_id "
        "WHERE t.token_hash=:t AND t.purpose='session' AND t.expires_at>now() AND u.email_verified"+(" FOR UPDATE OF u" if lock else "")),
        {"t":digest(token)}).mappings().first()
    if not user:raise HTTPException(401,"登入已失效，請重新登入")
    return user
def check_email(user,email):
    if email and email.strip().lower()!=user["email"].lower():raise HTTPException(403,"無權操作其他帳號")
def user_payload(c,user):
    premium=c.execute(text("SELECT EXISTS(SELECT 1 FROM public.memberships WHERE user_id=:u AND status='active' AND (end_date IS NULL OR end_date>now()))"),
        {"u":user["user_id"]}).scalar()
    return dict(id=str(user["user_id"]),email=user["email"],username=user["username"],name=user["user_name"] or "",
                is_premium=premium,avatar_url="/api/avatars/"+str(user["user_id"]) if user["avatar_path"] else None)
def set_session(response,token,secure):
    response.set_cookie(COOKIE,token,httponly=True,secure=secure,samesite="lax",max_age=604800,path="/")
