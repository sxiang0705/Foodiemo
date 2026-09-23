"""Real browser + isolated PostgreSQL. Creates only named run fixtures and cleans them."""
import os,sys,json,threading,time,subprocess,socket
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env.test',override=True,encoding='utf-8-sig')
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import create_app
from app.core.config import Settings
from app.core.database import build_engine
from app.core.safety import assert_test_target,assert_test_connection
from app.core.mail import CaptureMailer
from app.core.storage import schedule_delete,collect_files
from app.core.security import digest
import uvicorn
settings=Settings.from_env();assert_test_target(settings)
engine=build_engine(settings,readonly=False)
read_engine=build_engine(settings)
with engine.connect() as c:assert_test_connection(c,settings)
run=uuid4().hex;emails=[run+'@example.test',run+'-friend@example.test']
mailbox=ROOT/'.local'/('browser-mail-'+run+'.json')
class Mailer(CaptureMailer):
    def send(self,email,code,purpose):
        if email not in emails:raise RuntimeError('Test recipient not allowed')
        super().send(email,code,purpose)
        mailbox.write_text(json.dumps(self.messages),encoding='utf-8')
mail=Mailer();app=create_app(settings,read_engine,write_engine=engine,mailer=mail)
server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8004,log_level='error',access_log=False))
thread=threading.Thread(target=server.run,daemon=True)
try:
    with TestClient(app) as client:
        r=client.post('/api/register',json=dict(email=emails[1],name='Browser Friend',password='Friend-password-1'));assert r.status_code==200
        r=client.post('/api/verify_email_code',json=dict(email=emails[1],purpose='signup',code=mail.messages[-1]['code']));assert r.status_code==200
    with engine.begin() as c:
        assert_test_connection(c,settings)
        restaurant=c.execute(text('INSERT INTO restaurant_rows ("googleMaps_id",title,address) VALUES (:g,\'Browser Restaurant\',\'Test address\') RETURNING restaurant_id'),dict(g=run)).scalar()
    thread.start()
    for _ in range(100):
        if server.started:break
        time.sleep(.1)
    assert server.started
    env=dict(os.environ,V2_BROWSER_EMAIL=emails[0],V2_BROWSER_FRIEND_EMAIL=emails[1],V2_BROWSER_MAILBOX=str(mailbox))
    result=subprocess.run(['node',str(ROOT/'tests/features.cjs')],cwd=ROOT,env=env)
    code=result.returncode
finally:
    server.should_exit=True
    if thread.is_alive():thread.join(timeout=10)
    with engine.begin() as c:
        assert_test_connection(c,settings)
        for email in emails:
            user=c.execute(text('SELECT user_id,avatar_path FROM users WHERE email=:e'),dict(e=email)).mappings().first()
            if user:
                for key in c.execute(text('SELECT p.storage_path FROM photos p JOIN records r USING(record_id) WHERE r.user_id=:u'),dict(u=user['user_id'])).scalars():schedule_delete(c,key)
                schedule_delete(c,user['avatar_path'])
                c.execute(text('DELETE FROM users WHERE user_id=:u'),dict(u=user['user_id']))
            c.execute(text('DELETE FROM login_limits WHERE key_hash=:k'),dict(k=digest(email)))
        c.execute(text('DELETE FROM restaurant_rows WHERE "googleMaps_id"=:g'),dict(g=run))
    collect_files(app);mailbox.unlink(missing_ok=True);engine.dispose();read_engine.dispose()
sys.exit(code)
