import os, io, csv, json, base64, hashlib, hmac, secrets, urllib.request
from PIL import Image as PILImage
from pypdf import PdfReader, PdfWriter
from datetime import datetime, timedelta, timezone, date, time
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, LargeBinary, ForeignKey, UniqueConstraint, select, func
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, 'static')
DATA_DIR = os.path.join(ROOT, 'data')
os.makedirs(DATA_DIR, exist_ok=True)
JST = timezone(timedelta(hours=9))

# Supabase/PostgreSQL: set DATABASE_URL=postgresql+psycopg://...
DATABASE_URL = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(DATA_DIR, 'ittokai_v20.db')}")
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg://', 1)
if DATABASE_URL.startswith('postgresql://') and '+psycopg' not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

engine_kwargs = {'future': True, 'pool_pre_ping': True}
if DATABASE_URL.startswith('sqlite:'):
    engine_kwargs['connect_args'] = {'check_same_thread': False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def now_dt(): return datetime.now(JST).replace(tzinfo=None)
def now_iso(): return datetime.now(JST).isoformat(timespec='seconds')
def sha256_bytes(b: bytes): return hashlib.sha256(b).hexdigest()
def sha256_text(s: str): return hashlib.sha256((s or '').encode('utf-8')).hexdigest()


def hash_password(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, 160000)
    return base64.b64encode(salt).decode()+':' + base64.b64encode(dk).decode()

def verify_password(pw, stored):
    try:
        s,h=stored.split(':',1); salt=base64.b64decode(s); expected=base64.b64decode(h)
        got=hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, 160000)
        return hmac.compare_digest(got, expected)
    except Exception: return False

# ------------------ Models ------------------
class Facility(Base):
    __tablename__='facilities'
    id=Column(Integer, primary_key=True); code=Column(String(64), unique=True, index=True); name=Column(String(200), nullable=False)
    corporation=Column(String(200), default='社会福祉法人 一燈会'); address=Column(String(400), default=''); phone=Column(String(80), default=''); active=Column(Integer, default=1)

class Department(Base):
    __tablename__='departments'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, ForeignKey('facilities.id'), index=True); name=Column(String(160)); code=Column(String(64)); active=Column(Integer, default=1)
    __table_args__=(UniqueConstraint('facility_id','code', name='uq_department_code'),)

class User(Base):
    __tablename__='users'
    id=Column(Integer, primary_key=True); employee_code=Column(String(64), default=''); name=Column(String(160)); email=Column(String(240), unique=True, index=True); phone=Column(String(80), default='')
    password_hash=Column(Text); role=Column(String(40), index=True); facility_id=Column(Integer, ForeignKey('facilities.id'), nullable=True, index=True); department_id=Column(Integer, ForeignKey('departments.id'), nullable=True)
    line_user_id=Column(String(120), default=''); active=Column(Integer, default=1); created_at=Column(DateTime, default=now_dt)

class Resident(Base):
    __tablename__='residents'
    id=Column(Integer, primary_key=True); resident_code=Column(String(64), unique=True, index=True); facility_id=Column(Integer, ForeignKey('facilities.id'), index=True); name=Column(String(160)); service_type=Column(String(80), default='入所'); active=Column(Integer, default=1)

class FamilyLink(Base):
    __tablename__='family_links'
    id=Column(Integer, primary_key=True); user_id=Column(Integer, ForeignKey('users.id'), index=True); resident_id=Column(Integer, ForeignKey('residents.id'), index=True); relation=Column(String(80), default='家族'); is_primary=Column(Integer, default=0)
    __table_args__=(UniqueConstraint('user_id','resident_id', name='uq_family_resident'),)

class SessionToken(Base):
    __tablename__='sessions'
    token=Column(String(128), primary_key=True); user_id=Column(Integer, ForeignKey('users.id'), index=True); created_at=Column(DateTime, default=now_dt); expires_at=Column(DateTime)

class AuditLog(Base):
    __tablename__='audit_logs'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, nullable=True, index=True); actor_id=Column(Integer, nullable=True, index=True); actor_name=Column(String(160)); module=Column(String(80), index=True); action=Column(String(120)); entity_type=Column(String(80)); entity_id=Column(String(80)); metadata_json=Column(Text, default='{}'); ip=Column(String(100), default=''); user_agent=Column(Text, default=''); created_at=Column(DateTime, default=now_dt, index=True)

class Notification(Base):
    __tablename__='notifications'
    id=Column(Integer, primary_key=True); user_id=Column(Integer, ForeignKey('users.id'), index=True); title=Column(String(240)); body=Column(Text); module=Column(String(80)); entity_id=Column(String(80), default=''); read_at=Column(DateTime, nullable=True); created_at=Column(DateTime, default=now_dt)

class Message(Base):
    __tablename__='messages'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); family_user_id=Column(Integer, index=True); sender_id=Column(Integer, nullable=True); sender_name=Column(String(160)); sender_role=Column(String(40)); body=Column(Text); created_at=Column(DateTime, default=now_dt); read_at=Column(DateTime, nullable=True)

class News(Base):
    __tablename__='news'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); category=Column(String(80)); title=Column(String(240)); body=Column(Text); important=Column(Integer, default=0); image_url=Column(Text, default=''); created_at=Column(DateTime, default=now_dt)

# Documents v2
class Document(Base):
    __tablename__='documents'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); title=Column(String(300)); category=Column(String(100)); body=Column(Text, default=''); version=Column(Integer, default=1); status=Column(String(40), default='draft', index=True); due_at=Column(DateTime, nullable=True)
    requires_signature=Column(Integer, default=1); required_checks_json=Column(Text, default='["内容を確認しました"]'); file_name=Column(String(260), default=''); file_blob=Column(LargeBinary, nullable=True); original_hash=Column(String(64), default=''); created_by=Column(Integer); created_at=Column(DateTime, default=now_dt); sent_at=Column(DateTime, nullable=True); voided_at=Column(DateTime, nullable=True); previous_document_id=Column(Integer, nullable=True)

class DocumentRecipient(Base):
    __tablename__='document_recipients'
    id=Column(Integer, primary_key=True); document_id=Column(Integer, ForeignKey('documents.id'), index=True); user_id=Column(Integer, ForeignKey('users.id'), index=True); signer_role=Column(String(80), default='家族'); sign_order=Column(Integer, default=1); viewed_at=Column(DateTime, nullable=True); consent_at=Column(DateTime, nullable=True); signed_at=Column(DateTime, nullable=True); status=Column(String(40), default='sent')
    __table_args__=(UniqueConstraint('document_id','user_id', name='uq_document_recipient'),)

class DocumentSignature(Base):
    __tablename__='document_signatures'
    id=Column(Integer, primary_key=True); document_id=Column(Integer, index=True); recipient_id=Column(Integer, index=True); user_id=Column(Integer, index=True); signer_name=Column(String(160)); signature_data=Column(Text); signature_hash=Column(String(64)); ip=Column(String(100)); user_agent=Column(Text); created_at=Column(DateTime, default=now_dt)

# Staff workflow
class WorkflowRequest(Base):
    __tablename__='workflow_requests'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); department_id=Column(Integer, nullable=True); applicant_id=Column(Integer, index=True); request_type=Column(String(40), index=True); status=Column(String(40), default='pending_manager', index=True); request_date=Column(String(20)); start_time=Column(String(10), default=''); end_time=Column(String(10), default=''); payload_json=Column(Text, default='{}'); applicant_comment=Column(Text, default=''); manager_id=Column(Integer, nullable=True); admin_id=Column(Integer, nullable=True); created_at=Column(DateTime, default=now_dt); updated_at=Column(DateTime, default=now_dt); exported_at=Column(DateTime, nullable=True)

class WorkflowApproval(Base):
    __tablename__='workflow_approvals'
    id=Column(Integer, primary_key=True); request_id=Column(Integer, index=True); approver_id=Column(Integer); approver_role=Column(String(40)); action=Column(String(40)); comment=Column(Text, default=''); created_at=Column(DateTime, default=now_dt)

# Visit reservations
class VisitRule(Base):
    __tablename__='visit_rules'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); place_name=Column(String(120), default='面会室'); weekday=Column(Integer); start_time=Column(String(5)); end_time=Column(String(5)); slot_minutes=Column(Integer, default=30); capacity=Column(Integer, default=1); max_visitors=Column(Integer, default=4); booking_days_ahead=Column(Integer, default=30); cutoff_hours=Column(Integer, default=24); approval_mode=Column(String(20), default='auto'); active=Column(Integer, default=1)

class VisitBlock(Base):
    __tablename__='visit_blocks'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); block_date=Column(String(10), index=True); start_time=Column(String(5), default='00:00'); end_time=Column(String(5), default='23:59'); reason=Column(String(240), default='')

class VisitReservation(Base):
    __tablename__='visit_reservations'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); resident_id=Column(Integer, index=True); family_user_id=Column(Integer, index=True); visit_date=Column(String(10), index=True); start_time=Column(String(5)); end_time=Column(String(5)); place_name=Column(String(120)); visitor_count=Column(Integer, default=1); representative=Column(String(160)); phone=Column(String(80), default=''); notes=Column(Text, default=''); status=Column(String(40), default='confirmed'); checked_in_at=Column(DateTime, nullable=True); created_at=Column(DateTime, default=now_dt)

# CareDo procurement
class Supplier(Base):
    __tablename__='suppliers'
    id=Column(Integer, primary_key=True); supplier_type=Column(String(30), index=True); name=Column(String(200)); code=Column(String(64), unique=True); email=Column(String(240), default=''); phone=Column(String(80), default=''); site_url=Column(Text, default=''); order_url=Column(Text, default=''); active=Column(Integer, default=1)

class Product(Base):
    __tablename__='products'
    id=Column(Integer, primary_key=True); supplier_id=Column(Integer, ForeignKey('suppliers.id'), index=True); sku=Column(String(80), unique=True, index=True); name=Column(String(240)); specification=Column(String(240), default=''); category=Column(String(100)); unit=Column(String(40), default='個'); pack_size=Column(Integer, default=1); tax_rate=Column(Float, default=10.0); standard_price=Column(Float, default=0); min_order_qty=Column(Integer, default=1); lead_time_days=Column(Integer, default=2); substitute_sku=Column(String(80), default=''); inventory_managed=Column(Integer, default=1); active=Column(Integer, default=1)

class FacilityPrice(Base):
    __tablename__='facility_prices'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); product_id=Column(Integer, index=True); purchase_price=Column(Float, default=0); sale_price=Column(Float, default=0); effective_from=Column(String(10), default=''); effective_to=Column(String(10), default='')
    __table_args__=(UniqueConstraint('facility_id','product_id', name='uq_facility_product_price'),)

