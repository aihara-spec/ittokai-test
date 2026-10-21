import os, sys, json, base64, io
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
DB=ROOT/'data'/'ittokai_v20_7_line_test.db'
if DB.exists(): DB.unlink()
os.environ['DATABASE_URL']=f'sqlite:///{DB}'
os.environ['LINE_MOCK_MODE']='1'
os.environ['LIFF_ID']='TEST-LIFF-ID'
os.environ['LIFF_BASE_URL']='https://liff.line.me/TEST-LIFF-ID'
os.environ['NOTIFICATION_CRON_SECRET']='test-cron-secret'
sys.path.insert(0,str(ROOT))
import server
from fastapi.testclient import TestClient
client=TestClient(server.app)

accounts={
 'family':('family@ittokai.local','demo1234'), 'staff':('staff@ittokai.local','staff1234'),
 'middle_manager':('manager@ittokai.local','manager1234'), 'admin':('admin@ittokai.local','admin1234'),
 'hq':('hq@ittokai.local','hq1234'), 'caredo':('caredo@ittokai.local','caredo1234'),
 'sponsor':('sponsor@ittokai.local','sponsor1234')}
tokens={}; checks=0; scenarios=0; failures=[]
def ck(v,m):
 global checks; checks+=1
 if not v: raise AssertionError(m)
def req(role,method,path,**kw):
 h=kw.pop('headers',{}); h={**h,'Authorization':'Bearer '+tokens[role]}; return client.request(method,path,headers=h,**kw)
def exp(role,method,path,status=200,**kw):
 r=req(role,method,path,**kw); ck(r.status_code==status,f'{role} {method} {path}: {r.status_code} {r.text[:300]}'); return r
def line_deliveries(event_type=None,user_id=None,status=None):
 with server.SessionLocal() as s:
  q=s.query(server.NotificationDelivery,server.NotificationEvent).join(server.NotificationEvent,server.NotificationDelivery.event_id==server.NotificationEvent.id).filter(server.NotificationDelivery.channel=='line')
  if event_type: q=q.filter(server.NotificationEvent.event_type==event_type)
  if user_id: q=q.filter(server.NotificationDelivery.user_id==user_id)
  if status: q=q.filter(server.NotificationDelivery.status==status)
  return q.all()
def event_count(event_type):
 with server.SessionLocal() as s: return s.query(server.NotificationEvent).filter_by(event_type=event_type).count()

# login all roles
for role,(email,pw) in accounts.items():
 r=client.post('/api/login',json={'email':email,'password':pw}); ck(r.status_code==200,f'login {role}'); tokens[role]=r.json()['token']
scenarios+=7
bf=exp('family','GET','/api/bootstrap').json(); fam_id=bf['user']['id']; res_id=bf['residents'][0]['id']; fid=bf['user']['facility_id']
admin_id=exp('admin','GET','/api/bootstrap').json()['user']['id']; manager_id=exp('middle_manager','GET','/api/bootstrap').json()['user']['id']; staff_id=exp('staff','GET','/api/bootstrap').json()['user']['id']; caredo_id=exp('caredo','GET','/api/bootstrap').json()['user']['id']; sponsor_id=exp('sponsor','GET','/api/bootstrap').json()['user']['id']
ck(bf['line_notification']['linked'] is False,'family unexpectedly linked')

# unlinked fallback: app delivery must remain, LINE is skipped and logged
r=exp('admin','POST','/api/documents',json={'title':'未連携通知検証','category':'同意書','body':'本文','recipient_user_ids':[fam_id],'resident_id':res_id,'due_days':7,'requires_signature':True,'required_checks':['確認']}); d_unlinked=r.json()['id']
with server.SessionLocal() as s:
 ev=s.query(server.NotificationEvent).filter_by(event_key=f'document.requested:{d_unlinked}:{fam_id}').one(); ds=s.query(server.NotificationDelivery).filter_by(event_id=ev.id,user_id=fam_id).all(); sts={x.channel:x.status for x in ds}
 ck(sts.get('app')=='sent','app fallback missing'); ck(sts.get('line')=='skipped_unlinked','unlinked LINE not logged')
scenarios+=1

