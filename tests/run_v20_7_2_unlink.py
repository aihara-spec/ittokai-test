import os,sys,json,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));os.environ['DATABASE_URL']='sqlite:///'+str(ROOT/'data'/'unlink_2072_test.db');os.environ['LINE_MOCK_MODE']='1'
import server as s
from starlette.requests import Request
request=Request({'type':'http','headers':[], 'client':('127.0.0.1',0)})
checks=0
def ck(v):
 global checks
 checks+=1;assert v
with s.SessionLocal() as db:users={u.role:u.id for u in db.query(s.User).all()}
def invoke(role,method,token=None):
 with patch.object(s,'current_user',side_effect=lambda req,db:db.get(s.User,users[role])):
  return s.line_link(s.LineLinkIn(id_token=token),request) if method=='link' else s.line_unlink(request)
def conflict(role,token):
 try:invoke(role,'link',token);raise AssertionError('expected conflict')
 except s.HTTPException as e:ck(e.status_code==409)
for cycle in range(2):
 for role in users:
  for who in users:invoke(who,'unlink')
  ck(invoke(role,'link','mock:U-SHARED')['linked'])
  other=next(x for x in users if x!=role);conflict(other,'mock:U-SHARED')
  ck(not invoke(role,'unlink')['linked'])
  with s.SessionLocal() as db:
   row=db.query(s.LineAccountLink).filter_by(user_id=users[role]).one();ck(row.line_user_id is None and row.verified==0);ck(not s.line_user_id_for(db,users[role]))
  ck(invoke(other,'link','mock:U-SHARED')['linked']);conflict(role,'mock:U-SHARED')
  invoke(other,'unlink');ck(invoke(role,'link','mock:U-SHARED')['linked'])
# Previous v20.7.1 inactive reservation is reclaimed without manual DB edits.
for who in users:invoke(who,'unlink')
with s.SessionLocal() as db:
 row=db.query(s.LineAccountLink).filter_by(user_id=users['family']).one();row.line_user_id='U-OLD';row.active=0;row.verified=1;db.get(s.User,users['family']).line_user_id='U-OLD';db.commit()
ck(invoke('admin','link','mock:U-OLD')['linked'])
with s.SessionLocal() as db:ck(not s.line_user_id_for(db,users['family']));ck(s.line_user_id_for(db,users['admin'])=='U-OLD')
# Claim rollback preserves old reservation and prevents half-transfer.
invoke('admin','unlink')
with s.SessionLocal() as db:
 row=db.query(s.LineAccountLink).filter_by(user_id=users['family']).one();row.line_user_id='U-ROLL';row.active=0;db.commit()
original=s.SessionLocal.class_.commit;calls=[0]
def fail_once(db):
 calls[0]+=1
 if calls[0]==1:raise RuntimeError('test commit failure')
 return original(db)
with patch.object(s.SessionLocal.class_,'commit',fail_once):
 try:invoke('admin','link','mock:U-ROLL');raise AssertionError('expected rollback')
 except s.HTTPException as e:ck(e.status_code==503)
with s.SessionLocal() as db:ck(db.query(s.LineAccountLink).filter_by(user_id=users['family']).one().line_user_id=='U-ROLL');ck(not s.line_user_id_for(db,users['admin']))
ck(invoke('admin','link','mock:U-ROLL')['linked'])
report={'version':'20.7.2','result':'PASS','assertions':checks,'roles':list(users),'cycles':2,'scope':'Real SQLite transactions; direct server handlers with authenticated user injection; active duplicate, unlink release, transfer, old inactive reservation, rollback','limitations':['HTTP/browser/real LINE and PostgreSQL not executed in this run']}
(ROOT/'TEST_RESULT_v20.7.2.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