class Inventory(Base):
    __tablename__='inventory'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); product_id=Column(Integer, index=True); location=Column(String(120), default='主倉庫'); on_hand=Column(Float, default=0); safety_stock=Column(Float, default=0); reorder_point=Column(Float, default=0); target_stock=Column(Float, default=0); avg_daily_usage=Column(Float, default=0); updated_at=Column(DateTime, default=now_dt)
    __table_args__=(UniqueConstraint('facility_id','product_id','location', name='uq_inventory_location'),)

class InventoryTxn(Base):
    __tablename__='inventory_txns'
    id=Column(Integer, primary_key=True); facility_id=Column(Integer, index=True); product_id=Column(Integer, index=True); txn_type=Column(String(40)); qty=Column(Float); reference_type=Column(String(60), default=''); reference_id=Column(String(80), default=''); note=Column(Text, default=''); actor_id=Column(Integer, nullable=True); created_at=Column(DateTime, default=now_dt)

class PurchaseOrder(Base):
    __tablename__='purchase_orders'
    id=Column(Integer, primary_key=True); order_no=Column(String(80), unique=True, index=True); facility_id=Column(Integer, index=True); supplier_id=Column(Integer, index=True); status=Column(String(40), default='draft'); total_amount=Column(Float, default=0); approved_by=Column(Integer, nullable=True); ordered_at=Column(DateTime, nullable=True); confirmed_at=Column(DateTime, nullable=True); shipped_at=Column(DateTime, nullable=True); received_at=Column(DateTime, nullable=True); created_at=Column(DateTime, default=now_dt)

class PurchaseOrderItem(Base):
    __tablename__='purchase_order_items'
    id=Column(Integer, primary_key=True); order_id=Column(Integer, index=True); product_id=Column(Integer, index=True); qty=Column(Float); unit_price=Column(Float); received_qty=Column(Float, default=0)

class Invoice(Base):
    __tablename__='invoices'
    id=Column(Integer, primary_key=True); invoice_no=Column(String(80), unique=True, index=True); supplier_id=Column(Integer, index=True); facility_id=Column(Integer, index=True); order_id=Column(Integer, index=True); invoice_date=Column(String(10)); total_amount=Column(Float, default=0); pdf_blob=Column(LargeBinary, nullable=True); status=Column(String(40), default='received'); match_status=Column(String(40), default='unchecked'); difference_json=Column(Text, default='{}'); created_at=Column(DateTime, default=now_dt)

class InvoiceItem(Base):
    __tablename__='invoice_items'
    id=Column(Integer, primary_key=True); invoice_id=Column(Integer, index=True); product_id=Column(Integer, index=True); qty=Column(Float); unit_price=Column(Float); amount=Column(Float)

class IntegrationProfile(Base):
    __tablename__='integration_profiles'
    id=Column(Integer, primary_key=True); system_name=Column(String(80), unique=True); display_name=Column(String(160)); mode=Column(String(40), default='CSV'); direction=Column(String(40), default='bidirectional'); status=Column(String(40), default='template_ready'); notes=Column(Text, default='')

# ------------------ Helpers ------------------
ROLES = ['family','staff','middle_manager','admin','hq','caredo','sponsor']
ROLE_LABEL = {'family':'家族','staff':'一般職員','middle_manager':'中間管理職','admin':'施設管理者','hq':'法人本部','caredo':'ケア・ドゥ','sponsor':'外部協賛企業'}


def client_ip(request: Request):
    return (request.headers.get('x-forwarded-for') or request.client.host if request.client else '')[:100]

def get_token(request: Request):
    auth=request.headers.get('authorization','')
    if auth.lower().startswith('bearer '): return auth[7:].strip()
    return request.headers.get('x-session-token','')

def current_user(request: Request, s):
    token=get_token(request)
    if not token: raise HTTPException(401,'ログインが必要です')
    st=s.get(SessionToken, token)
    if not st or st.expires_at < now_dt(): raise HTTPException(401,'セッションが無効です')
    u=s.get(User, st.user_id)
    if not u or not u.active: raise HTTPException(401,'ユーザーが無効です')
    return u

def require_roles(u, *roles):
    if u.role not in roles: raise HTTPException(403,'権限がありません')

def facility_scope(u, facility_id):
    if u.role=='hq': return
    if u.role in ('caredo','sponsor'): return
    if u.facility_id != facility_id: raise HTTPException(403,'他施設のデータにはアクセスできません')

def audit(s, request, u, module, action, entity_type='', entity_id='', meta=None, facility_id=None):
    s.add(AuditLog(facility_id=facility_id or getattr(u,'facility_id',None), actor_id=getattr(u,'id',None), actor_name=getattr(u,'name','system'), module=module, action=action, entity_type=entity_type, entity_id=str(entity_id or ''), metadata_json=json.dumps(meta or {}, ensure_ascii=False), ip=client_ip(request), user_agent=request.headers.get('user-agent','')[:1000]))

def notify(s, user_id, title, body, module, entity_id=''):
    s.add(Notification(user_id=user_id,title=title,body=body,module=module,entity_id=str(entity_id or '')))
    # Optional LINE Messaging API. Link a LINE user id to User.line_user_id and set token.
    token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN','')
    if not token: return
    u=s.get(User,user_id)
    if not u or not u.line_user_id: return
    payload=json.dumps({'to':u.line_user_id,'messages':[{'type':'text','text':f'{title}\n{body}'}]},ensure_ascii=False).encode('utf-8')
    try:
        req=urllib.request.Request('https://api.line.me/v2/bot/message/push', data=payload, headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}, method='POST')
        urllib.request.urlopen(req, timeout=4).read()
    except Exception:
        pass

def user_json(u):
    return {'id':u.id,'name':u.name,'email':u.email,'role':u.role,'role_label':ROLE_LABEL.get(u.role,u.role),'facility_id':u.facility_id,'department_id':u.department_id,'employee_code':u.employee_code}

def facility_json(f): return {'id':f.id,'code':f.code,'name':f.name,'corporation':f.corporation,'address':f.address,'phone':f.phone}

def dt_iso(v): return v.isoformat(timespec='seconds') if v else None

# ------------------ Seed ------------------
def seed_data():
    with SessionLocal() as s:
        if s.query(Facility).count(): return
        fac=Facility(code='MAISON-NINOMIYA',name='メゾン・二宮',address='神奈川県中郡二宮町',phone='0463-00-0000'); s.add(fac); s.flush()
        deps=[]
        for code,name in [('ADMISSION','入所'),('DAY','デイサービス'),('SHORT','ショートステイ'),('ADMIN','事務')]:
            d=Department(facility_id=fac.id,code=code,name=name); s.add(d); deps.append(d)
        s.flush(); dep=deps[0]
        users=[
            User(name='相原 良太',email='family@ittokai.local',password_hash=hash_password('demo1234'),role='family',facility_id=fac.id),
            User(name='一般職員テスト',email='staff@ittokai.local',employee_code='E0001',password_hash=hash_password('staff1234'),role='staff',facility_id=fac.id,department_id=dep.id),
            User(name='中間管理職テスト',email='manager@ittokai.local',employee_code='M0001',password_hash=hash_password('manager1234'),role='middle_manager',facility_id=fac.id,department_id=dep.id),
            User(name='施設管理者',email='admin@ittokai.local',employee_code='A0001',password_hash=hash_password('admin1234'),role='admin',facility_id=fac.id,department_id=dep.id),
            User(name='法人本部',email='hq@ittokai.local',employee_code='HQ001',password_hash=hash_password('hq1234'),role='hq',facility_id=None),
            User(name='ケア・ドゥ担当',email='caredo@ittokai.local',password_hash=hash_password('caredo1234'),role='caredo',facility_id=None),
            User(name='協賛企業担当',email='sponsor@ittokai.local',password_hash=hash_password('sponsor1234'),role='sponsor',facility_id=None),
        ]
        s.add_all(users); s.flush(); family,staff,manager,admin,hq,caredo,sponsor=users
        res=Resident(resident_code='R0001',facility_id=fac.id,name='相原 太郎',service_type='入所'); s.add(res); s.flush(); s.add(FamilyLink(user_id=family.id,resident_id=res.id,relation='家族',is_primary=1))
        s.add_all([
            News(facility_id=fac.id,category='重要',title='面会についてのお知らせ',body='面会予約はITTOKAIからオンラインで行えます。',important=1,image_url='/assets/cards/news-important.svg'),
            News(facility_id=fac.id,category='施設だより',title='ITTOKAI統合版テスト開始',body='電子書類・職員申請・面会予約・在庫発注の統合テストを開始します。',important=0,image_url='/assets/cards/news-event.svg')
        ])
        s.add_all([
            Message(facility_id=fac.id,family_user_id=family.id,sender_id=admin.id,sender_name='メゾン・二宮',sender_role='admin',body='ITTOKAI統合版へようこそ。',read_at=now_dt()),
            Message(facility_id=fac.id,family_user_id=family.id,sender_id=family.id,sender_name=family.name,sender_role='family',body='よろしくお願いいたします。',read_at=now_dt())
        ])
        # Document sample
        doc=Document(facility_id=fac.id,title='写真・広報掲載に関する同意確認（テスト）',category='同意書',body='本書類は電子書類機能のテストです。内容を確認し、同意のうえ署名してください。',version=1,status='sent',due_at=now_dt()+timedelta(days=7),requires_signature=1,created_by=admin.id,sent_at=now_dt()); doc.original_hash=sha256_text(doc.title+doc.body); s.add(doc); s.flush(); s.add(DocumentRecipient(document_id=doc.id,user_id=family.id,signer_role='家族',sign_order=1,status='sent'))
        # Visit rules Monday-Sunday 14-17 30min
        for wd in range(7): s.add(VisitRule(facility_id=fac.id,place_name='面会室A',weekday=wd,start_time='14:00',end_time='17:00',slot_minutes=30,capacity=2,max_visitors=4,booking_days_ahead=30,cutoff_hours=24,approval_mode='auto'))
        # Suppliers/products/inventory
        sup=Supplier(supplier_type='caredo',name='株式会社ケア・ドゥ',code='CAREDO',site_url='https://caredo-zakka.jp/shop/',order_url='https://caredo-zakka.jp/shop/'); s.add(sup)
        sp=Supplier(supplier_type='sponsor',name='外部協賛企業A',code='SPONSOR-A',site_url='https://example.com',order_url='https://example.com'); s.add(sp); s.flush()
        products=[
            Product(supplier_id=sup.id,sku='CD-OM-M',name='リハビリパンツ M',specification='20枚',category='紙おむつ',unit='ケース',standard_price=2980,min_order_qty=1,lead_time_days=2),
            Product(supplier_id=sup.id,sku='CD-TISSUE',name='BOXティッシュ',specification='150組×5箱',category='日用品',unit='ケース',standard_price=1980,min_order_qty=1,lead_time_days=2),
            Product(supplier_id=sup.id,sku='CD-GLOVE',name='使い捨て手袋 M',specification='100枚',category='衛生',unit='箱',standard_price=780,min_order_qty=5,lead_time_days=2),
        ]; s.add_all(products); s.flush()
        for i,p in enumerate(products):
            s.add(FacilityPrice(facility_id=fac.id,product_id=p.id,purchase_price=p.standard_price*0.8,sale_price=p.standard_price))
            s.add(Inventory(facility_id=fac.id,product_id=p.id,on_hand=[2,8,3][i],safety_stock=[3,4,5][i],reorder_point=[4,5,6][i],target_stock=[8,10,12][i],avg_daily_usage=[0.3,0.2,0.5][i]))
        # Integration profiles
        s.add_all([
            IntegrationProfile(system_name='honobono',display_name='ほのぼの（介護・施設請求）',mode='CSV/API',direction='bidirectional',status='template_ready',notes='利用者・契約・請求・文書保存のCSV/APIアダプタ'),
            IntegrationProfile(system_name='chronos',display_name='クロノス（勤怠・給与）',mode='CSV/API',direction='bidirectional',status='template_ready',notes='職員・勤務・年休・残業・承認結果'),
            IntegrationProfile(system_name='yayoi',display_name='弥生（ケア・ドゥ販売／請求）',mode='CSV/API',direction='bidirectional',status='template_ready',notes='受注・売上・請求・入金・仕訳データ')
        ])
        s.commit()