# link each role via verified mock ID token
for role in accounts:
 r=exp(role,'POST','/api/line/link',json={'id_token':f'mock:U-{role.upper()}'}); ck(r.json()['linked'] is True,f'link {role}')
 b=exp(role,'GET','/api/bootstrap').json(); ck(b['line_notification']['linked'] is True,f'bootstrap linked {role}')
scenarios+=7

# duplicate LINE account must be rejected
exp('staff','POST','/api/line/link',status=409,json={'id_token':'mock:U-FAMILY'}); scenarios+=1

# document request -> family LINE, sign -> facility admin LINE, deep link and privacy body
r=exp('admin','POST','/api/documents',json={'title':'秘密の契約書名','category':'契約書','body':'要介護情報を含む想定本文','recipient_user_ids':[fam_id],'resident_id':res_id,'due_days':2,'requires_signature':True,'required_checks':['確認']}); did=r.json()['id']
rows=line_deliveries('document.requested',fam_id,'sent'); ck(any(str(did) in e.entity_id for d,e in rows),'document family line missing')
d,e=rows[-1]; ck('view=documents' in d.deep_link and f'entity={did}' in d.deep_link,'document deep link missing'); ck('秘密の契約書名' not in e.body and '要介護' not in e.body,'sensitive document detail leaked to LINE body')
img=Image.new('RGB',(80,30),'white'); bio=io.BytesIO(); img.save(bio,format='PNG'); sig='data:image/png;base64,'+base64.b64encode(bio.getvalue()).decode()
exp('family','POST',f'/api/documents/{did}/sign',json={'signer_name':'家族','signature_data':sig,'consent':True})
ck(line_deliveries('document.signed',admin_id,'sent'),'document signed -> admin LINE missing')
scenarios+=1

# manual reminder de-dupe same day
before=event_count('document.reminder'); exp('admin','POST',f'/api/documents/{d_unlinked}/remind'); mid=event_count('document.reminder'); exp('admin','POST',f'/api/documents/{d_unlinked}/remind'); after=event_count('document.reminder'); ck(mid==before+1 and after==mid,'manual reminder duplicate not prevented'); scenarios+=1

# workflow: staff -> middle manager -> admin -> applicant
future=(datetime.now()+timedelta(days=10)).date().isoformat()
w=exp('staff','POST','/api/workflows',json={'request_type':'有給申請','request_date':future,'start_time':'','end_time':'','payload':{'leave_days':1},'comment':'通知検証'}).json(); wid=w['id']
ck(line_deliveries('workflow.submitted',manager_id,'sent'),'workflow -> manager LINE missing')
exp('middle_manager','POST',f'/api/workflows/{wid}/action',json={'action':'approve','comment':''}); ck(line_deliveries('workflow.forwarded',admin_id,'sent'),'workflow forward -> admin LINE missing')
exp('admin','POST',f'/api/workflows/{wid}/action',json={'action':'approve','comment':''}); ck(line_deliveries('workflow.result',staff_id,'sent'),'workflow result -> staff LINE missing'); scenarios+=1

# shop CareDo: family order -> CareDo; state transitions -> family
fam=exp('family','GET','/api/bootstrap').json(); prod=fam['shop_recommendations'][0]
o=exp('family','POST','/api/shop/orders',json={'product_kind':'caredo','product_id':prod['id'],'qty':1,'resident_id':res_id,'gift_message':'','delivery_date':''}).json(); oid=o['id']
ck(line_deliveries('shop.order_submitted',caredo_id,'sent'),'CareDo shop LINE missing')
for st in ('accepted','shipped','delivered'): exp('caredo','POST',f'/api/shop/orders/{oid}/status',json={'status':st})
with server.SessionLocal() as s:
 n=s.query(server.NotificationEvent).filter(server.NotificationEvent.event_key.like(f'shop.order_status:{oid}:%')).count(); ck(n==3,'family order status notification count mismatch')
ck(len(line_deliveries('shop.order_status',fam_id,'sent'))>=4,'family shop status LINE missing')
scenarios+=1

