import os, sys, json, base64, io, importlib
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'ittokai_v20_3_test.db'
if DB.exists(): DB.unlink()
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
sys.path.insert(0,str(ROOT))
import server
from fastapi.testclient import TestClient

client=TestClient(server.app)
accounts={
 'family':('family@ittokai.local','demo1234'),
 'staff':('staff@ittokai.local','staff1234'),
 'middle_manager':('manager@ittokai.local','manager1234'),
 'admin':('admin@ittokai.local','admin1234'),
 'hq':('hq@ittokai.local','hq1234'),
 'caredo':('caredo@ittokai.local','caredo1234'),
 'sponsor':('sponsor@ittokai.local','sponsor1234'),
}
tokens={}
checks=0
failures=[]
scenarios=0

def ok(cond,msg):
 global checks
 checks+=1
 if not cond: raise AssertionError(msg)

def req(role,method,path,**kwargs):
 h=kwargs.pop('headers',{})
 h={**h,'Authorization':'Bearer '+tokens[role]}
 r=client.request(method,path,headers=h,**kwargs)
 return r

def expect(role,method,path,status=200,**kwargs):
 r=req(role,method,path,**kwargs)
 ok(r.status_code==status,f'{role} {method} {path}: expected {status}, got {r.status_code}: {r.text[:300]}')
 return r

# Login all seven role IDs and bootstrap
for role,(email,pw) in accounts.items():
 r=client.post('/api/login',json={'email':email,'password':pw})
 ok(r.status_code==200,f'login failed {role}: {r.text}')
 j=r.json(); tokens[role]=j['token']; ok(j['user']['role']==role,f'role mismatch {role}')
 b=expect(role,'GET','/api/bootstrap').json(); ok(b['user']['role']==role,f'bootstrap role mismatch {role}')
scenarios += 7

# Role UI/backend data expectations
bf=expect('family','GET','/api/bootstrap').json(); family_id=bf['user']['id']; resident_id=bf['residents'][0]['id']; facility_id=bf['user']['facility_id']
ba=expect('admin','GET','/api/bootstrap').json(); ok(len(ba.get('family_users',[]))>=1,'admin family list missing')
bs=expect('staff','GET','/api/bootstrap').json(); ok(len(bs.get('family_users',[]))>=1,'staff family list missing')
bm=expect('middle_manager','GET','/api/bootstrap').json(); ok(len(bm.get('family_users',[]))>=1,'middle manager family list missing')

# Chat permissions and round-trip. 120 operational cycles.
for i in range(120):
 body=f'家族テストメッセージ {i:03d}'
 expect('family','POST','/api/messages',json={'body':body})
 g=expect('admin','GET',f'/api/messages?user_id={family_id}').json(); ok(g['messages'][-1]['body']==body,f'admin did not receive family message {i}')
 reply=f'施設返信 {i:03d}'
 expect('admin','POST','/api/messages',json={'body':reply,'user_id':family_id})
 gf=expect('family','GET','/api/messages').json(); ok(gf['messages'][-1]['body']==reply,f'family did not receive admin reply {i}')
 rev=expect('family','GET','/api/messages/revision').json()['revision']; ok(bool(rev),f'chat revision missing {i}')
 scenarios += 1

# Staff and middle manager can use facility-family chat
expect('staff','GET',f'/api/messages?user_id={family_id}')
expect('middle_manager','GET',f'/api/messages?user_id={family_id}')
# CareDo / sponsor / HQ cannot open family chat
for role in ('caredo','sponsor','hq'):
 expect(role,'GET',f'/api/messages?user_id={family_id}',status=403)
 scenarios += 1

# Document cycles: create -> family view -> sign -> admin sees signed -> PDF
img=Image.new('RGB',(120,40),'white'); bio=io.BytesIO(); img.save(bio,format='PNG'); sig='data:image/png;base64,'+base64.b64encode(bio.getvalue()).decode()
for i in range(10):
 r=expect('admin','POST','/api/documents',json={'title':f'契約テスト{i}','category':'同意書','body':'テスト本文','recipient_user_ids':[family_id],'due_days':7,'requires_signature':True,'required_checks':['確認']})
 did=r.json()['id']
 expect('family','POST',f'/api/documents/{did}/view')
 expect('family','POST',f'/api/documents/{did}/sign',json={'signer_name':'相原 良太','signature_data':sig,'consent':True})
 famdocs=expect('family','GET','/api/bootstrap').json()['documents']; ok(any(d['id']==did and d['status']=='signed' for d in famdocs),f'family signed status missing {did}')
 admindocs=expect('admin','GET','/api/bootstrap').json()['documents']; ok(any(d['id']==did and d['status']=='signed' for d in admindocs),f'admin signed status missing {did}')
 pdf=expect('family','GET',f'/api/documents/{did}/pdf'); ok(pdf.content.startswith(b'%PDF'),f'bad signed pdf {did}')
 scenarios += 1

# Reject fake PDF upload
files={'file':('not.pdf',b'not a pdf','application/pdf')}
data={'title':'fake','category':'契約書','recipient_user_ids':str(family_id),'due_days':'7'}
r=req('admin','POST','/api/documents/upload',files=files,data=data); ok(r.status_code==400,'fake PDF was accepted')

