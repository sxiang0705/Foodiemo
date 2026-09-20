from contextlib import contextmanager
from io import BytesIO
from uuid import uuid4
import os
import pytest
from PIL import Image
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.core.config import Settings,ROOT
from app.core.database import build_engine
from app.core.safety import assert_test_target,assert_test_connection,assert_test_path
from app.core.mail import CaptureMailer,SMTPMailer
from app.main import create_app

pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv('RUN_PG_TESTS')!='1',reason='Guarded PostgreSQL only')]

@pytest.fixture
def setup():
    settings=Settings.from_env();assert_test_target(settings)
    engine=build_engine(settings,readonly=False)
    root=assert_test_path(ROOT/'test-uploads'/uuid4().hex)
    class TransactionEngine:
        def dispose(self):pass
        @contextmanager
        def begin(self):
            with conn.begin_nested():yield conn
    with engine.connect() as conn:
        transaction=conn.begin()
        assert_test_connection(conn,settings)
        mail=CaptureMailer()
        app=create_app(settings,engine,write_engine=TransactionEngine(),mailer=mail,storage_root=root)
        client=TestClient(app)
        try:yield client,mail,conn,app
        finally:
            client.close();transaction.rollback()
            if root.exists():
                for path in root.iterdir():assert_test_path(path).unlink()
                root.rmdir()
    engine.dispose()

def register(client,mail,email='feature@example.test',name='測試會員'):
    r=client.post('/api/register',json=dict(email=email,name=name,password='Correct-password-1'))
    assert r.status_code==200,r.text
    code=mail.messages[-1]['code']
    r=client.post('/api/verify_email_code',json=dict(email=email,purpose='signup',code=code))
    assert r.status_code==200,r.text
    return r.json()

def jpeg(color='red'):
    out=BytesIO();Image.new('RGB',(32,24),color).save(out,'JPEG');return out.getvalue()

def test_auth_reset_revokes_sessions_and_token(setup):
    c,mail,db,app=setup
    user=register(c,mail)
    assert c.get('/api/me').json()['id']==user['id']
    old_cookie=c.cookies.get('foodiemo_session')
    r=c.post('/api/send_email_code',json=dict(email=user['email'],purpose='reset_password'))
    assert r.status_code==200
    wrong='0000' if mail.messages[-1]['code']!='0000' else '0001'
    assert c.post('/api/verify_email_code',json=dict(email=user['email'],purpose='reset_password',code=wrong)).status_code==400
    assert db.execute(text("SELECT attempts FROM email_challenges WHERE purpose='reset_password' AND user_id=:u"),dict(u=int(user['id']))).scalar()==1
    token=c.post('/api/verify_email_code',json=dict(email=user['email'],purpose='reset_password',code=mail.messages[-1]['code'])).json()['reset_token']
    payload=dict(reset_token=token,new_password='New-password-2')
    assert c.post('/api/reset_password',json=payload).status_code==200
    assert c.post('/api/reset_password',json=payload).status_code==400
    c.cookies.set('foodiemo_session',old_cookie)
    assert c.get('/api/me').status_code==401
    c.cookies.clear()
    assert c.post('/api/login',json=dict(email=user['email'],password='Correct-password-1')).status_code==401
    assert c.post('/api/login',json=dict(email=user['email'],password='New-password-2')).status_code==200
    assert c.post('/api/logout').status_code==200
    assert c.get('/api/me').status_code==401

def test_mail_failure_rolls_back_registration(setup):
    c,mail,db,app=setup
    from dataclasses import replace
    app.state.mailer=SMTPMailer(replace(Settings.from_env(),smtp_host="",smtp_from=""))
    r=c.post('/api/register',json=dict(email='no-mail@example.test',name='No Mail',password='password-123'))
    assert r.status_code==503
    assert db.execute(text("SELECT count(*) FROM users WHERE email='no-mail@example.test'")).scalar()==0

def test_preferences_and_demo_idempotency(setup):
    c,mail,db,app=setup;u=register(c,mail)
    from app.api.accounts import OPTIONS
    answers={k:v[0] for k,v in OPTIONS.items()}
    assert c.put('/api/preferences',json=dict(version=1,answers=answers)).status_code==200
    assert c.get('/api/me').json()['preferences']['answers']==answers
    assert c.put('/api/preferences',json=dict(version=1,answers={})).status_code==422
    for _ in range(2):
        r=c.post('/api/upgrade_premium');assert r.status_code==200,r.text
        assert r.json()['simulated'] is True
    assert db.execute(text('SELECT count(*) FROM payment_transactions WHERE user_id=:u AND amount=0'),dict(u=int(u['id']))).scalar()==1
    assert c.get('/api/me').json()['is_premium'] is True
    assert c.post('/api/upgrade_premium',headers={'origin':'https://evil.example'}).status_code==403

