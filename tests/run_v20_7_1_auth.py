import os,sys,json,io,time,urllib.error
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import run_v20_7_1_line_integration as t
s=t.server
checks=0
def ck(v,msg):
 global checks
 checks+=1
 assert v,msg
for role in t.accounts:
 for cycle in range(2):
  t.exp(role,'POST','/api/line/unlink')
  ck(not t.exp(role,'GET','/api/bootstrap').json()['line_notification']['linked'],'unlink')
  t.exp(role,'POST','/api/line/link',json={'id_token':f'mock:U-{role.upper()}'})
  email,pw=t.accounts[role]
  t.tokens[role]=t.client.post('/api/login',json={'email':email,'password':pw}).json()['token']
  ck(t.exp(role,'GET','/api/bootstrap').json()['line_notification']['linked'],'relogin')
os.environ['LINE_MOCK_MODE']='0';os.environ['LINE_LOGIN_CHANNEL_ID']='2011515301'
class Reply(io.BytesIO):
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
def response(req,**kw):
 ck(b'client_id=2011515301' in req.data,'channel ID sent')
 return Reply(json.dumps({'sub':'U-FAMILY','aud':'2011515301','iss':'https://access.line.me','exp':time.time()+100}).encode())
with patch.object(s.urllib.request,'urlopen',side_effect=response):
 t.exp('family','POST','/api/line/link',json={'id_token':'raw-id-token'})
for out in [{'sub':'U-FAMILY'}, {'sub':'U-FAMILY','aud':'wrong','iss':'https://access.line.me','exp':time.time()+100}, {'sub':'U-FAMILY','aud':'2011515301','iss':'https://access.line.me','exp':0}]:
 with patch.object(s.urllib.request,'urlopen',side_effect=lambda *a,**k:Reply(json.dumps(out).encode())):
  t.exp('family','POST','/api/line/link',status=400,json={'id_token':'invalid'})
with patch.object(s.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('url',400,'bad',{},None)):
 t.exp('family','POST','/api/line/link',status=400,json={'id_token':'bad'})
os.environ['LINE_MOCK_MODE']='1'
# Inject one commit failure; diagnostic transaction must still persist.
commit=s.SessionLocal.class_.commit
calls=[0]
def fail_once(self):
 calls[0]+=1
 if calls[0]==1:raise RuntimeError('injected DB failure')
 return commit(self)
with patch.object(s.SessionLocal.class_,'commit',fail_once):
 r=t.exp('family','POST','/api/line/link',status=503,json={'id_token':'mock:U-REPLACEMENT'})
 ck('LINE_SAVE_FAILED' in r.text,'explicit error code')
with s.SessionLocal() as db:
 ck(s.line_user_id_for(db,t.fam_id)=='U-FAMILY','rollback preserved identity')
 ck(s.line_account_status(db,t.fam_id)['status']=='認証済み保存失敗','diagnostic persists')
t.exp('family','POST','/api/line/link',json={'id_token':'mock:U-FAMILY'})
t.exp('family','POST','/api/line/unlink')
t.exp('staff','POST','/api/line/link',status=409,json={'id_token':'mock:U-FAMILY'})
t.exp('family','POST','/api/line/link',json={'id_token':'mock:U-FAMILY'})
# HTTP push failures leave app notifications and retries use persisted outbox.
os.environ['LINE_MOCK_MODE']='0';os.environ['LINE_CHANNEL_ACCESS_TOKEN']='test-only-token'
for status in (400,403,429,500):
 with patch.object(s.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('url',status,'mock',{},io.BytesIO(b'mock error'))):
  t.exp('admin','POST','/api/messages',json={'body':f'HTTP fallback {status}','user_id':t.fam_id})
 with s.SessionLocal() as db:
  ck(db.query(s.Notification).filter_by(user_id=t.fam_id,module='chat').count()>0,'app fallback retained')
  ck(db.query(s.NotificationDelivery).filter_by(user_id=t.fam_id,channel='line',status='failed').count()>0,'HTTP failure persisted')
with patch.object(s.urllib.request,'urlopen',side_effect=lambda *a,**k:Reply(b'{}')):
 ck(t.exp('admin','POST','/api/notifications/retry-failed').json()['retried']>=1,'HTTP retry')
os.environ['LINE_MOCK_MODE']='1'
report={'version':'20.7.1','result':'PASS','additional_assertions':checks,'roles':list(t.accounts),'real_LINE_send':False,'postgresql_tested':False}
(ROOT/'TEST_RESULT_v20.7.1_AUTH.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report))
