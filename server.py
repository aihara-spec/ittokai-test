from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote
import sqlite3, json, os, secrets, hashlib, hmac, base64, io, qrcode, mimetypes
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(ROOT, 'static')
DB = os.environ.get('DB_PATH', os.path.join(ROOT, 'ittokai.db'))
JST = timezone(timedelta(hours=9))

def now(): return datetime.now(JST).isoformat(timespec='seconds')

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c

def hash_password(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, 120000)
    return base64.b64encode(salt).decode()+':' + base64.b64encode(dk).decode()

def verify_password(pw, stored):
    try:
        s,h=stored.split(':',1); salt=base64.b64decode(s); expected=base64.b64decode(h)
        got=hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, 120000)
        return hmac.compare_digest(got, expected)
    except Exception: return False

def init_db():
    c=db(); cur=c.cursor()
    cur.executescript('''
    CREATE TABLE IF NOT EXISTS facilities(id INTEGER PRIMARY KEY, name TEXT, corporation TEXT, address TEXT, phone TEXT, code TEXT UNIQUE);
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE, phone TEXT, password_hash TEXT, role TEXT, facility_id INTEGER, resident_name TEXT, relation TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT);
    CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY, facility_id INTEGER, name TEXT, type TEXT, subtitle TEXT);
    CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, facility_id INTEGER, user_id INTEGER, sender_role TEXT, sender_name TEXT, body TEXT, created_at TEXT, read_at TEXT);
    CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY, facility_id INTEGER, category TEXT, title TEXT, body TEXT, important INTEGER DEFAULT 0, created_at TEXT, image_url TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS vendors(id INTEGER PRIMARY KEY, facility_id INTEGER, name TEXT, contact_name TEXT DEFAULT '', email TEXT DEFAULT '', phone TEXT DEFAULT '', site_url TEXT DEFAULT '', order_url TEXT DEFAULT '', notes TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, category TEXT, name TEXT, price INTEGER, vendor TEXT, external_url TEXT, description TEXT, featured INTEGER DEFAULT 0, image_url TEXT DEFAULT '', vendor_id INTEGER);
    CREATE TABLE IF NOT EXISTS invites(code TEXT PRIMARY KEY, facility_id INTEGER, resident_name TEXT, relation TEXT, expires_at TEXT, max_uses INTEGER, used_count INTEGER DEFAULT 0, created_at TEXT);
    ''')
    # v5 migration: add image columns to older databases without deleting data
    news_cols={r['name'] for r in cur.execute('PRAGMA table_info(news)').fetchall()}
    if 'image_url' not in news_cols:
        cur.execute("ALTER TABLE news ADD COLUMN image_url TEXT DEFAULT ''")
    product_cols={r['name'] for r in cur.execute('PRAGMA table_info(products)').fetchall()}
    if 'image_url' not in product_cols:
        cur.execute("ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''")
    if 'vendor_id' not in product_cols:
        cur.execute("ALTER TABLE products ADD COLUMN vendor_id INTEGER")
    if cur.execute('SELECT COUNT(*) n FROM facilities').fetchone()['n']==0:
        cur.execute('INSERT INTO facilities(name,corporation,address,phone,code) VALUES(?,?,?,?,?)',('メゾン・二宮','社会福祉法人 一燈会','神奈川県中郡二宮町','0463-00-0000','MAISON-NINOMIYA'))
        fid=cur.lastrowid
        cur.executemany('INSERT INTO contacts(facility_id,name,type,subtitle) VALUES(?,?,?,?)',[
            (fid,'メゾン・二宮','施設','代表窓口'),(fid,'生活相談員','担当','ご相談・連絡'),(fid,'デイサービス','部署','利用日の連絡'),(fid,'事務','部署','請求・書類')])
        cur.execute('INSERT INTO users(name,email,phone,password_hash,role,facility_id,resident_name,relation,created_at) VALUES(?,?,?,?,?,?,?,?,?)',('施設管理者','admin@ittokai.local','',hash_password('admin1234'),'admin',fid,'','',now()))
        cur.execute('INSERT INTO users(name,email,phone,password_hash,role,facility_id,resident_name,relation,created_at) VALUES(?,?,?,?,?,?,?,?,?)',('相原 良太','family@ittokai.local','090-0000-0000',hash_password('demo1234'),'family',fid,'相原 太郎','家族',now()))
        uid=cur.lastrowid
        cur.executemany('INSERT INTO news(facility_id,category,title,body,important,created_at) VALUES(?,?,?,?,?,?)',[
            (fid,'重要','面会についてのお知らせ','面会時間は14:00〜17:00です。ご来館前に受付へお声がけください。',1,now()),
            (fid,'イベント','敬老会開催のお知らせ','9月20日（日）14:00より敬老会を開催します。',0,now()),
            (fid,'施設だより','施設だより9月号','今月の行事予定と施設からのお知らせをご案内します。',0,now())])
        cur.executemany('INSERT INTO vendors(facility_id,name,contact_name,email,phone,site_url,order_url,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',[
            (fid,'協賛販売会社A','営業担当','','','https://example.com/','https://example.com/','デモ協賛企業',1,now()),
            (fid,'協賛販売会社B','営業担当','','','https://example.com/','https://example.com/','デモ協賛企業',1,now()),
            (fid,'協賛販売会社C','営業担当','','','https://example.com/','https://example.com/','デモ協賛企業',1,now()),
            (fid,'協賛販売会社D','営業担当','','','https://example.com/','https://example.com/','デモ協賛企業',1,now())])
        vendors={r['name']:r['id'] for r in cur.execute('SELECT id,name FROM vendors WHERE facility_id=?',(fid,)).fetchall()}
        cur.executemany('INSERT INTO products(category,name,price,vendor,external_url,description,featured,vendor_id) VALUES(?,?,?,?,?,?,?,?)',[
            ('リハパン','リハビリパンツ M',2980,'協賛販売会社A','https://example.com/','施設へ直接送付できるリハビリパンツです。',1,vendors.get('協賛販売会社A')),
            ('尿取りパッド','夜用尿取りパッド',1980,'協賛販売会社B','https://example.com/','夜間用の高吸収タイプです。',1,vendors.get('協賛販売会社B')),
            ('日用品','BOXティッシュ 5箱',398,'協賛販売会社C','https://example.com/','施設で使いやすい日用品です。',0,vendors.get('協賛販売会社C')),
            ('食品','栄養補助ゼリー 6個',1280,'協賛販売会社D','https://example.com/','食べやすい栄養補助食品です。',0,vendors.get('協賛販売会社D'))])
        cur.executemany('INSERT INTO messages(facility_id,user_id,sender_role,sender_name,body,created_at,read_at) VALUES(?,?,?,?,?,?,?)',[
            (fid,uid,'facility','メゾン・二宮','本日のご様子です。昼食は全量召し上がられ、午後は体操に参加されています。',now(),now()),
            (fid,uid,'family','相原 良太','ありがとうございます。よろしくお願いいたします。',now(),now())])
        code='DEMO-INVITE'
        exp=(datetime.now(JST)+timedelta(days=30)).isoformat(timespec='seconds')
        cur.execute('INSERT INTO invites(code,facility_id,resident_name,relation,expires_at,max_uses,created_at) VALUES(?,?,?,?,?,?,?)',(code,fid,'山田 太郎','家族',exp,5,now()))
    # v8: 協賛企業マスタ（既存DBのアップグレード時も作成）
    fidrow=cur.execute('SELECT id FROM facilities ORDER BY id LIMIT 1').fetchone()
    if fidrow and cur.execute('SELECT COUNT(*) n FROM vendors').fetchone()['n']==0:
        fid=fidrow['id']
        cur.executemany('INSERT INTO vendors(facility_id,name,contact_name,site_url,order_url,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?)',[
            (fid,'協賛販売会社A','営業担当','https://example.com/','https://example.com/','デモ協賛企業',1,now()),
            (fid,'協賛販売会社B','営業担当','https://example.com/','https://example.com/','デモ協賛企業',1,now()),
            (fid,'協賛販売会社C','営業担当','https://example.com/','https://example.com/','デモ協賛企業',1,now()),
            (fid,'協賛販売会社D','営業担当','https://example.com/','https://example.com/','デモ協賛企業',1,now())])
        for r in cur.execute('SELECT id,vendor FROM products WHERE COALESCE(vendor_id,0)=0').fetchall():
            v=cur.execute('SELECT id FROM vendors WHERE facility_id=? AND name=?',(fid,r['vendor'])).fetchone()
            if v: cur.execute('UPDATE products SET vendor_id=? WHERE id=?',(v['id'],r['id']))

    # Add tasteful local demo imagery for existing sample records.
    cur.execute("UPDATE news SET image_url='/assets/cards/news-important.svg' WHERE title LIKE '%面会%' AND COALESCE(image_url,'')=''")
    cur.execute("UPDATE news SET image_url='/assets/cards/news-event.svg' WHERE title LIKE '%敬老会%' AND COALESCE(image_url,'')=''")
    cur.execute("UPDATE news SET image_url='/assets/cards/news-event.svg' WHERE title LIKE '%施設だより%' AND COALESCE(image_url,'')=''")
    cur.execute("UPDATE products SET image_url='/assets/cards/product-pants.svg' WHERE name LIKE '%リハビリパンツ%' AND COALESCE(image_url,'')=''")
    cur.execute("UPDATE products SET image_url='/assets/cards/product-pad.svg' WHERE name LIKE '%尿取りパッド%' AND COALESCE(image_url,'')=''")
    cur.execute("UPDATE products SET image_url='/assets/cards/product-tissue.svg' WHERE name LIKE '%ティッシュ%' AND COALESCE(image_url,'')=''")
    cur.execute("UPDATE products SET image_url='/assets/cards/product-jelly.svg' WHERE name LIKE '%ゼリー%' AND COALESCE(image_url,'')=''")
    # branding migration v10: keep existing test data while updating demo accounts
    cur.execute("UPDATE users SET email='admin@ittokai.local' WHERE lower(email)='admin@careconnect.local'")
    cur.execute("UPDATE users SET email='family@ittokai.local' WHERE lower(email)='demo@example.com'")
    c.commit(); c.close()