# ------------------ PDF ------------------
def pdf_styles():
    try: pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
    except Exception: pass
    styles=getSampleStyleSheet(); font='HeiseiKakuGo-W5'
    return {
        'title':ParagraphStyle('jp_title',parent=styles['Title'],fontName=font,fontSize=16,leading=22,spaceAfter=8),
        'body':ParagraphStyle('jp_body',parent=styles['BodyText'],fontName=font,fontSize=9.5,leading=15),
        'small':ParagraphStyle('jp_small',parent=styles['BodyText'],fontName=font,fontSize=7.5,leading=11,textColor=colors.HexColor('#555555')),
    }

def make_document_pdf(s, doc: Document, rec: Optional[DocumentRecipient]=None):
    buf=io.BytesIO(); st=pdf_styles(); story=[]
    story.append(Paragraph(doc.title,st['title'])); story.append(Paragraph(f'文書ID: {doc.id} / 版: {doc.version} / 区分: {doc.category}',st['small'])); story.append(Spacer(1,5*mm))
    if doc.file_blob:
        story.append(Paragraph('原本PDFが添付されています。ITTOKAIでは署名証跡ページを付与して保存します。',st['body'])); story.append(Spacer(1,5*mm))
    for para in (doc.body or '').split('\n'):
        story.append(Paragraph(para or '　',st['body']))
    story.append(Spacer(1,8*mm)); story.append(Paragraph('電子署名・監査証跡',st['title']))
    recs=[rec] if rec else s.query(DocumentRecipient).filter_by(document_id=doc.id).order_by(DocumentRecipient.sign_order,DocumentRecipient.id).all()
    for idx,rr in enumerate(recs):
        u=s.get(User,rr.user_id); sig=s.query(DocumentSignature).filter_by(document_id=doc.id,recipient_id=rr.id).order_by(DocumentSignature.id.desc()).first()
        if idx: story.append(Spacer(1,6*mm))
        data=[['署名者',u.name if u else ''],['ステータス',rr.status],['閲覧日時',dt_iso(rr.viewed_at) or '-'],['同意日時',dt_iso(rr.consent_at) or '-'],['署名日時',dt_iso(rr.signed_at) or '-'],['原本SHA-256',doc.original_hash or '-']]
        if sig: data += [['署名SHA-256',sig.signature_hash],['IP',sig.ip],['User-Agent',sig.user_agent[:80]]]
        t=Table(data,colWidths=[35*mm,145*mm]); t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'HeiseiKakuGo-W5'),('FONTSIZE',(0,0),(-1,-1),7.5),('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#dddddd')),('BACKGROUND',(0,0),(0,-1),colors.HexColor('#fff3e8')),('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),4)])); story.append(t)
        if sig and sig.signature_data and ',' in sig.signature_data:
            try:
                raw=base64.b64decode(sig.signature_data.split(',',1)[1]); bio=io.BytesIO(raw); PILImage.open(bio).verify(); bio.seek(0); story.append(Spacer(1,5*mm)); story.append(Paragraph('手書きサイン',st['body'])); story.append(RLImage(bio,width=55*mm,height=22*mm))
            except Exception: pass
    SimpleDocTemplate(buf,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm).build(story); buf.seek(0); evidence=buf.getvalue()
    if doc.file_blob and bytes(doc.file_blob).startswith(b'%PDF'):
        try:
            writer=PdfWriter()
            for page in PdfReader(io.BytesIO(bytes(doc.file_blob))).pages: writer.add_page(page)
            for page in PdfReader(io.BytesIO(evidence)).pages: writer.add_page(page)
            merged=io.BytesIO(); writer.write(merged); return merged.getvalue()
        except Exception:
            return evidence
    return evidence

# ------------------ App ------------------
app=FastAPI(title='ITTOKAI v20.3 Integrated',version='20.3')

@app.middleware('http')
async def no_store_api_responses(request:Request, call_next):
    response=await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma']='no-cache'
    return response

Base.metadata.create_all(bind=engine); seed_data()

@app.get('/health')
def health(): return {'ok':True,'version':'20.3','database':'postgresql' if DATABASE_URL.startswith('postgresql') else 'sqlite'}

class LoginIn(BaseModel): email:str; password:str
@app.post('/api/login')
def login(inp:LoginIn, request:Request):
    with SessionLocal() as s:
        u=s.query(User).filter(func.lower(User.email)==inp.email.lower()).first()
        if not u or not verify_password(inp.password,u.password_hash): raise HTTPException(401,'IDまたはパスワードが違います')
        token=secrets.token_urlsafe(32); s.add(SessionToken(token=token,user_id=u.id,expires_at=now_dt()+timedelta(days=30))); audit(s,request,u,'auth','login','user',u.id); s.commit(); return {'token':token,'user':user_json(u)}

@app.post('/api/logout')
def logout(request:Request):
    with SessionLocal() as s:
        token=get_token(request); st=s.get(SessionToken,token)
        if st: s.delete(st); s.commit()
    return {'ok':True}

def document_revision_value(s,u):
    """Return a lightweight revision number for document-related changes visible to the user.

    AuditLog IDs are monotonic and every document send/view/sign/remind/reissue action creates a log.
    Using a facility-scoped max ID lets clients detect remote changes without reloading the entire app.
    """
    q=s.query(func.max(AuditLog.id)).filter(AuditLog.module=='documents')
    if u.role!='hq':
        if not u.facility_id:
            return 0
        q=q.filter(AuditLog.facility_id==u.facility_id)
    return int(q.scalar() or 0)

@app.get('/api/documents/revision')
def document_revision(request:Request):
    with SessionLocal() as s:
        u=current_user(request,s)
        if u.role not in ('family','admin','hq'):
            raise HTTPException(403,'電子書類の同期権限がありません')
        return Response(
            content=json.dumps({'revision':document_revision_value(s,u)}, ensure_ascii=False),
            media_type='application/json',
            headers={'Cache-Control':'no-store, no-cache, must-revalidate, max-age=0','Pragma':'no-cache'}
        )

SYNC_ALLOWED = {
    'family': {'documents','chat','visits','news','all'},
    'staff': {'chat','workflow','visits','news','all'},
    'middle_manager': {'chat','workflow','visits','news','procurement','all'},
    'admin': {'documents','chat','workflow','visits','news','procurement','all'},
    'hq': {'documents','workflow','visits','news','procurement','all'},
    'caredo': {'procurement','all'},
    'sponsor': set(),
}

def module_revision_value(s,u,module):
    if module not in SYNC_ALLOWED.get(u.role,set()):
        raise HTTPException(403,'同期権限がありません')
    q=s.query(func.max(AuditLog.id))
    if module!='all': q=q.filter(AuditLog.module==module)
    # HQ is corporation-wide. CareDo sees procurement across all facilities.
    if u.role=='caredo':
        q=q.filter(AuditLog.module=='procurement')
    elif u.role!='hq':
        if not u.facility_id: return 0
        q=q.filter(AuditLog.facility_id==u.facility_id)
    return int(q.scalar() or 0)

@app.get('/api/sync/revision')
def sync_revision(request:Request,module:str='all'):
    with SessionLocal() as s:
        u=current_user(request,s)
        return {'module':module,'revision':module_revision_value(s,u,module)}

def chat_target(s,u,user_id=None):
    require_roles(u,'family','staff','middle_manager','admin')
    target=u.id if u.role=='family' else int(user_id or 0)
    if not target: raise HTTPException(400,'相手を選択してください')
    tu=s.get(User,target)
    if not tu or tu.role!='family' or not tu.active: raise HTTPException(404,'家族アカウントがありません')
    facility_scope(u,tu.facility_id)
    return target,tu

def chat_revision_value(s,u,user_id=None):
    require_roles(u,'family','staff','middle_manager','admin')
    if u.role!='family' and not user_id:
        q=s.query(Message).filter_by(facility_id=u.facility_id)
    else:
        target,tu=chat_target(s,u,user_id)
        q=s.query(Message).filter_by(family_user_id=target,facility_id=tu.facility_id)
    max_id=int(q.with_entities(func.max(Message.id)).scalar() or 0)
    read_count=int(q.filter(Message.read_at.is_not(None)).count())
    return f'{max_id}:{read_count}'

@app.get('/api/messages/revision')
def messages_revision(request:Request,user_id:Optional[int]=None):
    with SessionLocal() as s:
        u=current_user(request,s)
        return {'revision':chat_revision_value(s,u,user_id)}

@app.get('/api/bootstrap')
def bootstrap(request:Request):
    with SessionLocal() as s:
        u=current_user(request,s)
        fac=s.get(Facility,u.facility_id) if u.facility_id else None
        data={'user':user_json(u),'facility':facility_json(fac) if fac else None,'role_labels':ROLE_LABEL,'version':'20.3','targets':{'facilities':50,'staff':1000,'middle_managers':200,'admins':50,'families':2000,'sponsors':100}}
        if u.role in ('family','admin','hq'): data['document_revision']=document_revision_value(s,u)
        data['notifications']=[{'id':n.id,'title':n.title,'body':n.body,'module':n.module,'entity_id':n.entity_id,'created_at':dt_iso(n.created_at),'read_at':dt_iso(n.read_at)} for n in s.query(Notification).filter_by(user_id=u.id).order_by(Notification.id.desc()).limit(30).all()]
        if u.role=='family':
            links=s.query(FamilyLink,Resident).join(Resident,FamilyLink.resident_id==Resident.id).filter(FamilyLink.user_id==u.id).all(); resident_ids=[r.id for _,r in links]
            data['residents']=[{'id':r.id,'name':r.name,'facility_id':r.facility_id,'service_type':r.service_type,'relation':l.relation} for l,r in links]
            data['news']=[{'id':n.id,'category':n.category,'title':n.title,'body':n.body,'important':n.important,'image_url':n.image_url,'created_at':dt_iso(n.created_at)} for n in s.query(News).filter_by(facility_id=u.facility_id).order_by(News.id.desc()).limit(30)]
            data['documents']=document_list_for_user(s,u)
            data['visits']=visit_list_for_user(s,u)
            data['messages']=messages_for_family(s,u.id,u.facility_id)
        elif u.role in ('staff','middle_manager','admin'):
            data['news']=[{'id':n.id,'category':n.category,'title':n.title,'body':n.body,'important':n.important,'image_url':n.image_url,'created_at':dt_iso(n.created_at)} for n in s.query(News).filter_by(facility_id=u.facility_id).order_by(News.id.desc()).limit(30)]
            data['family_users']=family_users_for_facility(s,u.facility_id)
            data['my_requests']=workflow_list(s,u,own=True)
            data['visits']=visit_list_for_facility(s,u.facility_id)
            if u.role in ('middle_manager','admin'): data['approval_queue']=workflow_list(s,u,approval=True)
            if u.role=='admin':
                data['documents']=document_list_for_facility(s,u.facility_id); data['visit_rules']=visit_rules_for_facility(s,u.facility_id); data['procurement']=procurement_snapshot(s,u.facility_id)
        elif u.role=='hq':
            data['dashboard']=hq_dashboard(s); data['facilities']=[facility_json(f) for f in s.query(Facility).filter_by(active=1).all()]; data['integrations']=integration_list(s)
        elif u.role=='caredo':
            data['caredo']=caredo_snapshot(s)
        elif u.role=='sponsor':
            data['sponsor']={'message':'外部協賛企業ポータル。利用者個人情報・介護情報は表示しません。','shop_url':'https://caredo-zakka.jp/shop/'}
        data['sync_revisions']={m:module_revision_value(s,u,m) for m in SYNC_ALLOWED.get(u.role,set()) if m!='chat'}
        return data

# -------- chat/news --------
def family_users_for_facility(s,fid): return [{'id':x.id,'name':x.name,'email':x.email} for x in s.query(User).filter_by(role='family',facility_id=fid,active=1).all()]
def messages_for_family(s,uid,fid): return [{'id':m.id,'sender_id':m.sender_id,'sender_name':m.sender_name,'sender_role':m.sender_role,'body':m.body,'created_at':dt_iso(m.created_at),'read_at':dt_iso(m.read_at)} for m in s.query(Message).filter_by(family_user_id=uid,facility_id=fid).order_by(Message.id.asc()).all()]

@app.get('/api/messages')
def get_messages(request:Request,user_id:Optional[int]=None):
    with SessionLocal() as s:
        u=current_user(request,s); target,tu=chat_target(s,u,user_id)
        changed=False
        for m in s.query(Message).filter_by(family_user_id=target,facility_id=tu.facility_id).all():
            if m.sender_id!=u.id and not m.read_at:
                m.read_at=now_dt(); changed=True
        if changed:
            audit(s,request,u,'chat','read','message_thread',target,{'target':target},tu.facility_id)
            s.commit()
        return {'messages':messages_for_family(s,target,tu.facility_id),'revision':chat_revision_value(s,u,target if u.role!='family' else None)}

class MsgIn(BaseModel): body:str; user_id:Optional[int]=None
@app.post('/api/messages')
def post_message(inp:MsgIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); target,tu=chat_target(s,u,inp.user_id)
        body=inp.body.strip()
        if not body: raise HTTPException(400,'メッセージを入力してください')
        if len(body)>4000: raise HTTPException(400,'メッセージは4000文字以内にしてください')
        m=Message(facility_id=tu.facility_id,family_user_id=target,sender_id=u.id,sender_name=u.name,sender_role=u.role,body=body); s.add(m); s.flush()
        if u.role=='family':
            recipients=s.query(User).filter(User.facility_id==tu.facility_id,User.role.in_(['middle_manager','admin']),User.active==1).all()
            for x in recipients: notify(s,x.id,'新着トーク',body[:80],'chat',target)
        else:
            notify(s,target,'施設から新着トークがあります',body[:80],'chat',target)
        audit(s,request,u,'chat','send','message',m.id,{'target':target},tu.facility_id); s.commit(); return {'ok':True,'id':m.id}

@app.post('/api/messages/read')
def read_messages(inp:dict,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); target,tu=chat_target(s,u,inp.get('user_id'))
        changed=False
        for m in s.query(Message).filter_by(family_user_id=target,facility_id=tu.facility_id).all():
            if m.sender_id!=u.id and not m.read_at:
                m.read_at=now_dt(); changed=True
        if changed:
            audit(s,request,u,'chat','read','message_thread',target,{'target':target},tu.facility_id)
            s.commit()
        return {'ok':True}


class NewsIn(BaseModel):
    category:str='お知らせ'; title:str; body:str; important:bool=False; image_url:str=''
@app.post('/api/news')
def create_news(inp:NewsIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq'); fid=u.facility_id or 1
        n=News(facility_id=fid,category=inp.category,title=inp.title,body=inp.body,important=1 if inp.important else 0,image_url=inp.image_url); s.add(n); s.flush()
        for fam in s.query(User).filter_by(facility_id=fid,role='family',active=1).all(): notify(s,fam.id,'施設からのお知らせ',inp.title,'news',n.id)
        audit(s,request,u,'news','publish','news',n.id,{},fid); s.commit(); return {'id':n.id,'ok':True}

# -------- documents --------
def document_list_for_user(s,u):
    rows=s.query(DocumentRecipient,Document).join(Document,DocumentRecipient.document_id==Document.id).filter(DocumentRecipient.user_id==u.id).order_by(Document.id.desc()).all()
    return [doc_json(d,r) for r,d in rows]
def document_list_for_facility(s,fid):
    rows=s.query(DocumentRecipient,Document,User).join(Document,DocumentRecipient.document_id==Document.id).join(User,DocumentRecipient.user_id==User.id).filter(Document.facility_id==fid).order_by(Document.id.desc()).all()
    return [dict(doc_json(d,r),recipient_name=u.name,recipient_user_id=u.id) for r,d,u in rows]
def doc_json(d,r=None):
    return {'id':d.id,'facility_id':d.facility_id,'title':d.title,'category':d.category,'body':d.body,'version':d.version,'status':r.status if r else d.status,'due_at':dt_iso(d.due_at),'requires_signature':d.requires_signature,'file_name':d.file_name,'sent_at':dt_iso(d.sent_at),'viewed_at':dt_iso(r.viewed_at) if r else None,'consent_at':dt_iso(r.consent_at) if r else None,'signed_at':dt_iso(r.signed_at) if r else None}

class DocumentCreate(BaseModel): title:str; category:str='書類'; body:str=''; recipient_user_ids:list[int]; due_days:int=7; requires_signature:bool=True; required_checks:list[str]=['内容を確認しました']
@app.post('/api/documents')
def create_document(inp:DocumentCreate,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq'); fid=u.facility_id or 1
        d=Document(facility_id=fid,title=inp.title,category=inp.category,body=inp.body,status='sent',due_at=now_dt()+timedelta(days=max(1,inp.due_days)),requires_signature=1 if inp.requires_signature else 0,required_checks_json=json.dumps(inp.required_checks,ensure_ascii=False),created_by=u.id,sent_at=now_dt()); d.original_hash=sha256_text(d.title+d.body+now_iso()); s.add(d); s.flush()
        for uid in inp.recipient_user_ids:
            ru=s.get(User,uid)
            if not ru or ru.role!='family' or ru.facility_id!=fid: continue
            s.add(DocumentRecipient(document_id=d.id,user_id=uid,signer_role='家族',sign_order=1,status='sent')); notify(s,uid,'新しい書類があります',d.title,'documents',d.id)
        audit(s,request,u,'documents','create_send','document',d.id,{'recipients':inp.recipient_user_ids},fid); s.commit(); return {'id':d.id,'ok':True}

@app.post('/api/documents/upload')
async def upload_document(request:Request,title:str=Form(...),category:str=Form('契約書'),recipient_user_ids:str=Form(...),due_days:int=Form(7),file:UploadFile=File(...)):
    data=await file.read()
    if len(data)>12*1024*1024: raise HTTPException(400,'PDFは12MB以下にしてください')
    if not data.startswith(b'%PDF'): raise HTTPException(400,'PDF形式のファイルを選択してください')
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq'); fid=u.facility_id or 1
        try: ids=[int(x) for x in recipient_user_ids.split(',') if x.strip()]
        except Exception: ids=[]
        if not ids: raise HTTPException(400,'送付先が必要です')
        d=Document(facility_id=fid,title=title,category=category,body='',status='sent',due_at=now_dt()+timedelta(days=due_days),requires_signature=1,file_name=file.filename or 'document.pdf',file_blob=data,original_hash=sha256_bytes(data),created_by=u.id,sent_at=now_dt()); s.add(d); s.flush()
        order=1
        for uid in ids:
            ru=s.get(User,uid)
            if not ru or ru.facility_id!=fid or ru.role!='family': continue
            s.add(DocumentRecipient(document_id=d.id,user_id=uid,signer_role='家族',sign_order=order,status='sent')); notify(s,uid,'新しい契約書があります',title,'documents',d.id); order+=1
        audit(s,request,u,'documents','upload_send','document',d.id,{'file':file.filename,'recipients':ids},fid); s.commit(); return {'id':d.id,'ok':True}

@app.post('/api/documents/{doc_id}/view')
def view_document(doc_id:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); d=s.get(Document,doc_id)
        if not d: raise HTTPException(404,'書類がありません')
        r=s.query(DocumentRecipient).filter_by(document_id=doc_id,user_id=u.id).first()
        if not r:
            require_roles(u,'admin','hq'); facility_scope(u,d.facility_id)
        if r and not r.viewed_at:
            r.viewed_at=now_dt(); r.status='viewed'; audit(s,request,u,'documents','view','document',doc_id,facility_id=d.facility_id); s.commit()
        return {'ok':True}

class SignIn(BaseModel): signer_name:str; signature_data:str; consent:bool=True
@app.post('/api/documents/{doc_id}/sign')
def sign_document(doc_id:int,inp:SignIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); r=s.query(DocumentRecipient).filter_by(document_id=doc_id,user_id=u.id).first(); d=s.get(Document,doc_id)
        if not r or not d: raise HTTPException(404,'書類がありません')
        if r.signed_at: raise HTTPException(400,'署名済みです')
        if not inp.consent: raise HTTPException(400,'同意が必要です')
        sig_hash=sha256_text(inp.signature_data); sig=DocumentSignature(document_id=doc_id,recipient_id=r.id,user_id=u.id,signer_name=inp.signer_name,signature_data=inp.signature_data,signature_hash=sig_hash,ip=client_ip(request),user_agent=request.headers.get('user-agent','')); s.add(sig); r.consent_at=now_dt(); r.signed_at=now_dt(); r.status='signed'; s.flush(); remaining=s.query(DocumentRecipient).filter(DocumentRecipient.document_id==doc_id,DocumentRecipient.signed_at.is_(None)).count(); d.status='signed' if remaining==0 else 'partial_signed'; audit(s,request,u,'documents','sign','document',doc_id,{'signature_hash':sig_hash});
        admins=s.query(User).filter_by(facility_id=d.facility_id,role='admin',active=1).all()
        for a in admins: notify(s,a.id,'書類の署名が完了しました',d.title,'documents',doc_id)
        s.commit(); return {'ok':True}

@app.get('/api/documents/{doc_id}/original')
def original_document(doc_id:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); d=s.get(Document,doc_id)
        if not d or not d.file_blob: raise HTTPException(404,'原本PDFがありません')
        r=s.query(DocumentRecipient).filter_by(document_id=doc_id,user_id=u.id).first()
        if not r:
            require_roles(u,'admin','hq'); facility_scope(u,d.facility_id)
        return Response(content=bytes(d.file_blob),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="original_{doc_id}.pdf"'})

class ReissueIn(BaseModel):
    title:Optional[str]=None; body:Optional[str]=None; due_days:int=7
@app.post('/api/documents/{doc_id}/reissue')
def reissue_document(doc_id:int,inp:ReissueIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq'); old=s.get(Document,doc_id)
        if not old: raise HTTPException(404,'書類がありません')
        facility_scope(u,old.facility_id)
        d=Document(facility_id=old.facility_id,title=inp.title or old.title,category=old.category,body=inp.body if inp.body is not None else old.body,version=old.version+1,status='sent',due_at=now_dt()+timedelta(days=inp.due_days),requires_signature=old.requires_signature,required_checks_json=old.required_checks_json,file_name=old.file_name,file_blob=old.file_blob,original_hash=old.original_hash,created_by=u.id,sent_at=now_dt(),previous_document_id=old.id); s.add(d); s.flush()
        for idx,r in enumerate(s.query(DocumentRecipient).filter_by(document_id=old.id).order_by(DocumentRecipient.sign_order).all(),1):
            s.add(DocumentRecipient(document_id=d.id,user_id=r.user_id,signer_role=r.signer_role,sign_order=idx,status='sent')); notify(s,r.user_id,'書類が再発行されました',d.title,'documents',d.id)
        old.status='superseded'; audit(s,request,u,'documents','reissue','document',d.id,{'previous':old.id},old.facility_id); s.commit(); return {'id':d.id,'version':d.version,'ok':True}

@app.post('/api/documents/{doc_id}/remind')
def remind_document(doc_id:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq'); d=s.get(Document,doc_id)
        if not d: raise HTTPException(404,'書類がありません')
        facility_scope(u,d.facility_id)
        n=0
        for r in s.query(DocumentRecipient).filter_by(document_id=d.id).all():
            if not r.signed_at: notify(s,r.user_id,'書類の確認をお願いします',d.title,'documents',d.id); n+=1
        audit(s,request,u,'documents','remind','document',d.id,{'count':n},d.facility_id); s.commit(); return {'ok':True,'count':n}

@app.get('/api/documents/{doc_id}/pdf')
def signed_pdf(doc_id:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); d=s.get(Document,doc_id)
        if not d: raise HTTPException(404,'書類がありません')
        r=s.query(DocumentRecipient).filter_by(document_id=doc_id,user_id=u.id).first()
        if not r:
            require_roles(u,'admin','hq'); facility_scope(u,d.facility_id)
        pdf=make_document_pdf(s,d,r); return Response(content=pdf,media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="ITTOKAI_document_{doc_id}.pdf"'})

# -------- workflow --------
def workflow_json(s,w):
    applicant=s.get(User,w.applicant_id); return {'id':w.id,'request_type':w.request_type,'status':w.status,'request_date':w.request_date,'start_time':w.start_time,'end_time':w.end_time,'payload':json.loads(w.payload_json or '{}'),'comment':w.applicant_comment,'applicant_id':w.applicant_id,'applicant_name':applicant.name if applicant else '','created_at':dt_iso(w.created_at),'updated_at':dt_iso(w.updated_at)}
def workflow_list(s,u,own=False,approval=False):
    q=s.query(WorkflowRequest)
    if own: q=q.filter(WorkflowRequest.applicant_id==u.id)
    elif approval:
        q=q.filter(WorkflowRequest.facility_id==u.facility_id)
        if u.role=='middle_manager':
            q=q.filter(WorkflowRequest.status=='pending_manager')
            if u.department_id: q=q.filter(WorkflowRequest.department_id==u.department_id)
        elif u.role=='admin': q=q.filter(WorkflowRequest.status.in_(['pending_admin','pending_manager']))
    return [workflow_json(s,w) for w in q.order_by(WorkflowRequest.id.desc()).limit(100)]

class WorkflowIn(BaseModel): request_type:str; request_date:str; start_time:str=''; end_time:str=''; payload:dict={}; comment:str=''
@app.post('/api/workflows')
def create_workflow(inp:WorkflowIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'staff','middle_manager','admin')
        status='pending_manager' if u.role=='staff' else ('pending_admin' if u.role=='middle_manager' else 'approved')
        w=WorkflowRequest(facility_id=u.facility_id,department_id=u.department_id,applicant_id=u.id,request_type=inp.request_type,status=status,request_date=inp.request_date,start_time=inp.start_time,end_time=inp.end_time,payload_json=json.dumps(inp.payload,ensure_ascii=False),applicant_comment=inp.comment); s.add(w); s.flush(); audit(s,request,u,'workflow','submit','workflow_request',w.id,{'type':inp.request_type},u.facility_id)
        approvers=s.query(User).filter(User.facility_id==u.facility_id,User.role.in_(['middle_manager','admin']),User.active==1).all()
        for a in approvers:
            if a.role=='middle_manager' and u.department_id and a.department_id!=u.department_id: continue
            notify(s,a.id,'職員申請があります',f'{u.name}：{inp.request_type}','workflow',w.id)
        s.commit(); return {'id':w.id,'status':w.status}

class ApprovalIn(BaseModel): action:str; comment:str=''
@app.post('/api/workflows/{rid}/action')
def workflow_action(rid:int,inp:ApprovalIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'middle_manager','admin'); w=s.get(WorkflowRequest,rid)
        if not w: raise HTTPException(404,'申請がありません')
        facility_scope(u,w.facility_id)
        if u.role=='middle_manager' and u.department_id and w.department_id!=u.department_id: raise HTTPException(403,'他部署の申請は承認できません')
        if w.applicant_id==u.id: raise HTTPException(400,'自分の申請は承認できません')
        if w.status not in ('pending_manager','pending_admin'): raise HTTPException(400,'この申請はすでに処理済みです')
        if u.role=='middle_manager' and w.status!='pending_manager': raise HTTPException(400,'中間管理職の承認対象ではありません')
        if inp.action not in ('approve','reject','return'): raise HTTPException(400,'操作が不正です')
        if inp.action in ('reject','return') and not inp.comment.strip(): raise HTTPException(400,'否認・差戻しはコメント必須です')
        if inp.action=='approve':
            if u.role=='middle_manager': w.status='pending_admin'; w.manager_id=u.id
            else: w.status='approved'; w.admin_id=u.id
        elif inp.action=='reject': w.status='rejected'
        else: w.status='returned'
        w.updated_at=now_dt(); s.add(WorkflowApproval(request_id=w.id,approver_id=u.id,approver_role=u.role,action=inp.action,comment=inp.comment)); notify(s,w.applicant_id,'申請結果が更新されました',f'{w.request_type}：{w.status}','workflow',w.id); audit(s,request,u,'workflow',inp.action,'workflow_request',w.id,{'comment':inp.comment},w.facility_id); s.commit(); return {'ok':True,'status':w.status}

# -------- visits --------
def visit_rules_for_facility(s,fid): return [{'id':r.id,'place_name':r.place_name,'weekday':r.weekday,'start_time':r.start_time,'end_time':r.end_time,'slot_minutes':r.slot_minutes,'capacity':r.capacity,'max_visitors':r.max_visitors,'booking_days_ahead':r.booking_days_ahead,'cutoff_hours':r.cutoff_hours,'approval_mode':r.approval_mode,'active':r.active} for r in s.query(VisitRule).filter_by(facility_id=fid).all()]
def visit_json(s,v):
    r=s.get(Resident,v.resident_id); u=s.get(User,v.family_user_id); return {'id':v.id,'facility_id':v.facility_id,'resident_id':v.resident_id,'resident_name':r.name if r else '','family_user_id':v.family_user_id,'family_name':u.name if u else '','visit_date':v.visit_date,'start_time':v.start_time,'end_time':v.end_time,'place_name':v.place_name,'visitor_count':v.visitor_count,'representative':v.representative,'phone':v.phone,'notes':v.notes,'status':v.status,'checked_in_at':dt_iso(v.checked_in_at)}
def visit_list_for_user(s,u): return [visit_json(s,v) for v in s.query(VisitReservation).filter_by(family_user_id=u.id).order_by(VisitReservation.visit_date.desc()).limit(100)]
def visit_list_for_facility(s,fid): return [visit_json(s,v) for v in s.query(VisitReservation).filter_by(facility_id=fid).order_by(VisitReservation.visit_date.desc()).limit(200)]

@app.get('/api/visits/availability')
def visit_availability(request:Request,facility_id:int,visit_date:str):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'family','staff','middle_manager','admin','hq'); facility_scope(u,facility_id)
        try: d=date.fromisoformat(visit_date)
        except ValueError: raise HTTPException(400,'日付が不正です')
        if d < datetime.now(JST).date(): raise HTTPException(400,'過去の日付は予約できません')
        rules=s.query(VisitRule).filter_by(facility_id=facility_id,weekday=d.weekday(),active=1).all(); slots=[]
        blocks=s.query(VisitBlock).filter_by(facility_id=facility_id,block_date=visit_date).all()
        for r in rules:
            sh,sm=map(int,r.start_time.split(':')); eh,em=map(int,r.end_time.split(':')); cur=datetime.combine(d,time(sh,sm)); end=datetime.combine(d,time(eh,em))
            while cur+timedelta(minutes=r.slot_minutes)<=end:
                st=cur.strftime('%H:%M'); et=(cur+timedelta(minutes=r.slot_minutes)).strftime('%H:%M'); blocked=any(not (et<=b.start_time or st>=b.end_time) for b in blocks)
                # Apply booking horizon/cutoff server-side.
                days_ahead=(d-datetime.now(JST).date()).days
                cutoff_at=datetime.combine(d,time(sh,sm),tzinfo=JST)-timedelta(hours=r.cutoff_hours)
                outside=days_ahead>r.booking_days_ahead or datetime.now(JST)>cutoff_at
                count=s.query(VisitReservation).filter_by(facility_id=facility_id,visit_date=visit_date,start_time=st,place_name=r.place_name).filter(VisitReservation.status.in_(['confirmed','pending'])).count()
                slots.append({'place_name':r.place_name,'start_time':st,'end_time':et,'capacity':r.capacity,'remaining':0 if blocked or outside else max(0,r.capacity-count),'approval_mode':r.approval_mode,'max_visitors':r.max_visitors}); cur+=timedelta(minutes=r.slot_minutes)
        return {'date':visit_date,'slots':slots}

class VisitIn(BaseModel): resident_id:int; visit_date:str; start_time:str; end_time:str; place_name:str; visitor_count:int=1; representative:str; phone:str=''; notes:str=''
@app.post('/api/visits')
def create_visit(inp:VisitIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'family'); res=s.get(Resident,inp.resident_id)
        if not res: raise HTTPException(404,'利用者がいません')
        link=s.query(FamilyLink).filter_by(user_id=u.id,resident_id=res.id).first()
        if not link: raise HTTPException(403,'この利用者の予約権限がありません')
        avail=visit_availability(request,res.facility_id,inp.visit_date)['slots']; slot=next((x for x in avail if x['start_time']==inp.start_time and x['place_name']==inp.place_name),None)
        if not slot or slot['remaining']<=0: raise HTTPException(400,'この時間枠は予約できません')
        if inp.visitor_count<1 or inp.visitor_count>int(slot.get('max_visitors') or 4): raise HTTPException(400,'来訪人数が上限を超えています')
        if not inp.representative.strip(): raise HTTPException(400,'来訪代表者名が必要です')
        status='confirmed' if slot['approval_mode']=='auto' else 'pending'; v=VisitReservation(facility_id=res.facility_id,resident_id=res.id,family_user_id=u.id,visit_date=inp.visit_date,start_time=inp.start_time,end_time=slot['end_time'],place_name=inp.place_name,visitor_count=inp.visitor_count,representative=inp.representative.strip(),phone=inp.phone,notes=inp.notes,status=status); s.add(v); s.flush(); audit(s,request,u,'visits','book','visit',v.id,{},res.facility_id); s.commit(); return {'id':v.id,'status':status}

@app.post('/api/visits/{vid}/cancel')
def cancel_visit(vid:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'family','staff','middle_manager','admin','hq'); v=s.get(VisitReservation,vid)
        if not v: raise HTTPException(404,'予約がありません')
        if u.role=='family' and v.family_user_id!=u.id: raise HTTPException(403,'権限がありません')
        facility_scope(u,v.facility_id); v.status='cancelled'; audit(s,request,u,'visits','cancel','visit',vid,{},v.facility_id); s.commit(); return {'ok':True}


class VisitRuleIn(BaseModel):
    place_name:str='面会室A'; weekday:int; start_time:str='14:00'; end_time:str='17:00'; slot_minutes:int=30; capacity:int=1; max_visitors:int=4; booking_days_ahead:int=30; cutoff_hours:int=24; approval_mode:str='auto'
@app.post('/api/visit-rules')
def create_visit_rule(inp:VisitRuleIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin'); r=VisitRule(facility_id=u.facility_id,**inp.model_dump()); s.add(r); s.flush(); audit(s,request,u,'visits','rule_create','visit_rule',r.id,inp.model_dump(),u.facility_id); s.commit(); return {'id':r.id,'ok':True}

@app.delete('/api/visit-rules/{rid}')
def delete_visit_rule(rid:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin'); r=s.get(VisitRule,rid)
        if not r or r.facility_id!=u.facility_id: raise HTTPException(404,'設定がありません')
        s.delete(r); audit(s,request,u,'visits','rule_delete','visit_rule',rid,{},u.facility_id); s.commit(); return {'ok':True}

class VisitBlockIn(BaseModel):
    block_date:str; start_time:str='00:00'; end_time:str='23:59'; reason:str=''
@app.post('/api/visit-blocks')
def create_visit_block(inp:VisitBlockIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin'); b=VisitBlock(facility_id=u.facility_id,**inp.model_dump()); s.add(b); s.flush(); audit(s,request,u,'visits','block_create','visit_block',b.id,inp.model_dump(),u.facility_id); s.commit(); return {'id':b.id,'ok':True}

class ProxyVisitIn(VisitIn):
    family_user_id:int
@app.post('/api/visits/proxy')
def proxy_visit(inp:ProxyVisitIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin'); res=s.get(Resident,inp.resident_id); fam=s.get(User,inp.family_user_id)
        if not res or res.facility_id!=u.facility_id or not fam or fam.facility_id!=u.facility_id: raise HTTPException(400,'利用者または家族が不正です')
        v=VisitReservation(facility_id=u.facility_id,resident_id=res.id,family_user_id=fam.id,visit_date=inp.visit_date,start_time=inp.start_time,end_time=inp.end_time,place_name=inp.place_name,visitor_count=inp.visitor_count,representative=inp.representative,phone=inp.phone,notes=inp.notes,status='confirmed'); s.add(v); s.flush(); notify(s,fam.id,'面会予約を登録しました',f'{inp.visit_date} {inp.start_time} {inp.place_name}','visits',v.id); audit(s,request,u,'visits','proxy_book','visit',v.id,{},u.facility_id); s.commit(); return {'id':v.id,'status':'confirmed'}

# -------- procurement --------
def procurement_snapshot(s,fid):
    inv=s.query(Inventory,Product,Supplier).join(Product,Inventory.product_id==Product.id).join(Supplier,Product.supplier_id==Supplier.id).filter(Inventory.facility_id==fid).all()
    inventory=[]; suggestions=[]
    for i,p,sup in inv:
        row={'inventory_id':i.id,'product_id':p.id,'sku':p.sku,'name':p.name,'category':p.category,'supplier':sup.name,'supplier_type':sup.supplier_type,'on_hand':i.on_hand,'safety_stock':i.safety_stock,'reorder_point':i.reorder_point,'target_stock':i.target_stock,'avg_daily_usage':i.avg_daily_usage,'unit':p.unit}; inventory.append(row)
        if i.on_hand < i.reorder_point:
            q=max(p.min_order_qty, int(max(0,i.target_stock-i.on_hand)+0.999)); suggestions.append(dict(row,suggested_qty=q))
    orders=[order_json(s,o) for o in s.query(PurchaseOrder).filter_by(facility_id=fid).order_by(PurchaseOrder.id.desc()).limit(100)]
    invoices=[invoice_json(s,x) for x in s.query(Invoice).filter_by(facility_id=fid).order_by(Invoice.id.desc()).limit(100)]
    return {'inventory':inventory,'suggestions':suggestions,'orders':orders,'invoices':invoices}
def order_json(s,o):
    sup=s.get(Supplier,o.supplier_id); items=[]
    for it in s.query(PurchaseOrderItem).filter_by(order_id=o.id).all():
        p=s.get(Product,it.product_id); items.append({'id':it.id,'product_id':it.product_id,'sku':p.sku if p else '','name':p.name if p else '','qty':it.qty,'unit_price':it.unit_price,'received_qty':it.received_qty})
    return {'id':o.id,'order_no':o.order_no,'facility_id':o.facility_id,'supplier_id':o.supplier_id,'supplier':sup.name if sup else '','status':o.status,'total_amount':o.total_amount,'ordered_at':dt_iso(o.ordered_at),'confirmed_at':dt_iso(o.confirmed_at),'shipped_at':dt_iso(o.shipped_at),'received_at':dt_iso(o.received_at),'items':items}
def invoice_json(s,inv): return {'id':inv.id,'invoice_no':inv.invoice_no,'facility_id':inv.facility_id,'order_id':inv.order_id,'invoice_date':inv.invoice_date,'total_amount':inv.total_amount,'status':inv.status,'match_status':inv.match_status,'differences':json.loads(inv.difference_json or '{}')}
def caredo_snapshot(s):
    sup=s.query(Supplier).filter_by(code='CAREDO').first(); orders=[order_json(s,o) for o in s.query(PurchaseOrder).filter_by(supplier_id=sup.id).order_by(PurchaseOrder.id.desc()).limit(300)] if sup else []
    return {'supplier':{'id':sup.id,'name':sup.name,'site_url':sup.site_url} if sup else None,'orders':orders,'products':[{'id':p.id,'sku':p.sku,'name':p.name,'category':p.category,'unit':p.unit,'standard_price':p.standard_price,'lead_time_days':p.lead_time_days} for p in s.query(Product).filter_by(supplier_id=sup.id,active=1).all()] if sup else []}

class InventoryAdjust(BaseModel): product_id:int; qty:float; txn_type:str='adjust'; note:str=''
@app.post('/api/inventory/adjust')
def inventory_adjust(inp:InventoryAdjust,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'staff','middle_manager','admin'); inv=s.query(Inventory).filter_by(facility_id=u.facility_id,product_id=inp.product_id).first()
        if not inv: raise HTTPException(404,'在庫がありません')
        inv.on_hand += inp.qty; inv.updated_at=now_dt(); s.add(InventoryTxn(facility_id=u.facility_id,product_id=inp.product_id,txn_type=inp.txn_type,qty=inp.qty,note=inp.note,actor_id=u.id)); audit(s,request,u,'procurement','inventory_adjust','product',inp.product_id,{'qty':inp.qty},u.facility_id); s.commit(); return {'ok':True,'on_hand':inv.on_hand}

class OrderIn(BaseModel): items:list[dict]
@app.post('/api/orders')
def create_order(inp:OrderIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'middle_manager','admin'); sup=s.query(Supplier).filter_by(code='CAREDO').first()
        if not sup: raise HTTPException(500,'ケア・ドゥ取引先マスタがありません')
        if not inp.items: raise HTTPException(400,'発注明細がありません')
        validated=[]
        for x in inp.items:
            try: pid=int(x['product_id']); q=float(x['qty'])
            except Exception: raise HTTPException(400,'発注明細が不正です')
            p=s.get(Product,pid)
            if not p or not p.active or p.supplier_id!=sup.id: raise HTTPException(400,'ケア・ドゥの商品ではありません')
            if q<=0: raise HTTPException(400,'発注数量は1以上にしてください')
            if q<p.min_order_qty: raise HTTPException(400,f'{p.name}は最低{p.min_order_qty}{p.unit}から発注できます')
            validated.append((p,q))
        no='PO-'+datetime.now(JST).strftime('%Y%m%d%H%M%S%f')+'-'+secrets.token_hex(2).upper(); o=PurchaseOrder(order_no=no,facility_id=u.facility_id,supplier_id=sup.id,status='submitted',approved_by=u.id,ordered_at=now_dt()); s.add(o); s.flush(); total=0
        for p,q in validated:
            fp=s.query(FacilityPrice).filter_by(facility_id=u.facility_id,product_id=p.id).first(); price=fp.purchase_price if fp else p.standard_price; total+=q*price; s.add(PurchaseOrderItem(order_id=o.id,product_id=p.id,qty=q,unit_price=price))
        o.total_amount=total; audit(s,request,u,'procurement','order_submit','purchase_order',o.id,{'total':total},u.facility_id); s.commit(); return {'id':o.id,'order_no':o.order_no,'total_amount':total}

class OrderStatusIn(BaseModel): status:str
@app.post('/api/orders/{oid}/status')
def order_status(oid:int,inp:OrderStatusIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'caredo','admin'); o=s.get(PurchaseOrder,oid)
        if not o: raise HTTPException(404,'注文がありません')
        if u.role=='admin': facility_scope(u,o.facility_id)
        allowed={'submitted':{'confirmed','cancelled'},'confirmed':{'shipped','cancelled'}} if u.role=='caredo' else {'submitted':{'cancelled'},'confirmed':{'cancelled'}}
        if inp.status not in allowed.get(o.status,set()): raise HTTPException(400,'現在の状態からその変更はできません')
        o.status=inp.status
        if inp.status=='confirmed': o.confirmed_at=now_dt()
        if inp.status=='shipped': o.shipped_at=now_dt()
        audit(s,request,u,'procurement','order_status','purchase_order',o.id,{'status':inp.status},o.facility_id); s.commit(); return {'ok':True}

class InvoiceIn(BaseModel): order_id:int; invoice_no:str; invoice_date:str; items:list[dict]
@app.post('/api/invoices')
def create_invoice(inp:InvoiceIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'caredo'); o=s.get(PurchaseOrder,inp.order_id)
        if not o: raise HTTPException(404,'注文がありません')
        if o.status!='received': raise HTTPException(400,'検品完了後に請求書を作成してください')
        if s.query(Invoice).filter_by(order_id=o.id).first(): raise HTTPException(400,'この注文の請求書は作成済みです')
        if s.query(Invoice).filter_by(invoice_no=inp.invoice_no).first(): raise HTTPException(400,'請求書番号が重複しています')
        total=0; inv=Invoice(invoice_no=inp.invoice_no,supplier_id=o.supplier_id,facility_id=o.facility_id,order_id=o.id,invoice_date=inp.invoice_date,status='received'); s.add(inv); s.flush()
        for x in inp.items:
            pid=int(x['product_id']); qty=float(x['qty']); price=float(x['unit_price']); amount=qty*price; total+=amount; s.add(InvoiceItem(invoice_id=inv.id,product_id=pid,qty=qty,unit_price=price,amount=amount))
        inv.total_amount=total; perform_match(s,inv,o); s.flush(); inv.pdf_blob=make_invoice_pdf(s,inv); audit(s,request,u,'procurement','invoice_create','invoice',inv.id,{'match':inv.match_status},o.facility_id); s.commit(); return invoice_json(s,inv)

def perform_match(s,inv,o):
    diffs=[]; oi={x.product_id:x for x in s.query(PurchaseOrderItem).filter_by(order_id=o.id).all()}
    for ii in s.query(InvoiceItem).filter_by(invoice_id=inv.id).all():
        x=oi.get(ii.product_id)
        if not x: diffs.append({'product_id':ii.product_id,'type':'not_ordered'}); continue
        if abs(ii.qty-x.received_qty)>0.0001: diffs.append({'product_id':ii.product_id,'type':'qty','ordered':x.qty,'received':x.received_qty,'invoice':ii.qty})
        if abs(ii.unit_price-x.unit_price)>0.01: diffs.append({'product_id':ii.product_id,'type':'price','ordered_price':x.unit_price,'invoice_price':ii.unit_price})
    inv.difference_json=json.dumps({'items':diffs},ensure_ascii=False); inv.match_status='matched' if not diffs else 'difference'; o.status='invoiced' if not diffs else o.status



class ReceiveIn(BaseModel):
    items:list[dict]
@app.post('/api/orders/{oid}/receive')
def receive_order(oid:int,inp:ReceiveIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','middle_manager'); o=s.get(PurchaseOrder,oid)
        if not o: raise HTTPException(404,'注文がありません')
        facility_scope(u,o.facility_id)
        if o.status not in ('shipped','partially_received'): raise HTTPException(400,'出荷済みの注文だけ検品できます')
        byid={x.id:x for x in s.query(PurchaseOrderItem).filter_by(order_id=o.id).all()}
        for x in inp.items:
            it=byid.get(int(x.get('item_id',0)))
            if not it: continue
            new=float(x.get('received_qty',0))
            if new<0 or new>it.qty: raise HTTPException(400,'受領数量が不正です')
            delta=new-it.received_qty; it.received_qty=new
            if delta:
                inv=s.query(Inventory).filter_by(facility_id=o.facility_id,product_id=it.product_id).first()
                if inv: inv.on_hand+=delta; inv.updated_at=now_dt()
                s.add(InventoryTxn(facility_id=o.facility_id,product_id=it.product_id,txn_type='receipt',qty=delta,reference_type='purchase_order',reference_id=str(o.id),actor_id=u.id))
        all_items=list(byid.values()); complete=all(abs(x.received_qty-x.qty)<0.0001 for x in all_items)
        o.status='received' if complete else 'partially_received'; o.received_at=now_dt() if complete else None
        audit(s,request,u,'procurement','receive_inspect','purchase_order',o.id,{'complete':complete},o.facility_id); s.commit(); return {'ok':True,'status':o.status}

class ProductIn(BaseModel):
    sku:str; name:str; specification:str=''; category:str=''; unit:str='個'; standard_price:float=0; min_order_qty:int=1; lead_time_days:int=2
@app.post('/api/products')
def create_product(inp:ProductIn,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'caredo','hq'); sup=s.query(Supplier).filter_by(code='CAREDO').first()
        if s.query(Product).filter_by(sku=inp.sku).first(): raise HTTPException(400,'SKUが重複しています')
        p=Product(supplier_id=sup.id,**inp.model_dump()); s.add(p); s.flush(); audit(s,request,u,'procurement','product_create','product',p.id,{'sku':p.sku}); s.commit(); return {'id':p.id,'ok':True}

def make_invoice_pdf(s,inv:Invoice):
    buf=io.BytesIO(); st=pdf_styles(); fac=s.get(Facility,inv.facility_id); sup=s.get(Supplier,inv.supplier_id); story=[Paragraph('請求書',st['title']),Paragraph(f'請求書番号: {inv.invoice_no}',st['body']),Paragraph(f'請求日: {inv.invoice_date}',st['body']),Spacer(1,4*mm),Paragraph(f'請求先: {fac.name if fac else ""}',st['body']),Paragraph(f'発行元: {sup.name if sup else ""}',st['body']),Spacer(1,6*mm)]
    data=[['SKU','商品','数量','単価','金額']]
    for it in s.query(InvoiceItem).filter_by(invoice_id=inv.id).all():
        p=s.get(Product,it.product_id); data.append([p.sku if p else '',p.name if p else '',str(it.qty),f'{it.unit_price:,.0f}',f'{it.amount:,.0f}'])
    data.append(['','','','','合計 ¥'+f'{inv.total_amount:,.0f}']); t=Table(data,colWidths=[28*mm,65*mm,18*mm,28*mm,35*mm]); t.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'HeiseiKakuGo-W5'),('FONTSIZE',(0,0),(-1,-1),8),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#dddddd')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#fff0df')),('ALIGN',(2,1),(-1,-1),'RIGHT')])); story.append(t); story.append(Spacer(1,5*mm)); story.append(Paragraph(f'3点照合: {inv.match_status}',st['small'])); SimpleDocTemplate(buf,pagesize=A4,rightMargin=15*mm,leftMargin=15*mm,topMargin=15*mm,bottomMargin=15*mm).build(story); return buf.getvalue()

@app.get('/api/invoices/{iid}/pdf')
def invoice_pdf(iid:int,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq','caredo'); inv=s.get(Invoice,iid)
        if not inv: raise HTTPException(404,'請求書がありません')
        if u.role=='admin': facility_scope(u,inv.facility_id)
        pdf=inv.pdf_blob or make_invoice_pdf(s,inv); return Response(content=bytes(pdf),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="invoice_{iid}.pdf"'})

# -------- CSV bulk import --------
def csv_rows(raw:bytes):
    text=raw.decode('utf-8-sig'); return list(csv.DictReader(io.StringIO(text)))

@app.post('/api/import/{kind}')
async def bulk_import(kind:str,request:Request,file:UploadFile=File(...)):
    raw=await file.read()
    rows=csv_rows(raw); count=0; warnings=[]
    with SessionLocal() as s:
        u=current_user(request,s)
        if kind=='facilities':
            require_roles(u,'hq')
            for r in rows:
                code=(r.get('facility_code') or '').strip(); name=(r.get('facility_name') or '').strip()
                if not code or not name: warnings.append('施設コード/施設名不足'); continue
                f=s.query(Facility).filter_by(code=code).first() or Facility(code=code,name=name); f.name=name; f.corporation=r.get('corporation') or '社会福祉法人 一燈会'; f.address=r.get('address') or ''; f.phone=r.get('phone') or ''; s.add(f); count+=1
        elif kind=='staff':
            require_roles(u,'hq','admin'); default_pw=os.environ.get('IMPORT_DEFAULT_PASSWORD','ChangeMe1234!')
            for r in rows:
                email=(r.get('email') or '').strip().lower(); code=(r.get('employee_code') or '').strip(); name=(r.get('name') or '').strip(); fcode=(r.get('facility_code') or '').strip(); dcode=(r.get('department_code') or '').strip(); role=(r.get('role') or 'staff').strip()
                f=s.query(Facility).filter_by(code=fcode).first();
                if not email or not f or role not in ('staff','middle_manager','admin'): warnings.append(f'{email or name}: データ不足'); continue
                if u.role=='admin' and f.id!=u.facility_id: warnings.append(f'{email}: 他施設'); continue
                d=s.query(Department).filter_by(facility_id=f.id,code=dcode).first() if dcode else None
                usr=s.query(User).filter(func.lower(User.email)==email).first()
                if not usr: usr=User(email=email,password_hash=hash_password(default_pw),created_at=now_dt())
                usr.employee_code=code; usr.name=name; usr.role=role; usr.facility_id=f.id; usr.department_id=d.id if d else None; usr.active=1; s.add(usr); count+=1
        elif kind=='residents_family':
            require_roles(u,'hq','admin'); default_pw=os.environ.get('IMPORT_DEFAULT_PASSWORD','ChangeMe1234!')
            for r in rows:
                f=s.query(Facility).filter_by(code=(r.get('facility_code') or '').strip()).first(); rcode=(r.get('resident_code') or '').strip(); rname=(r.get('resident_name') or '').strip(); email=(r.get('family_email') or '').strip().lower()
                if not f or not rcode or not rname or not email: warnings.append(f'{rcode or rname}: データ不足'); continue
                if u.role=='admin' and f.id!=u.facility_id: continue
                res=s.query(Resident).filter_by(resident_code=rcode).first() or Resident(resident_code=rcode,facility_id=f.id,name=rname); res.name=rname; res.facility_id=f.id; res.service_type=r.get('service_type') or '入所'; s.add(res); s.flush()
                fam=s.query(User).filter(func.lower(User.email)==email).first()
                if not fam: fam=User(name=r.get('family_name') or '家族',email=email,password_hash=hash_password(default_pw),role='family',facility_id=f.id,created_at=now_dt()); s.add(fam); s.flush()
                if not s.query(FamilyLink).filter_by(user_id=fam.id,resident_id=res.id).first(): s.add(FamilyLink(user_id=fam.id,resident_id=res.id,relation=r.get('relation') or '家族',is_primary=1))
                count+=1
        elif kind=='caredo_products':
            require_roles(u,'hq','caredo'); sup=s.query(Supplier).filter_by(code='CAREDO').first()
            for r in rows:
                sku=(r.get('sku') or '').strip(); name=(r.get('name') or '').strip()
                if not sku or not name: continue
                p=s.query(Product).filter_by(sku=sku).first() or Product(supplier_id=sup.id,sku=sku,name=name); p.name=name; p.specification=r.get('specification') or ''; p.category=r.get('category') or ''; p.unit=r.get('unit') or '個'; p.pack_size=int(float(r.get('pack_size') or 1)); p.standard_price=float(r.get('standard_price') or 0); p.min_order_qty=int(float(r.get('min_order_qty') or 1)); p.lead_time_days=int(float(r.get('lead_time_days') or 2)); p.substitute_sku=r.get('substitute_sku') or ''; p.inventory_managed=int(float(r.get('inventory_managed') or 1)); p.active=1; s.add(p); count+=1
        elif kind=='inventory':
            require_roles(u,'hq','admin')
            for r in rows:
                f=s.query(Facility).filter_by(code=(r.get('facility_code') or '').strip()).first(); p=s.query(Product).filter_by(sku=(r.get('sku') or '').strip()).first()
                if not f or not p: warnings.append('施設またはSKU不明'); continue
                if u.role=='admin' and f.id!=u.facility_id: continue
                loc=r.get('location') or '主倉庫'; inv=s.query(Inventory).filter_by(facility_id=f.id,product_id=p.id,location=loc).first() or Inventory(facility_id=f.id,product_id=p.id,location=loc)
                for field in ['on_hand','safety_stock','reorder_point','target_stock','avg_daily_usage']: setattr(inv,field,float(r.get(field) or 0))
                inv.updated_at=now_dt(); s.add(inv)
                fp=s.query(FacilityPrice).filter_by(facility_id=f.id,product_id=p.id).first() or FacilityPrice(facility_id=f.id,product_id=p.id)
                fp.purchase_price=float(r.get('purchase_price') or 0); fp.sale_price=float(r.get('sale_price') or 0); s.add(fp); count+=1
        else: raise HTTPException(404,'未対応の取込種別です')
        audit(s,request,u,'import','csv_import',kind,'',{'count':count,'warnings':warnings[:20]}); s.commit(); return {'ok':True,'count':count,'warnings':warnings[:50]}

# -------- integrations / dashboard --------
def hq_dashboard(s):
    return {'facilities':s.query(Facility).filter_by(active=1).count(),'users':s.query(User).filter_by(active=1).count(),'families':s.query(User).filter_by(role='family',active=1).count(),'staff':s.query(User).filter(User.role.in_(['staff','middle_manager','admin']),User.active==1).count(),'middle_managers':s.query(User).filter_by(role='middle_manager',active=1).count(),'admins':s.query(User).filter_by(role='admin',active=1).count(),'documents_pending':s.query(DocumentRecipient).filter(DocumentRecipient.status!='signed').count(),'workflow_pending':s.query(WorkflowRequest).filter(WorkflowRequest.status.in_(['pending_manager','pending_admin'])).count(),'visits_upcoming':s.query(VisitReservation).filter(VisitReservation.status.in_(['confirmed','pending'])).count(),'orders_open':s.query(PurchaseOrder).filter(PurchaseOrder.status.notin_(['closed','cancelled'])).count()}
def integration_list(s): return [{'system_name':x.system_name,'display_name':x.display_name,'mode':x.mode,'direction':x.direction,'status':x.status,'notes':x.notes} for x in s.query(IntegrationProfile).all()]

@app.get('/api/dashboard')
def dashboard(request:Request):
    with SessionLocal() as s:
        u=current_user(request,s)
        if u.role=='hq': return hq_dashboard(s)
        if u.role in ('admin','middle_manager'): return {'workflow_pending':len(workflow_list(s,u,approval=True)),'visits':len(visit_list_for_facility(s,u.facility_id)),'procurement':procurement_snapshot(s,u.facility_id) if u.role=='admin' else {}}
        return {}

@app.get('/api/integrations')
def integrations(request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'hq','admin'); return {'items':integration_list(s)}

@app.get('/api/integrations/export/{system_name}')
def integration_export(system_name:str,request:Request):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'hq','admin')
        out=io.StringIO(); w=csv.writer(out)
        if system_name=='chronos':
            w.writerow(['employee_code','request_type','request_date','start_time','end_time','status','approved_at'])
            q=s.query(WorkflowRequest,User).join(User,WorkflowRequest.applicant_id==User.id).filter(WorkflowRequest.status=='approved')
            if u.role=='admin': q=q.filter(WorkflowRequest.facility_id==u.facility_id)
            for r,usr in q.all(): w.writerow([usr.employee_code,r.request_type,r.request_date,r.start_time,r.end_time,r.status,dt_iso(r.updated_at)])
        elif system_name=='honobono':
            w.writerow(['resident_code','resident_name','facility_code','service_type'])
            q=s.query(Resident,Facility).join(Facility,Resident.facility_id==Facility.id)
            if u.role=='admin': q=q.filter(Resident.facility_id==u.facility_id)
            for r,f in q.all(): w.writerow([r.resident_code,r.name,f.code,r.service_type])
        elif system_name=='yayoi':
            w.writerow(['invoice_no','invoice_date','facility','total_amount','match_status'])
            q=s.query(Invoice,Facility).join(Facility,Invoice.facility_id==Facility.id)
            if u.role=='admin': q=q.filter(Invoice.facility_id==u.facility_id)
            for inv,f in q.all(): w.writerow([inv.invoice_no,inv.invoice_date,f.name,inv.total_amount,inv.match_status])
        else: raise HTTPException(404,'未対応の連携先です')
        data='\ufeff'+out.getvalue(); return Response(content=data.encode('utf-8'),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="ittokai_{system_name}_export.csv"'})

@app.get('/api/audit')
def audit_list(request:Request,module:Optional[str]=None):
    with SessionLocal() as s:
        u=current_user(request,s); require_roles(u,'admin','hq'); q=s.query(AuditLog)
        if u.role=='admin': q=q.filter(AuditLog.facility_id==u.facility_id)
        if module: q=q.filter(AuditLog.module==module)
        return {'items':[{'id':x.id,'actor_name':x.actor_name,'module':x.module,'action':x.action,'entity_type':x.entity_type,'entity_id':x.entity_id,'metadata':json.loads(x.metadata_json or '{}'),'ip':x.ip,'created_at':dt_iso(x.created_at)} for x in q.order_by(AuditLog.id.desc()).limit(300)]}

# Static / PWA
app.mount('/assets', StaticFiles(directory=os.path.join(STATIC,'assets')), name='assets')
@app.get('/manifest.webmanifest')
def manifest(): return FileResponse(os.path.join(STATIC,'manifest.webmanifest'),media_type='application/manifest+json')
@app.get('/sw.js')
def sw(): return FileResponse(os.path.join(STATIC,'sw.js'),media_type='application/javascript')
@app.get('/privacy')
def privacy(): return FileResponse(os.path.join(STATIC,'privacy.html'))
@app.get('/terms')
def terms(): return FileResponse(os.path.join(STATIC,'terms.html'))
@app.get('/{path:path}')
def spa(path:str):
    fp=os.path.join(STATIC,path)
    if path and os.path.isfile(fp): return FileResponse(fp)
    return FileResponse(os.path.join(STATIC,'index.html'))

if __name__=='__main__':
    import uvicorn
    port=int(os.environ.get('PORT','8000'))
    uvicorn.run(app,host='0.0.0.0',port=port)