# sponsor gift: family order -> owner; merchant payload excludes family/resident identity
fam=exp('family','GET','/api/bootstrap').json(); gifts=fam.get('gift_recommendations',[]); ck(bool(gifts),'gift product missing'); gift=gifts[0]
go=exp('family','POST','/api/shop/orders',json={'product_kind':'sponsor','product_id':gift['id'],'qty':1,'resident_id':res_id,'gift_message':'おめでとう','delivery_date':future}).json(); goid=go['id']
ck(line_deliveries('shop.order_submitted',sponsor_id,'sent'),'sponsor gift LINE missing')
sp=exp('sponsor','GET','/api/bootstrap').json()['sponsor']; merchant=next(x for x in sp['customer_orders'] if x['id']==goid); ck('family_user_id' not in merchant and 'resident_id' not in merchant and 'resident_name' not in merchant,'merchant payload leaks family/resident identity')
exp('caredo','POST',f'/api/shop/orders/{goid}/status',status=403,json={'status':'accepted'})
exp('sponsor','POST',f'/api/shop/orders/{goid}/status',json={'status':'accepted'}); scenarios+=1

# visit: request -> facility and auto-confirm -> family
future2=(datetime.now()+timedelta(days=3)).date().isoformat(); slots=exp('family','GET',f'/api/visits/availability?facility_id={fid}&visit_date={future2}').json()['slots']; slot=next(x for x in slots if x['remaining']>0)
v=exp('family','POST','/api/visits',json={'resident_id':res_id,'visit_date':future2,'start_time':slot['start_time'],'end_time':slot['end_time'],'place_name':slot['place_name'],'visitor_count':1,'representative':'家族','phone':'','notes':''}).json(); vid=v['id']
ck(line_deliveries('visit.requested',admin_id,'sent'),'visit -> admin LINE missing'); ck(line_deliveries('visit.confirmed',fam_id,'sent'),'visit confirm -> family LINE missing'); scenarios+=1

# CareDo inventory auto-order candidate -> facility + CareDo; no duplicate event on reevaluation
np=exp('caredo','POST','/api/products',json={'sku':'LINE-AUTO-1','name':'LINE在庫通知検証','category':'日用品','unit':'ケース','standard_price':1000,'purchase_price':800,'sale_price':1000,'short_message':'検証','min_order_qty':1,'lead_time_days':2}).json(); pid=np['id']
with server.SessionLocal() as s: s.add(server.Inventory(facility_id=fid,product_id=pid,location='主倉庫',on_hand=1,safety_stock=2,reorder_point=5,target_stock=10)); s.commit()
pol=exp('caredo','POST','/api/inventory/policy',json={'facility_id':fid,'product_id':pid,'reorder_point':5,'target_stock':10,'reorder_qty':8,'max_stock':12,'auto_order_mode':'approval'}).json(); ck(len(pol['auto_order_events'])==1,'auto candidate missing')
ck(line_deliveries('inventory.auto_order_candidate',admin_id,'sent'),'inventory candidate admin LINE missing'); ck(line_deliveries('inventory.auto_order_candidate',caredo_id,'sent'),'inventory candidate CareDo LINE missing')
with server.SessionLocal() as s:
 c1=s.query(server.AutoOrderEvent).filter_by(product_id=pid,status='pending_approval').count()
exp('caredo','POST','/api/inventory/evaluate-auto-orders')
with server.SessionLocal() as s:
 c2=s.query(server.AutoOrderEvent).filter_by(product_id=pid,status='pending_approval').count()
ck(c1==1 and c2==1,'duplicate auto-order candidate created for same product'); scenarios+=1

# rule can suppress LINE while leaving app notification
exp('admin','POST','/api/notifications/rules',json={'event_type':'document.requested','recipient_role':'family','app_enabled':True,'line_enabled':False,'repeat_after_hours':24,'deadline_before_hours':72,'active':True})
r=exp('admin','POST','/api/documents',json={'title':'ルール検証','category':'同意書','body':'本文','recipient_user_ids':[fam_id],'resident_id':res_id,'due_days':7,'requires_signature':True,'required_checks':['確認']}); rd=r.json()['id']
with server.SessionLocal() as s:
 ev=s.query(server.NotificationEvent).filter_by(event_key=f'document.requested:{rd}:{fam_id}').one(); ds=s.query(server.NotificationDelivery).filter_by(event_id=ev.id,user_id=fam_id).all(); ck(any(x.channel=='app' for x in ds),'rule app notification missing'); ck(not any(x.channel=='line' for x in ds),'rule failed to suppress LINE')