def test_photos_order_mentions_ownership_delete(setup):
    c,mail,db,app=setup
    other=register(c,mail,'other@example.test','好友測試')
    c.cookies.clear();user=register(c,mail)
    db.execute(text('INSERT INTO restaurant_rows (restaurant_id,"googleMaps_id",title) VALUES (981234,\'feature-test\',\'測試地點\')'))
    assert c.get('/api/locations?q=測試').json()['items'][0]['id']=='981234'
    assert c.get('/api/members?q=好友').json()['items']==[dict(id=other['id'],name='好友測試')]
    data=dict(restaurant_id='981234',mention_ids='["'+other['id']+'"]')
    r=c.post('/api/upload_memory_post',data=data,files=[('files',('a.jpg',jpeg(),'image/jpeg')),('files',('b.jpg',jpeg('blue'),'image/jpeg'))])
    assert r.status_code==200,r.text
    record=r.json()['id'];post=c.get('/api/get_post/'+record).json();a,b=post['imageUrls']
    assert post['mentions'][0]['id']==other['id']
    assert c.get(a).status_code==200
    import json
    r=c.post('/api/update_post',data=dict(data,post_id=record,photo_order=json.dumps([dict(existing=b),dict(new=0),dict(existing=a)])),files={'files':('c.jpg',jpeg('green'),'image/jpeg')})
    assert r.status_code==200,r.text
    urls=c.get('/api/get_post/'+record).json()['imageUrls']
    assert urls[0]==b and urls[2]==a and len(urls)==3
    with TestClient(app) as stranger:
        assert stranger.get(a).status_code==401
        assert stranger.post('/api/login',json=dict(email=other['email'],password='Correct-password-1')).status_code==200
        # A tagged member may view the photo in My Memories but cannot edit/delete it.
        assert stranger.get(a).status_code==200
        assert stranger.delete('/api/posts/'+record).status_code==404
        assert stranger.get('/api/get_memories',params={'email':user['email']}).status_code==403
    assert c.post('/api/upload_memory_post',files={'files':('bad.jpg',b'not an image','image/jpeg')}).status_code==422
    assert c.delete('/api/posts/'+record).status_code==200
    assert c.get('/api/get_post/'+record).status_code==404
    assert c.get(a).status_code==404
    assert list(app.state.storage_root.iterdir())==[]


def test_tagged_post_is_in_memories_and_can_be_untagged(setup):
    c,mail,db,app=setup
    owner=register(c,mail,'memory-owner@example.test','貼文作者')
    c.cookies.clear()
    tagged=register(c,mail,'memory-tagged@example.test','被標記會員')
    c.cookies.clear()
    assert c.post('/api/login',json={'email':owner['email'],'password':'Correct-password-1'}).status_code==200
    created=c.post('/api/upload_memory_post',data={'mention_ids':'["'+tagged['id']+'"]'},files={'files':('tagged.jpg',jpeg(),'image/jpeg')})
    assert created.status_code==200,created.text
    record=created.json()['id']
    assert c.get('/api/get_memories').json()[0]['isOwner'] is True
    with TestClient(app) as tagged_client:
        assert tagged_client.post('/api/login',json={'email':tagged['email'],'password':'Correct-password-1'}).status_code==200
        assert tagged_client.get('/api/get_memories').json()==[]
        memories=tagged_client.get('/api/get_memories',params={'scope':'memories'}).json()
        social=tagged_client.get('/api/get_memories',params={'scope':'social'}).json()
        assert len(memories)==1 and len(social)==1 and social[0]['id']==record
        assert memories[0]['isTagged'] is True and memories[0]['isOwner'] is False and memories[0]['canEdit'] is False
        assert tagged_client.get(memories[0]['url']).status_code==200
        assert tagged_client.post('/api/posts/'+record+'/like').status_code==200
        assert tagged_client.delete('/api/posts/'+record+'/mention').json()['untagged'] is True
        assert tagged_client.get('/api/get_memories',params={'scope':'memories'}).json()==[]
        assert tagged_client.delete('/api/posts/'+record+'/mention').status_code==404
    assert c.get('/api/get_post/'+record).json()['mentions']==[]

def test_capture_message_creates_comment_and_like_persists(setup):
    c,mail,db,app=setup;register(c,mail)
    r=c.post('/api/upload_memory_post',data={'initial_comment':'今天的午餐 🍜','photo_location_text':'照片位置 25.03300, 121.56540'},files={'files':('capture.jpg',jpeg(),'image/jpeg')})
    assert r.status_code==200,r.text
    record=r.json()['id']
    post=c.get('/api/get_post/'+record).json()
    assert post['comments'][0]['text']=='今天的午餐 🍜'
    assert post['commentCount']==1
    assert post['location']=='照片位置 25.03300, 121.56540'
    assert post['likes']==0 and post['isLiked'] is False
    assert c.post('/api/posts/'+record+'/like').json()=={'status':'success','liked':True}
    post=c.get('/api/get_post/'+record).json()
    assert post['likes']==1 and post['isLiked'] is True
    # The primary key makes repeated taps idempotent.
    assert c.post('/api/posts/'+record+'/like').status_code==200
    assert c.get('/api/get_post/'+record).json()['likes']==1
    assert c.delete('/api/posts/'+record+'/like').json()=={'status':'success','liked':False}
    post=c.get('/api/get_post/'+record).json()
    assert post['likes']==0 and post['isLiked'] is False