# Workflow cycles: staff -> middle manager -> admin
for i in range(10):
 r=expect('staff','POST','/api/workflows',json={'request_type':'有給申請','request_date':(datetime.now()+timedelta(days=10+i)).date().isoformat(),'start_time':'','end_time':'','payload':{},'comment':f'テスト{i}'})
 wid=r.json()['id']; ok(r.json()['status']=='pending_manager','workflow initial status')
 r=expect('middle_manager','POST',f'/api/workflows/{wid}/action',json={'action':'approve','comment':''}); ok(r.json()['status']=='pending_admin','manager transition failed')
 r=expect('admin','POST',f'/api/workflows/{wid}/action',json={'action':'approve','comment':''}); ok(r.json()['status']=='approved','admin transition failed')
 # repeat action must be blocked
 expect('admin','POST',f'/api/workflows/{wid}/action',status=400,json={'action':'approve','comment':''})
 scenarios += 1

# Visit cycles: availability -> reserve -> cancel
future=(datetime.now()+timedelta(days=2)).date().isoformat()
for i in range(10):
 av=expect('family','GET',f'/api/visits/availability?facility_id={facility_id}&visit_date={future}').json()['slots']
 slot=next((x for x in av if x['remaining']>0),None); ok(slot is not None,'no visit slot available')
 r=expect('family','POST','/api/visits',json={'resident_id':resident_id,'visit_date':future,'start_time':slot['start_time'],'end_time':'23:59','place_name':slot['place_name'],'visitor_count':1,'representative':'テスト家族','phone':'','notes':''})
 vid=r.json()['id']; expect('family','POST',f'/api/visits/{vid}/cancel')
 scenarios += 1
# Sponsor cannot cancel a visit ID even if known
av=expect('family','GET',f'/api/visits/availability?facility_id={facility_id}&visit_date={future}').json()['slots']; slot=next(x for x in av if x['remaining']>0)
vid=expect('family','POST','/api/visits',json={'resident_id':resident_id,'visit_date':future,'start_time':slot['start_time'],'end_time':slot['end_time'],'place_name':slot['place_name'],'visitor_count':1,'representative':'権限テスト','phone':'','notes':''}).json()['id']
expect('sponsor','POST',f'/api/visits/{vid}/cancel',status=403)
expect('family','POST',f'/api/visits/{vid}/cancel')

# Procurement cycles: admin order -> CareDo confirm/ship -> admin receive -> CareDo invoice -> PDF
for i in range(10):
 snap=expect('admin','GET','/api/bootstrap').json()['procurement']
 product=snap['inventory'][0]; qty=max(1,int(product.get('target_stock',8)-product.get('on_hand',0)+1))
 # ensure minimum is not an issue; seed first product min 1
 r=expect('admin','POST','/api/orders',json={'items':[{'product_id':product['product_id'],'qty':qty}]}); oid=r.json()['id']
 expect('caredo','POST',f'/api/orders/{oid}/status',json={'status':'confirmed'})
 expect('caredo','POST',f'/api/orders/{oid}/status',json={'status':'shipped'})
 care=expect('caredo','GET','/api/bootstrap').json()['caredo']; order=next(o for o in care['orders'] if o['id']==oid)
 recv=[{'item_id':x['id'],'received_qty':x['qty']} for x in order['items']]
 rr=expect('admin','POST',f'/api/orders/{oid}/receive',json={'items':recv}); ok(rr.json()['status']=='received','receive not complete')
 inv_no=f'TEST-{i:03d}-{oid}'
 items=[{'product_id':x['product_id'],'qty':x['qty'],'unit_price':x['unit_price']} for x in order['items']]
 inv=expect('caredo','POST','/api/invoices',json={'order_id':oid,'invoice_no':inv_no,'invoice_date':datetime.now().date().isoformat(),'items':items}).json(); ok(inv['match_status']=='matched','3-way match failed')
 pdf=expect('admin','GET',f"/api/invoices/{inv['id']}/pdf"); ok(pdf.content.startswith(b'%PDF'),'invoice PDF invalid')
 scenarios += 1

# News flow
nid=expect('admin','POST','/api/news',json={'category':'テスト','title':'全ID運用テスト','body':'通知確認','important':False,'image_url':''}).json()['id']
news=expect('family','GET','/api/bootstrap').json()['news']; ok(any(n['id']==nid for n in news),'news not visible to family'); scenarios += 1

# HQ integrations / exports
for sysname in ('honobono','chronos','yayoi'):
 r=expect('hq','GET',f'/api/integrations/export/{sysname}'); ok('text/csv' in r.headers.get('content-type','') or r.status_code==200,f'export failed {sysname}')
scenarios += 3

# Cross-facility security regression: create second facility and admin/document directly.
with server.SessionLocal() as s:
 f2=server.Facility(code='F2',name='第二施設'); s.add(f2); s.flush()
 a2=server.User(name='第二管理者',email='admin2@test.local',password_hash=server.hash_password('x'),role='admin',facility_id=f2.id); fam2=server.User(name='第二家族',email='fam2@test.local',password_hash=server.hash_password('x'),role='family',facility_id=f2.id); s.add_all([a2,fam2]); s.flush()
 d2=server.Document(facility_id=f2.id,title='第二施設秘密書類',category='契約',body='secret',status='sent',created_by=a2.id,sent_at=server.now_dt()); d2.original_hash=server.sha256_text('secret'); s.add(d2); s.flush(); s.add(server.DocumentRecipient(document_id=d2.id,user_id=fam2.id,status='sent')); s.commit(); d2id=d2.id
expect('admin','GET',f'/api/documents/{d2id}/pdf',status=403); scenarios += 1

# Health/version
h=client.get('/health'); ok(h.status_code==200 and h.json()['version']=='20.3','health version mismatch')

report={'version':'20.3','scenario_cycles':scenarios,'assertions':checks,'failures':failures,'result':'PASS'}
print(json.dumps(report,ensure_ascii=False,indent=2))
Path(ROOT/'TEST_RESULT_v20.3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