# restore
exp('admin','POST','/api/notifications/rules',json={'event_type':'document.requested','recipient_role':'family','app_enabled':True,'line_enabled':True,'repeat_after_hours':24,'deadline_before_hours':72,'active':True}); scenarios+=1

# failed actual push is logged; retry later succeeds in mock mode
os.environ['LINE_MOCK_MODE']='0'; os.environ.pop('LINE_CHANNEL_ACCESS_TOKEN',None)
r=exp('admin','POST','/api/documents',json={'title':'再送検証','category':'同意書','body':'本文','recipient_user_ids':[fam_id],'resident_id':res_id,'due_days':7,'requires_signature':True,'required_checks':['確認']}); fd=r.json()['id']; ck(any(str(fd)==e.entity_id for d,e in line_deliveries('document.requested',fam_id,'failed')),'LINE failure not logged')
os.environ['LINE_MOCK_MODE']='1'; rr=exp('admin','POST','/api/notifications/retry-failed').json(); ck(rr['retried']>=1,'failed retry not attempted'); ck(any(str(fd)==e.entity_id for d,e in line_deliveries('document.requested',fam_id,'sent')),'retry did not become sent'); scenarios+=1

# notification read + delivery audit permissions
fb=exp('family','GET','/api/bootstrap').json(); unread=next((n for n in fb['notifications'] if not n['read_at']),None); ck(unread is not None,'no unread notification'); exp('family','POST',f"/api/notifications/{unread['id']}/read")
exp('family','GET','/api/notifications/deliveries',status=403); dl=exp('admin','GET','/api/notifications/deliveries').json(); ck(len(dl['items'])>0,'admin delivery log empty'); scenarios+=1

# cron reminders: pending document due soon should notify at most once per repeat window
before=event_count('document.reminder'); cr=client.post('/api/notifications/run-reminders',headers={'x-ittokai-cron-secret':'test-cron-secret'}); ck(cr.status_code==200,'cron secret failed'); first=cr.json(); cr2=client.post('/api/notifications/run-reminders',headers={'x-ittokai-cron-secret':'test-cron-secret'}); ck(cr2.status_code==200,'cron second call failed'); second=cr2.json(); ck(second['documents']==0,'scheduled document reminder repeated inside repeat window'); scenarios+=1

# transactional outbox: rollback must not create/send a ghost notification
with server.SessionLocal() as s:
    u=s.get(server.User,fam_id)
    server.emit_notification_event(s,'document.requested',[fam_id],'ロールバック通知','表示されてはいけません','documents',999999,fid,admin_id,'rollback-test-event')
    s.rollback()
server.dispatch_pending_line_deliveries()
with server.SessionLocal() as s:
    ck(s.query(server.NotificationEvent).filter_by(event_key='rollback-test-event').count()==0,'rolled-back event persisted')
    ck(s.query(server.Notification).filter_by(title='ロールバック通知').count()==0,'rolled-back app notification persisted')
scenarios+=1

# administrator can see notification transport health
nh=exp('admin','GET','/api/bootstrap').json().get('notification_health',{}); ck('counts' in nh and 'failed' in nh.get('counts',{}),'notification health missing')
scenarios+=1

# unlink keeps app usable and future LINE delivery is skipped
exp('family','POST','/api/line/unlink'); ck(exp('family','GET','/api/bootstrap').json()['line_notification']['linked'] is False,'unlink failed')
r=exp('admin','POST','/api/documents',json={'title':'解除後通知','category':'同意書','body':'本文','recipient_user_ids':[fam_id],'resident_id':res_id,'due_days':7,'requires_signature':True,'required_checks':['確認']}); ud=r.json()['id']
ck(any(str(ud)==e.entity_id for d,e in line_deliveries('document.requested',fam_id,'skipped_unlinked')),'post-unlink skip not logged'); scenarios+=1

h=client.get('/health'); ck(h.status_code==200 and h.json()['version']=='20.7','health version')
report={'version':'20.7','scenarios':scenarios,'assertions':checks,'result':'PASS','failures':failures}
print(json.dumps(report,ensure_ascii=False,indent=2)); (ROOT/'TEST_RESULT_v20.7_LINE.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if DB.exists(): DB.unlink()