def test_friend_search_request_approve_and_list(setup):
    c,mail,db,app=setup
    friend=register(c,mail,'friend@example.test','好友會員')
    c.cookies.clear();me=register(c,mail,'member@example.test','目前會員')
    result=c.get('/api/friends/search?q=好友').json()['items']
    assert result[0]['id']==friend['id'] and result[0]['relationship']=='none'
    request_id=c.post('/api/friends/requests',json={'user_id':int(friend['id'])}).json()['request_id']
    assert c.get('/api/friends/search?q=好友').json()['items'][0]['relationship']=='pending_outgoing'
    c.cookies.clear();assert c.post('/api/login',json={'email':friend['email'],'password':'Correct-password-1'}).status_code==200
    incoming=c.get('/api/friends').json()['incoming']
    assert incoming[0]['request_id']==request_id and incoming[0]['id']==me['id']
    assert c.post('/api/friends/requests/'+request_id+'/approve').status_code==200
    assert c.get('/api/friends').json()['friends'][0]['id']==me['id']
    c.cookies.clear();assert c.post('/api/login',json={'email':me['email'],'password':'Correct-password-1'}).status_code==200
    assert c.get('/api/friends').json()['friends'][0]['id']==friend['id']


def test_friend_chat_requires_accepted_friend_and_persists_messages(setup):
    c,mail,db,app=setup
    friend=register(c,mail,'chat-friend@example.test','聊天好友')
    c.cookies.clear();me=register(c,mail,'chat-member@example.test','聊天會員')
    request_id=c.post('/api/friends/requests',json={'user_id':int(friend['id'])}).json()['request_id']
    c.cookies.clear();assert c.post('/api/login',json={'email':friend['email'],'password':'Correct-password-1'}).status_code==200
    assert c.get('/api/chats/'+me['id']+'/messages').status_code==403
    assert c.post('/api/friends/requests/'+request_id+'/approve').status_code==200
    assert c.post('/api/chats/'+me['id']+'/messages',json={'text':'你好，今天吃什麼？'}).status_code==200
    c.cookies.clear();assert c.post('/api/login',json={'email':me['email'],'password':'Correct-password-1'}).status_code==200
    result=c.get('/api/chats/'+friend['id']+'/messages').json()
    assert result['friend']['id']==friend['id'] and result['messages'][0]['text']=='你好，今天吃什麼？'
    sent=c.post('/api/chats/'+friend['id']+'/messages',json={'text':'我想吃拉麵'}).json()['message']
    assert sent['sender_id']==me['id']
    assert c.post('/api/chats/'+friend['id']+'/messages',json={'text':'   '}).status_code==422
def test_otp_attempt_limit_expiry_and_resend(setup):
    c,mail,db,app=setup
    email='otp-limit@example.test'
    assert c.post('/api/register',json=dict(email=email,name='OTP Test',password='Correct-password-1')).status_code==200
    correct=mail.messages[-1]['code'];wrong='1111' if correct!='1111' else '2222'
    assert c.post('/api/send_email_code',json=dict(email=email,purpose='signup')).status_code==429
    for _ in range(5):assert c.post('/api/verify_email_code',json=dict(email=email,purpose='signup',code=wrong)).status_code==400
    assert c.post('/api/verify_email_code',json=dict(email=email,purpose='signup',code=correct)).status_code==400
    db.execute(text("UPDATE email_challenges SET attempts=0,expires_at=now()-interval '1 second'"))
    assert c.post('/api/verify_email_code',json=dict(email=email,purpose='signup',code=correct)).status_code==400
    assert c.get('/api/me').status_code==401

def test_invalid_upload_rolls_back_files_and_last_photo_delete(setup):
    c,mail,db,app=setup;register(c,mail)
    r=c.post('/api/upload_memory_post',files=[('files',('valid.jpg',jpeg(),'image/jpeg')),('files',('invalid.jpg',b'not image','image/jpeg'))])
    assert r.status_code==422
    assert not app.state.storage_root.exists() or list(app.state.storage_root.iterdir())==[]
    assert c.get('/api/get_memories').json()==[]
    r=c.post('/api/upload_memory_post',files={'files':('a.jpg',jpeg(),'image/jpeg')});assert r.status_code==200
    record=r.json()['id'];url=c.get('/api/get_post/'+record).json()['url']
    assert c.delete('/api/delete_single_photo',params=dict(post_id=record,photo_url=url)).status_code==200
    assert c.get('/api/get_memories').json()==[]
    assert list(app.state.storage_root.iterdir())==[]