def rowdict(r): return dict(r) if r else None

def auth_user(headers):
    a=headers.get('Authorization','')
    if not a.startswith('Bearer '): return None
    token=a[7:]
    c=db(); r=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?',(token,)).fetchone(); c.close(); return rowdict(r)

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy','camera=(self), microphone=(), geolocation=()')
        super().end_headers()
    def translate_path(self, path):
        p=urlparse(path).path
        if p.startswith('/api/'): return super().translate_path(path)
        rel=p.lstrip('/') or 'index.html'
        if rel=='register': rel='index.html'
        if rel=='privacy': rel='privacy.html'
        if rel=='terms': rel='terms.html'
        return os.path.join(STATIC, rel)
    def _json(self, obj, status=200):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self):
        try: return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0') or 0)) or b'{}')
        except: return {}
    def do_GET(self):
        u=urlparse(self.path); p=u.path
        if p=='/healthz': return self._json({'ok':True,'service':'ittokai'})
        if p=='/api/bootstrap':
            user=auth_user(self.headers)
            if not user: return self._json({'error':'unauthorized'},401)
            c=db(); fid=user['facility_id'] or 1
            out={'user':user,
                 'facility':rowdict(c.execute('SELECT * FROM facilities WHERE id=?',(fid,)).fetchone()),
                 'contacts':[dict(x) for x in c.execute('SELECT * FROM contacts WHERE facility_id=? ORDER BY id',(fid,))],
                 'messages':[dict(x) for x in c.execute('SELECT * FROM messages WHERE facility_id=? AND user_id=? ORDER BY id',(fid,user['id'] if user['role']!='admin' else (c.execute("SELECT id FROM users WHERE facility_id=? AND role='family' ORDER BY id LIMIT 1",(fid,)).fetchone() or {'id':user['id']})['id'])).fetchall()],
                 'family_users':[dict(x) for x in c.execute("SELECT id,name,email,resident_name,relation FROM users WHERE facility_id=? AND role='family' ORDER BY id",(fid,)).fetchall()] if user['role']=='admin' else [],
                 'news':[dict(x) for x in c.execute('SELECT * FROM news WHERE facility_id=? ORDER BY important DESC,id DESC',(fid,))],
                 'products':[dict(x) for x in c.execute('SELECT * FROM products ORDER BY featured DESC,id DESC')],
                 'vendors':[dict(x) for x in c.execute('SELECT * FROM vendors WHERE facility_id=? ORDER BY active DESC,name',(fid,)).fetchall()] if user['role']=='admin' else [],
                 'invites':[dict(x) for x in c.execute('SELECT * FROM invites WHERE facility_id=? ORDER BY created_at DESC',(fid,)).fetchall()] if user['role']=='admin' else []}
            c.close(); return self._json(out)
        if p=='/api/sync':
            user=auth_user(self.headers)
            if not user: return self._json({'error':'unauthorized'},401)
            c=db(); fid=user['facility_id'] or 1
            out={'news':[dict(x) for x in c.execute('SELECT * FROM news WHERE facility_id=? ORDER BY important DESC,id DESC',(fid,)).fetchall()],
                 'products':[dict(x) for x in c.execute('SELECT * FROM products ORDER BY featured DESC,id DESC').fetchall()],
                 'vendors':[dict(x) for x in c.execute('SELECT * FROM vendors WHERE facility_id=? ORDER BY active DESC,name',(fid,)).fetchall()] if user['role']=='admin' else []}
            c.close(); return self._json(out)
        if p=='/api/messages':
            user=auth_user(self.headers)
            if not user: return self._json({'error':'unauthorized'},401)
            qs=parse_qs(u.query); target=user['id']
            if user['role']=='admin':
                try: target=int(qs.get('user_id',['0'])[0] or 0)
                except: target=0
                c=db(); valid=c.execute("SELECT id FROM users WHERE id=? AND facility_id=? AND role='family'",(target,user['facility_id'])).fetchone()
                if not valid:
                    r=c.execute("SELECT id FROM users WHERE facility_id=? AND role='family' ORDER BY id LIMIT 1",(user['facility_id'],)).fetchone(); target=r['id'] if r else user['id']
                rows=[dict(x) for x in c.execute('SELECT * FROM messages WHERE facility_id=? AND user_id=? ORDER BY id',(user['facility_id'],target)).fetchall()]; c.close()
            else:
                c=db(); rows=[dict(x) for x in c.execute('SELECT * FROM messages WHERE facility_id=? AND user_id=? ORDER BY id',(user['facility_id'],user['id'])).fetchall()]; c.close()
            return self._json({'messages':rows,'user_id':target})
        if p=='/api/invite':
            code=parse_qs(u.query).get('code',[''])[0]; c=db(); r=c.execute('SELECT i.*,f.name facility_name FROM invites i JOIN facilities f ON f.id=i.facility_id WHERE i.code=?',(code,)).fetchone(); c.close()
            if not r: return self._json({'error':'not_found'},404)
            d=dict(r); d['valid'] = d['used_count'] < d['max_uses'] and datetime.fromisoformat(d['expires_at']) > datetime.now(JST)
            return self._json(d)
        if p=='/api/qr':
            data=parse_qs(u.query).get('data',[''])[0]
            if not data: return self._json({'error':'missing_data'},400)
            img=qrcode.make(data); bio=io.BytesIO(); img.save(bio,format='PNG'); b=bio.getvalue()
            self.send_response(200); self.send_header('Content-Type','image/png'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        return super().do_GET()
    def do_POST(self):
        p=urlparse(self.path).path; body=self._body()
        if p=='/api/login':
            c=db(); r=c.execute('SELECT * FROM users WHERE lower(email)=lower(?)',(body.get('email',''),)).fetchone()
            if not r or not verify_password(body.get('password',''),r['password_hash']): c.close(); return self._json({'error':'invalid_credentials'},401)
            token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)',(token,r['id'],now())); c.commit(); c.close(); return self._json({'token':token,'role':r['role']})
        if p=='/api/register':
            code=body.get('invite','').strip(); c=db(); inv=c.execute('SELECT * FROM invites WHERE code=?',(code,)).fetchone()
            if not inv: c.close(); return self._json({'error':'invite_not_found'},400)
            if inv['used_count']>=inv['max_uses'] or datetime.fromisoformat(inv['expires_at'])<=datetime.now(JST): c.close(); return self._json({'error':'invite_expired'},400)
            try:
                cur=c.execute('INSERT INTO users(name,email,phone,password_hash,role,facility_id,resident_name,relation,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(body.get('name','').strip(),body.get('email','').strip(),body.get('phone','').strip(),hash_password(body.get('password','')),'family',inv['facility_id'],inv['resident_name'],inv['relation'],now()))
                c.execute('UPDATE invites SET used_count=used_count+1 WHERE code=?',(code,)); token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)',(token,cur.lastrowid,now())); c.commit(); c.close(); return self._json({'token':token})
            except sqlite3.IntegrityError: c.close(); return self._json({'error':'email_exists'},400)
        user=auth_user(self.headers)
        if not user: return self._json({'error':'unauthorized'},401)
        c=db()
        if p=='/api/messages':
            text=body.get('body','').strip()
            if not text: c.close(); return self._json({'error':'empty'},400)
            target=user['id']
            if user['role']=='admin':
                try: target=int(body.get('user_id') or 0)
                except: target=0
                valid=c.execute("SELECT id FROM users WHERE id=? AND facility_id=? AND role='family'",(target,user['facility_id'])).fetchone()
                if not valid: c.close(); return self._json({'error':'invalid_conversation'},400)
            c.execute('INSERT INTO messages(facility_id,user_id,sender_role,sender_name,body,created_at,read_at) VALUES(?,?,?,?,?,?,NULL)',(user['facility_id'],target,user['role'],user['name'],text,now())); c.commit()
            mid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.close(); return self._json({'ok':True,'id':mid})
        if p=='/api/messages/read':
            target=user['id']
            if user['role']=='admin':
                try: target=int(body.get('user_id') or 0)
                except: target=0
                valid=c.execute("SELECT id FROM users WHERE id=? AND facility_id=? AND role='family'",(target,user['facility_id'])).fetchone()
                if not valid: c.close(); return self._json({'error':'invalid_conversation'},400)
                c.execute("UPDATE messages SET read_at=? WHERE facility_id=? AND user_id=? AND sender_role='family' AND read_at IS NULL",(now(),user['facility_id'],target))
            else:
                c.execute("UPDATE messages SET read_at=? WHERE facility_id=? AND user_id=? AND sender_role='admin' AND read_at IS NULL",(now(),user['facility_id'],user['id']))
                c.execute("UPDATE messages SET read_at=? WHERE facility_id=? AND user_id=? AND sender_role='facility' AND read_at IS NULL",(now(),user['facility_id'],user['id']))
            c.commit(); c.close(); return self._json({'ok':True})
        if p=='/api/news' and user['role']=='admin':
            c.execute('INSERT INTO news(facility_id,category,title,body,important,created_at,image_url) VALUES(?,?,?,?,?,?,?)',(user['facility_id'],body.get('category','お知らせ'),body.get('title','').strip(),body.get('body','').strip(),1 if body.get('important') else 0,now(),body.get('image_url','').strip())); c.commit(); c.close(); return self._json({'ok':True})
        if p=='/api/vendors' and user['role']=='admin':
            name=body.get('name','').strip()
            if not name: c.close(); return self._json({'error':'vendor_name_required'},400)
            c.execute('INSERT INTO vendors(facility_id,name,contact_name,email,phone,site_url,order_url,notes,active,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(user['facility_id'],name,body.get('contact_name','').strip(),body.get('email','').strip(),body.get('phone','').strip(),body.get('site_url','').strip(),body.get('order_url','').strip(),body.get('notes','').strip(),1,now()))
            c.commit(); vid=c.execute('SELECT last_insert_rowid() id').fetchone()['id']; c.close(); return self._json({'ok':True,'id':vid})
        if p=='/api/products' and user['role']=='admin':
            try: vendor_id=int(body.get('vendor_id') or 0)
            except: vendor_id=0
            vendor_name=body.get('vendor','').strip(); external_url=body.get('external_url','').strip()
            if vendor_id:
                vr=c.execute('SELECT * FROM vendors WHERE id=? AND facility_id=? AND active=1',(vendor_id,user['facility_id'])).fetchone()
                if vr:
                    vendor_name=vr['name']; external_url=external_url or vr['order_url'] or vr['site_url']
            c.execute('INSERT INTO products(category,name,price,vendor,external_url,description,featured,image_url,vendor_id) VALUES(?,?,?,?,?,?,?,?,?)',(body.get('category','日用品'),body.get('name','').strip(),int(body.get('price') or 0),vendor_name,external_url,body.get('description','').strip(),1 if body.get('featured') else 0,body.get('image_url','').strip(),vendor_id or None)); c.commit(); c.close(); return self._json({'ok':True})
        if p=='/api/invites' and user['role']=='admin':
            code='INV-'+secrets.token_hex(4).upper(); days=int(body.get('days') or 7); uses=int(body.get('max_uses') or 1); exp=(datetime.now(JST)+timedelta(days=days)).isoformat(timespec='seconds')
            c.execute('INSERT INTO invites(code,facility_id,resident_name,relation,expires_at,max_uses,created_at) VALUES(?,?,?,?,?,?,?)',(code,user['facility_id'],body.get('resident_name','').strip(),body.get('relation','家族').strip(),exp,uses,now())); c.commit(); c.close(); return self._json({'ok':True,'code':code})
        c.close(); return self._json({'error':'not_found'},404)

def run():
    init_db(); os.chdir(STATIC); port=int(os.environ.get('PORT','8000')); print(f'ITTOKAI: http://localhost:{port}'); ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
if __name__=='__main__': run()
