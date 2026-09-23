from playwright.sync_api import sync_playwright
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'static'/'app.js').read_text(encoding='utf-8')
roles=['family','staff','middle_manager','admin','hq','caredo','sponsor']
labels={'family':'家族','staff':'一般職員','middle_manager':'中間管理職','admin':'施設管理者','hq':'法人本部','caredo':'ケア・ドゥ','sponsor':'外部協賛企業'}
navs={
 'family':['home','talk','news','documents','visits','me'],
 'staff':['home','talk','requests','visits','me'],
 'middle_manager':['home','talk','requests','visits','me'],
 'admin':['home','dashboard','talk','news','documents','requests','visits','procurement','me'],
 'hq':['home','dashboard','integrations','me'],
 'caredo':['home','procurement','me'],
 'sponsor':['home','me'],
}

def bootstrap(role):
    base={'user':{'id':1 if role=='family' else 10,'name':labels[role]+'テスト','email':role+'@test','role':role,'role_label':labels[role],'facility_id':1 if role not in ('hq','caredo','sponsor') else None,'department_id':1,'employee_code':'E1'},
          'facility': {'id':1,'code':'F1','name':'メゾン・二宮','corporation':'一燈会','address':'','phone':''} if role not in ('hq','caredo','sponsor') else None,
          'version':'20.3','targets':{'facilities':50,'staff':1000,'middle_managers':200,'admins':50,'families':2000,'sponsors':100},'notifications':[],
          'sync_revisions':{'all':1,'news':1,'documents':1,'workflow':1,'visits':1,'procurement':1}}
    if role=='family': base.update({'residents':[{'id':1,'name':'利用者A','facility_id':1,'service_type':'入所','relation':'家族'}],'news':[],'documents':[],'visits':[],'messages':[{'id':1,'sender_id':10,'sender_name':'施設管理者','sender_role':'admin','body':'こんにちは','created_at':'2026-09-23T09:00:00','read_at':'2026-09-23T09:01:00'}]})
    if role in ('staff','middle_manager','admin'):
        base.update({'news':[],'family_users':[{'id':1,'name':'家族A','email':'family@test'}],'my_requests':[],'visits':[]})
        if role in ('middle_manager','admin'): base['approval_queue']=[]
        if role=='admin': base.update({'documents':[],'visit_rules':[],'procurement':{'inventory':[],'suggestions':[],'orders':[],'invoices':[]}})
    if role=='hq': base.update({'dashboard':{'facilities':50,'staff':1000,'families':2000,'documents_pending':0,'workflow_pending':0,'orders_open':0},'facilities':[],'integrations':[{'system_name':'honobono','display_name':'ほのぼの','mode':'CSV/API','direction':'bidirectional','status':'ready','notes':''}]})
    if role=='caredo': base['caredo']={'supplier':{'id':1,'name':'株式会社ケア・ドゥ','site_url':''},'orders':[],'products':[]}
    if role=='sponsor': base['sponsor']={'message':'外部協賛企業ポータル','shop_url':'https://example.com'}
    return base

errors=[]; transitions=0; chat_checks=0
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    for role in roles:
        page=browser.new_page()
        page_errors=[]
        page.on('pageerror', lambda exc, pe=page_errors: pe.append(str(exc)))
        page.set_content('<!doctype html><html><body><div id="startup"></div><div id="app"></div><div id="toast"></div></body></html>')
        boot=bootstrap(role)
        page.evaluate("""(boot)=>{
          Object.defineProperty(window,'localStorage',{configurable:true,value:{_d:{ittokai_token:'tok'},getItem(k){return this._d[k]||null},setItem(k,v){this._d[k]=String(v)},removeItem(k){delete this._d[k]}}});
          Object.defineProperty(document,'hidden',{configurable:true,get(){return false}});
          history.replaceState=()=>{};
          window.__boot=boot;
          window.fetch=async (path,opt={})=>{
            const u=String(path), method=(opt.method||'GET').toUpperCase();
            const json=(obj,status=200)=>new Response(JSON.stringify(obj),{status,headers:{'Content-Type':'application/json'}});
            if(u.startsWith('/api/bootstrap')) return json(window.__boot);
            if(u.startsWith('/api/messages/revision')) return json({revision:'2:2'});
            if(u.startsWith('/api/messages') && method==='GET') return json({messages:[{id:1,sender_id:1,sender_name:'家族A',sender_role:'family',body:'テストメッセージ',created_at:'2026-09-23T09:00:00',read_at:'2026-09-23T09:01:00'}],revision:'2:2'});
            if(u.startsWith('/api/sync/revision')) return json({revision:1});
            return json({ok:true});
          };
          Object.defineProperty(navigator,'serviceWorker',{configurable:true,value:{register:()=>Promise.resolve()}});
          window.open=()=>({document:{title:'',body:{innerHTML:''}},location:{replace:()=>{}},close:()=>{}});
        }""", boot)
        page.add_script_tag(content=APP)
        page.wait_for_timeout(100)
        if page.locator('#loginForm').count(): errors.append(f'{role}: token bootstrap failed')
        # repeat every permitted view 3 times to catch rebind/navigation errors
        for _ in range(3):
            for v in navs[role]:
                sel=f'button[data-view="{v}"]'
                if page.locator(sel).count()==0:
                    errors.append(f'{role}: nav missing {v}'); continue
                page.locator(sel).first.click(); page.wait_for_timeout(5); transitions+=1
        # facility-side talk selection must actually enter thread
        if role in ('staff','middle_manager','admin'):
            page.locator('button[data-view="talk"]').first.click(); page.wait_for_timeout(10)
            if page.locator('[data-chat]').count()!=1: errors.append(f'{role}: family thread selector missing')
            else:
                page.locator('[data-chat]').first.click(); page.wait_for_timeout(20); chat_checks+=1
                if page.locator('#msgForm').count()!=1: errors.append(f'{role}: did not transition into talk thread')
                if page.locator('[data-chat-back]').count()!=1: errors.append(f'{role}: chat back button missing')
                if page.locator('[data-chat]').count()!=0: errors.append(f'{role}: family list still shown instead of thread')
        if role=='family':
            page.locator('button[data-view="talk"]').first.click(); page.wait_for_timeout(10); chat_checks+=1
            if page.locator('#msgForm').count()!=1: errors.append('family: talk form missing')
        if page_errors: errors.extend([f'{role}: pageerror {e}' for e in page_errors])
        page.close()
    browser.close()

report={'version':'20.3','roles_tested':len(roles),'ui_transitions':transitions,'chat_thread_checks':chat_checks,'errors':errors,'result':'PASS' if not errors else 'FAIL'}
print(json.dumps(report,ensure_ascii=False,indent=2))
(ROOT/'UI_TEST_RESULT_v20.3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if errors: raise SystemExit(1)
