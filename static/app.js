const $=(s,e=document)=>e.querySelector(s);
const app=$('#app');
const initialView=new URLSearchParams(location.search).get('view');
const state={token:localStorage.getItem('cc_token')||'',data:null,view:['home','talk','news','shop','me'].includes(initialView)?initialView:'home',modal:null,activeChatUserId:null};
let installPrompt=null;
let chatPoll=null;
let chatPolling=false;
let appPoll=null;
let appPolling=false;

const ICONS={
 home:'<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10.5V20h13v-9.5"/><path d="M9 20v-6h6v6"/>',
 chat:'<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/><path d="M8 9h8M8 13h5"/>',
 bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/>',
 shop:'<path d="M3 9h18l-1.5 11h-15z"/><path d="m7 9 2-5h6l2 5"/><path d="M9 13v3M15 13v3"/>',
 user:'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
 send:'<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
 gift:'<rect x="3" y="8" width="18" height="13" rx="2"/><path d="M12 8v13M3 12h18"/><path d="M12 8H7.5A2.5 2.5 0 1 1 10 5.5zM12 8h4.5A2.5 2.5 0 1 0 14 5.5z"/>',
 qr:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM18 18h3v3h-3zM18 14h3M14 18v3"/>',
 chevron:'<path d="m9 18 6-6-6-6"/>',
 arrowLeft:'<path d="m15 18-6-6 6-6"/>',
 plus:'<path d="M12 5v14M5 12h14"/>',
 camera:'<path d="M14.5 4 16 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2h3l1.5-3z"/><circle cx="12" cy="13" r="4"/>',
 external:'<path d="M14 3h7v7M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/>',
 shield:'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10"/><path d="m9 12 2 2 4-4"/>',
 logout:'<path d="M10 17l5-5-5-5M15 12H3"/><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
 heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8z"/>',
 building:'<path d="M4 21V4h12v17"/><path d="M16 9h4v12"/><path d="M8 8h4M8 12h4M8 16h4M8 21v-3h4v3"/>',
 package:'<path d="m21 8-9-5-9 5 9 5z"/><path d="m3 8 9 5 9-5M12 13v9"/><path d="m3 8v9l9 5 9-5V8"/>'
};
function icon(name,size=22,cls=''){return `<svg class="ui-icon ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]||ICONS.info}</svg>`}
function toast(t){const e=$('#toast');e.textContent=t;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),1800)}
async function api(path,opt={}){opt.headers={...(opt.headers||{}),'Content-Type':'application/json'};if(state.token)opt.headers.Authorization='Bearer '+state.token;const r=await fetch(path,opt);const j=await r.json();if(!r.ok)throw new Error(j.error||'error');return j}
function esc(s=''){return String(s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function safeImg(url,fallback=''){const u=(url||'').trim();return u?esc(u):fallback}
function dateJP(v){try{return new Date(v).toLocaleDateString('ja-JP',{month:'short',day:'numeric'})}catch{return ''}}
function nav(){const items=[['home','home','ホーム'],['talk','chat','トーク'],['news','bell','お知らせ'],['shop','shop','ショップ'],['me','user','マイページ']];return `<nav class="nav">${items.map(([v,i,l])=>`<button data-view="${v}" class="${state.view===v?'active':''}"><span class="nav-icon">${icon(i,23)}</span><span>${l}</span></button>`).join('')}</nav>`}
function shell(body,title='ITTOKAI'){const d=state.data;return `<div class="shell">${d?.user?.role==='admin'?'<div class="adminbar">施設管理モード</div>':''}<header class="top premium-top"><div class="brand-wrap"><img class="mini-logo" src="/assets/icon-192.png" alt=""><div><div class="eyebrow">${esc(title)}</div><div class="brand">${esc(d?.facility?.name||'ITTOKAI')}</div></div></div><div class="top-actions"><button class="icon-btn" data-view="news" aria-label="お知らせ">${icon('bell',20)}<span class="notify-dot"></span></button><button class="profile-chip" data-view="me"><span>${esc((d?.user?.name||'U')[0])}</span></button></div></header>${body}${nav()}</div>`}
function installBanner(){if(window.matchMedia('(display-mode: standalone)').matches||navigator.standalone)return '';return `<div class="install-card"><img src="/assets/icon-192.png"><div class="install-copy"><b>ホーム画面に追加</b><div class="muted">1タップでITTOKAIを開けます</div></div><button class="btn secondary compact" id="installApp">追加</button></div>`}
function newsImage(x){return safeImg(x.image_url,x.important?'/assets/cards/news-important.svg':'/assets/cards/news-event.svg')}
function productImage(x){return safeImg(x.image_url,'/assets/cards/product-tissue.svg')}

function home(){const d=state.data,n=d.news||[],important=n.find(x=>x.important)||n[0];return shell(`${installBanner()}<main class="content home-content">
<section class="welcome-card"><div class="welcome-copy"><span class="welcome-kicker">WELCOME</span><h1>${esc(d.user.name)} 様</h1><p>${esc(d.user.resident_name||d.facility.name)} の情報をまとめて確認できます。</p></div><div class="welcome-mark">${icon('heart',34)}</div></section>
<div class="quick-row"><button class="action-card" data-view="talk"><span class="action-icon mint">${icon('chat',25)}</span><span><b>施設へ連絡</b><small>メッセージを送る</small></span>${icon('chevron',18,'chev')}</button><button class="action-card" data-view="shop"><span class="action-icon sand">${icon('gift',25)}</span><span><b>商品を送る</b><small>施設へ直接配送</small></span>${icon('chevron',18,'chev')}</button></div>
<div class="section-head"><div><span class="section-kicker">IMPORTANT</span><h2>大切なお知らせ</h2></div><button class="text-link" data-view="news">すべて見る ${icon('chevron',15)}</button></div>
${important?`<article class="featured-news" data-view="news"><img src="${newsImage(important)}" alt=""><div class="featured-overlay"></div><div class="featured-copy"><span class="badge ${important.important?'red':''}">${esc(important.category)}</span><h3>${esc(important.title)}</h3><p>${esc(important.body)}</p><span class="featured-date">${icon('calendar',15)} ${dateJP(important.created_at)}</span></div></article>`:'<div class="empty-card">現在、重要なお知らせはありません</div>'}
<div class="section-head"><div><span class="section-kicker">LATEST</span><h2>最近のお知らせ</h2></div></div>
<div class="news-scroll">${n.slice(0,4).map(x=>`<article class="mini-news-card" data-view="news"><img src="${newsImage(x)}" alt=""><div class="mini-news-body"><span class="badge">${esc(x.category)}</span><h3>${esc(x.title)}</h3><span>${dateJP(x.created_at)}</span></div></article>`).join('')}</div>
</main>`)}

function chatTargetId(){
  if(!state.data)return null;
  if(state.data.user.role!=='admin')return state.data.user.id;
  const users=state.data.family_users||[];
  return Number(state.activeChatUserId||(users[0]&&users[0].id)||0)||null;
}
function chatTarget(){
  const id=chatTargetId();
  return state.data?.user?.role==='admin'?(state.data.family_users||[]).find(x=>Number(x.id)===Number(id)):null;
}
function messageTime(v){try{return new Date(v).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'})}catch{return ''}}
function messageHtml(m){
  const role=state.data.user.role;
  const mine=role==='admin'?m.sender_role==='admin':m.sender_role==='family';
  return `<div class="bubble-wrap ${mine?'me':'them'}"><div class="bubble ${mine?'me':'them'}">${esc(m.body)}<div class="message-meta"><span>${messageTime(m.created_at)}</span>${mine?`<span class="read-state ${m.read_at?'is-read':''}">${m.read_at?'既読':'送信済み'}</span>`:''}</div></div></div>`;
}
function talk(){
  const d=state.data,msgs=d.messages||[],last=msgs.length?msgs[msgs.length-1]:null;
  if(d.user.role==='admin'){
    const families=d.family_users||[];
    return shell(`<main class="content"><div class="page-intro"><span class="section-kicker">MESSAGES</span><h1>トーク</h1><p>家族ごとに会話を確認できます。</p></div><div class="conversation-list">${families.length?families.map(u=>`<button type="button" class="conversation-card" data-chat-user="${u.id}"><div class="avatar">${esc((u.name||'家')[0])}</div><div class="conversation-copy"><div class="row between"><b>${esc(u.name)}</b><span class="time-mini">家族</span></div><p>${esc(u.resident_name||'利用者未設定')} ${u.relation?'・'+esc(u.relation):''}</p></div>${icon('chevron',18,'chev')}</button>`).join(''):'<div class="empty">登録された家族がまだいません</div>'}</div></main>`,'トーク');
  }
  return shell(`<main class="content"><div class="page-intro"><span class="section-kicker">MESSAGES</span><h1>トーク</h1><p>施設とリアルタイムで連絡できます。</p></div><div class="conversation-list"><button type="button" class="conversation-card" data-chat-user="${d.user.id}"><div class="avatar facility-avatar">${icon('home',23)}</div><div class="conversation-copy"><div class="row between"><b>${esc(d.facility.name)}</b><span class="time-mini">オンライン</span></div><p>${esc(last?.body||'メッセージはありません')}</p></div>${icon('chevron',18,'chev')}</button></div></main>`,'トーク');
}
function chat(){
  const m=state.data.messages||[],target=chatTarget();
  const title=state.data.user.role==='admin'?(target?.name||'家族'):state.data.facility.name;
  const sub=state.data.user.role==='admin'?`${target?.resident_name||''}${target?.relation?'・'+target.relation:''}`:'施設と接続中';
  return `<div class="shell chat-shell"><header class="chat-top"><button type="button" class="icon-btn chat-back" data-back aria-label="戻る">${icon('arrowLeft',24)}</button><div class="chat-title"><div class="avatar facility-avatar small">${state.data.user.role==='admin'?esc((target?.name||'家')[0]):icon('home',18)}</div><div><b>${esc(title)}</b><span>${esc(sub)}</span></div></div><button type="button" class="icon-btn" aria-label="情報">${icon('info',21)}</button></header><div class="chat" id="chatMessages">${m.map(messageHtml).join('')}</div><form class="composer" id="msgForm"><button type="button" class="composer-add" aria-label="追加">${icon('plus',20)}</button><input class="field" name="body" autocomplete="off" placeholder="メッセージを入力"><button type="submit" class="send-btn" aria-label="送信">${icon('send',20)}</button></form></div>`;
}
function news(){const n=state.data.news||[];return shell(`<main class="content"><div class="page-intro row between align-start"><div><span class="section-kicker">NEWS</span><h1>お知らせ</h1><p>施設からの最新情報です。</p></div>${state.data.user.role==='admin'?`<button class="round-add" data-modal="newsCreate">${icon('plus',21)}</button>`:''}</div><div class="news-list">${n.map(x=>`<article class="news-card"><img src="${newsImage(x)}" alt=""><div class="news-card-body"><div class="row between"><span class="badge ${x.important?'red':''}">${esc(x.category)}</span><span class="muted tiny">${dateJP(x.created_at)}</span></div><h3>${esc(x.title)}</h3><p>${esc(x.body)}</p></div></article>`).join('')}</div></main>`,'お知らせ')}
function shop(){const p=state.data.products||[];return shell(`<main class="content"><div class="page-intro row between align-start"><div><span class="section-kicker">SHOP</span><h1>施設へお届け</h1><p>必要な商品を施設へ直接送れます。</p></div>${state.data.user.role==='admin'?`<button class="round-add" data-modal="productCreate">${icon('plus',21)}</button>`:''}</div><div class="shop-banner"><div><span>CARE DELIVERY</span><h2>施設への配送先入力は不要です</h2><p>登録施設を配送先として選択できます。</p></div>${icon('package',50)}</div><div class="product-grid">${p.map(x=>`<article class="product"><div class="product-media"><img src="${productImage(x)}" alt="${esc(x.name)}">${x.featured?'<span class="featured-tag">おすすめ</span>':''}</div><div class="product-body"><span class="product-category">${esc(x.category)}</span><h3>${esc(x.name)}</h3><div class="price">¥${Number(x.price).toLocaleString()}</div><div class="vendor">${esc(x.vendor)}</div><button class="product-button" data-buy="${x.id}">商品を見る ${icon('chevron',16)}</button></div></article>`).join('')}</div></main>`,'ショップ')}
function me(){const u=state.data.user;const vendors=state.data.vendors||[];return shell(`<main class="content"><div class="page-intro"><span class="section-kicker">ACCOUNT</span><h1>マイページ</h1></div><section class="profile-card"><div class="profile-avatar">${esc(u.name[0])}</div><div><h2>${esc(u.name)}</h2><p>${esc(u.email)}</p><span class="verified">${icon('shield',15)} 登録済み</span></div></section><section class="settings-card"><div class="setting-row"><span class="setting-icon">${icon('home',20)}</span><div><small>利用施設</small><b>${esc(state.data.facility.name)}</b></div></div><div class="setting-row"><span class="setting-icon">${icon('user',20)}</span><div><small>登録利用者</small><b>${esc(u.resident_name||'-')} ${u.relation?'（'+esc(u.relation)+'）':''}</b></div></div><button class="setting-action" data-modal="qrAdd"><span class="setting-icon">${icon('qr',20)}</span><div><b>QRコードで追加・登録</b><small>施設や利用者とつながる</small></div>${icon('chevron',18,'chev')}</button><a class="setting-action manual-link" href="/MANUAL.html" target="_blank"><span class="setting-icon">${icon('info',20)}</span><div><b>操作マニュアル</b><small>お知らせ・ショップ・協賛企業の登録方法</small></div>${icon('external',18,'chev')}</a></section>${u.role==='admin'?`<section class="settings-card admin-section"><div class="section-head compact-head"><div><span class="section-kicker">VENDOR</span><h2>協賛企業管理</h2></div><button class="btn compact" data-modal="vendorCreate">${icon('plus',17)} 企業登録</button></div>${vendors.length?vendors.map(v=>`<div class="vendor-row"><div><b>${esc(v.name)}</b><small>${esc(v.contact_name||'担当者未登録')} ${v.email?' / '+esc(v.email):''}</small><small>${v.order_url?'購入URL登録済み':'購入URL未登録'}</small></div><span class="status-pill ${v.active?'on':''}">${v.active?'利用中':'停止'}</span></div>`).join(''):'<div class="empty-card">協賛企業はまだ登録されていません</div>'}</section><section class="settings-card admin-section"><div class="section-head compact-head"><div><span class="section-kicker">ADMIN</span><h2>施設管理</h2></div><button class="btn compact" data-modal="inviteCreate">${icon('qr',17)} 招待QR</button></div>${state.data.invites.map(i=>`<div class="invite-row"><div><b>${esc(i.resident_name)}</b><small>${esc(i.relation)} / 使用 ${i.used_count}/${i.max_uses}</small></div><button class="icon-btn soft" data-showqr="${esc(i.code)}">${icon('qr',19)}</button></div>`).join('')}</section>`:''}<button class="logout-button" id="logout">${icon('logout',19)} ログアウト</button></main>`,'マイページ')}
function modal(type,payload){let c='';
if(type==='newsCreate')c=`<div class="sheet-heading"><span class="sheet-icon">${icon('bell',21)}</span><div><span>NEWS</span><h2>ニュース配信</h2></div></div><form id="newsForm" class="stack"><label>カテゴリ<input class="field" name="category" placeholder="例：重要・イベント・施設だより" value="お知らせ"></label><label>タイトル<input class="field" name="title" placeholder="例：敬老会開催のお知らせ" required></label><label>本文<textarea class="field" name="body" placeholder="ご家族に伝える内容を入力" rows="5" required></textarea></label><label>写真URL<input class="field" name="image_url" placeholder="https://...（空欄でもOK）"></label><label class="check-row"><input type="checkbox" name="important"> 重要なお知らせとしてホーム上部に表示</label><div class="form-help">「配信する」を押すと、同じ施設に登録された家族側へ自動反映されます。</div><button class="btn">配信する</button></form>`;
if(type==='vendorCreate')c=`<div class="sheet-heading"><span class="sheet-icon">${icon('building',21)}</span><div><span>VENDOR</span><h2>協賛企業登録</h2></div></div><form id="vendorForm" class="stack"><label>会社名<input class="field" name="name" placeholder="例：〇〇株式会社" required></label><label>担当者名<input class="field" name="contact_name" placeholder="例：営業部 山田様"></label><label>メールアドレス<input class="field" name="email" type="email" placeholder="sales@example.co.jp"></label><label>電話番号<input class="field" name="phone" placeholder="03-0000-0000"></label><label>会社ホームページ<input class="field" name="site_url" type="url" placeholder="https://company.example.jp/"></label><label>購入・注文ページURL<input class="field" name="order_url" type="url" placeholder="https://shop.example.jp/"></label><label>備考<textarea class="field" name="notes" rows="3" placeholder="最低ロット、送料、担当者情報など"></textarea></label><div class="form-help">先に協賛企業を登録すると、商品登録画面で販売会社を選べます。購入URLも自動利用できます。</div><button class="btn">企業を登録する</button></form>`;
if(type==='productCreate'){const vendors=state.data.vendors||[];c=`<div class="sheet-heading"><span class="sheet-icon">${icon('shop',21)}</span><div><span>SHOP</span><h2>商品登録</h2></div></div><form id="productForm" class="stack"><label>カテゴリ<input class="field" name="category" value="日用品" placeholder="例：オムツ・食品・日用品"></label><label>商品名<input class="field" name="name" placeholder="例：リハビリパンツ M" required></label><label>販売価格（税込・円）<input class="field" name="price" type="number" min="0" placeholder="2980" required></label><label>協賛・販売会社<select class="field" name="vendor_id" id="vendorSelect"><option value="">会社を選択してください</option>${vendors.map(v=>`<option value="${v.id}" data-order="${esc(v.order_url||v.site_url||'')}">${esc(v.name)}</option>`).join('')}</select></label>${vendors.length?'':'<div class="form-help warn">協賛企業が未登録です。マイページ → 協賛企業管理 → 企業登録 を先に行ってください。</div>'}<label>外部購入URL<input class="field" name="external_url" id="productExternalUrl" placeholder="企業登録済みなら自動入力できます"></label><label>商品写真URL<input class="field" name="image_url" placeholder="https://...（空欄でもOK）"></label><label>商品説明<textarea class="field" name="description" rows="4" placeholder="サイズ、入り数、特徴、配送条件など"></textarea></label><label class="check-row"><input type="checkbox" name="featured"> おすすめ商品として表示</label><div class="form-help">購入ボタンを押すと「外部購入URL」に登録した協賛会社のサイトへ移動します。</div><button class="btn">商品を登録する</button></form>`}
if(type==='inviteCreate')c=`<div class="sheet-heading"><span class="sheet-icon">${icon('qr',21)}</span><div><span>INVITE</span><h2>招待QR発行</h2></div></div><form id="inviteForm" class="stack"><input class="field" name="resident_name" placeholder="利用者氏名" required><input class="field" name="relation" value="家族" placeholder="続柄"><input class="field" name="days" type="number" value="7" min="1" placeholder="有効日数"><input class="field" name="max_uses" type="number" value="1" min="1" placeholder="使用回数"><button class="btn">QRを発行</button></form>`;
if(type==='showqr'){const base=location.origin+'/register?invite='+encodeURIComponent(payload);c=`<div class="sheet-heading"><span class="sheet-icon">${icon('qr',21)}</span><div><span>INVITE</span><h2>招待QR</h2></div></div><div class="qrbox"><img src="/api/qr?data=${encodeURIComponent(base)}"><p><b>${esc(payload)}</b></p><div class="muted">このQRを登録するご家族に読み取ってもらってください。</div></div>`}
if(type==='qrAdd')c=`<div class="sheet-heading"><span class="sheet-icon">${icon('camera',21)}</span><div><span>CONNECT</span><h2>QRで追加・登録</h2></div></div><p class="muted">カメラをQRコードに向けてください。</p><div class="camera"><video id="qrVideo" autoplay playsinline></video><div class="scanner-frame"></div></div><div class="stack" style="margin-top:14px"><div class="or-line"><span>または</span></div><input class="field" id="manualInvite" placeholder="招待コードを入力"><button class="btn secondary" id="manualInviteBtn">コードを確認</button></div>`;
return `<div class="modal"><div class="sheet"><button class="close" data-close>×</button>${c}</div></div>`}
function productModal(p){return `<div class="modal"><div class="sheet product-sheet"><button class="close" data-close2>×</button><div class="product-detail-media"><img src="${productImage(p)}" alt="${esc(p.name)}"></div><span class="product-category">${esc(p.category)}</span><h2>${esc(p.name)}</h2><p>${esc(p.description)}</p><div class="detail-price">¥${Number(p.price).toLocaleString()}</div><p class="muted">販売元：${esc(p.vendor)}</p><div class="delivery-box"><span>${icon('home',20)}</span><div><small>配送先</small><b>${esc(state.data.facility.name)}</b><p>施設へ直接送付</p></div>${icon('shield',19)}</div><button class="btn full" id="externalBuy">協賛会社サイトで購入 ${icon('external',17)}</button></div></div>`}
function render(){
  if(chatPoll){clearInterval(chatPoll);chatPoll=null}
  if(!state.token)return renderAuth();
  if(!state.data){app.innerHTML='<div class="auth loading">読み込み中...</div>';return}
  const v=state.view==='home'?home():state.view==='talk'?talk():state.view==='chat'?chat():state.view==='news'?news():state.view==='shop'?shop():me();
  app.innerHTML=v+(state.modal?modal(state.modal.type,state.modal.payload):'');bind();
  if(state.modal?.type==='qrAdd')startScanner();
  if(state.view==='chat'){setTimeout(()=>{scrollChat(true);markRead();startChatPolling()},0)}
}
function renderAuth(){const invite=new URLSearchParams(location.search).get('invite')||'';app.innerHTML=`<div class="auth premium-auth"><div class="auth-brand"><img src="/assets/icon-192.png" alt="ITTOKAI"><h1>ITTOKAI</h1><p>一燈会とご家族を、もっと近くに。</p></div><div class="tabs"><button class="on" data-auth-tab="login">ログイン</button><button data-auth-tab="register">新規登録</button></div><form id="loginForm" class="stack auth-form"><label>メールアドレス<input class="field" name="email" type="email" value="family@ittokai.local" required></label><label>パスワード<input class="field" name="password" type="password" value="demo1234" required></label><button class="btn full">ログイン</button><div class="demo-box"><b>デモログイン</b><span>家族：family@ittokai.local / demo1234</span><span>管理者：admin@ittokai.local / admin1234</span></div></form><form id="registerForm" class="stack auth-form" style="display:none"><input class="field" name="invite" placeholder="招待コード" value="${esc(invite)}" required><input class="field" name="name" placeholder="氏名" required><input class="field" name="email" type="email" placeholder="メールアドレス" required><input class="field" name="phone" placeholder="電話番号"><input class="field" name="password" type="password" placeholder="パスワード" required><button class="btn full">登録する</button></form><div class="legal-links"><a href="/privacy" target="_blank">プライバシーポリシー</a><span>・</span><a href="/terms" target="_blank">利用規約</a></div></div>`;bindAuth();if(invite)$('[data-auth-tab="register"]').click()}
function bindAuth(){document.querySelectorAll('[data-auth-tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-auth-tab]').forEach(x=>x.classList.toggle('on',x===b));$('#loginForm').style.display=b.dataset.authTab==='login'?'grid':'none';$('#registerForm').style.display=b.dataset.authTab==='register'?'grid':'none'});$('#loginForm').onsubmit=async e=>{e.preventDefault();const o=Object.fromEntries(new FormData(e.target));try{const r=await api('/api/login',{method:'POST',body:JSON.stringify(o)});state.token=r.token;localStorage.setItem('cc_token',r.token);await load()}catch{toast('ログイン情報を確認してください')}};$('#registerForm').onsubmit=async e=>{e.preventDefault();const o=Object.fromEntries(new FormData(e.target));try{const r=await api('/api/register',{method:'POST',body:JSON.stringify(o)});state.token=r.token;localStorage.setItem('cc_token',r.token);history.replaceState({},'',location.pathname);await load();toast('登録しました')}catch(err){toast('登録できません：'+err.message)}}}
function setView(v,push=true){
  state.view=v;state.modal=null;
  if(push){try{history.pushState({view:v},'',location.pathname+'?view='+encodeURIComponent(v))}catch{}}
  render();
}
function openChat(userId){
  if(userId)state.activeChatUserId=Number(userId);
  setView('chat',true);
}
function bind(){
  const ib=$('#installApp');if(ib)ib.onclick=async()=>{if(installPrompt){installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;render()}else alert(/iphone|ipad|ipod/i.test(navigator.userAgent)?'Safariの共有ボタン →「ホーム画面に追加」を選んでください。':'ブラウザのメニューから「ホーム画面に追加」または「アプリをインストール」を選んでください。')};
  document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>setView(b.dataset.view,true));
  document.querySelectorAll('[data-chat-user]').forEach(b=>b.onclick=()=>openChat(b.dataset.chatUser));
  const back=$('[data-back]');if(back)back.onclick=()=>setView('talk',true);
  document.querySelectorAll('[data-modal]').forEach(b=>b.onclick=()=>{state.modal={type:b.dataset.modal};render()});
  if($('[data-close]'))$('[data-close]').onclick=()=>{state.modal=null;render()};
  document.querySelectorAll('[data-showqr]').forEach(b=>b.onclick=()=>{state.modal={type:'showqr',payload:b.dataset.showqr};render()});
  if($('#logout'))$('#logout').onclick=()=>{localStorage.removeItem('cc_token');state.token='';state.data=null;state.activeChatUserId=null;render()};
  if($('#msgForm'))$('#msgForm').onsubmit=async e=>{e.preventDefault();const input=e.target.elements.body;const text=(input.value||'').trim();if(!text)return;input.disabled=true;try{await api('/api/messages',{method:'POST',body:JSON.stringify({body:text,user_id:chatTargetId()})});input.value='';await refreshMessages(true)}catch{toast('送信できませんでした')}finally{input.disabled=false;input.focus()}};
  if($('#newsForm'))$('#newsForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),o=Object.fromEntries(f);o.important=f.get('important')==='on';await api('/api/news',{method:'POST',body:JSON.stringify(o)});state.modal=null;await load();toast('配信しました')};
  if($('#vendorForm'))$('#vendorForm').onsubmit=async e=>{e.preventDefault();const o=Object.fromEntries(new FormData(e.target));await api('/api/vendors',{method:'POST',body:JSON.stringify(o)});state.modal=null;await load();toast('協賛企業を登録しました')};
  const vendorSelect=$('#vendorSelect'), extUrl=$('#productExternalUrl');if(vendorSelect&&extUrl)vendorSelect.onchange=()=>{const op=vendorSelect.selectedOptions[0];if(op?.dataset?.order&&!extUrl.value)extUrl.value=op.dataset.order};
  if($('#productForm'))$('#productForm').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),o=Object.fromEntries(f);o.featured=f.get('featured')==='on';await api('/api/products',{method:'POST',body:JSON.stringify(o)});state.modal=null;await load();toast('商品を登録しました')};
  if($('#inviteForm'))$('#inviteForm').onsubmit=async e=>{e.preventDefault();const o=Object.fromEntries(new FormData(e.target));const r=await api('/api/invites',{method:'POST',body:JSON.stringify(o)});await load();state.modal={type:'showqr',payload:r.code};render();toast('招待QRを発行しました')};
  document.querySelectorAll('[data-buy]').forEach(b=>b.onclick=()=>{const p=state.data.products.find(x=>x.id==b.dataset.buy);app.insertAdjacentHTML('beforeend',productModal(p));$('[data-close2]').onclick=()=>render();$('#externalBuy').onclick=()=>window.open(p.external_url,'_blank')})
}
function scrollChat(force=false){const el=$('#chatMessages');if(!el)return;if(force||el.scrollHeight-el.scrollTop-el.clientHeight<180)el.scrollTop=el.scrollHeight}
async function markRead(){if(state.view!=='chat'||!chatTargetId())return;try{await api('/api/messages/read',{method:'POST',body:JSON.stringify({user_id:chatTargetId()})})}catch{}}
async function refreshMessages(forceScroll=false){
  if(chatPolling||state.view!=='chat'||!chatTargetId())return;chatPolling=true;
  try{
    const r=await api('/api/messages?user_id='+encodeURIComponent(chatTargetId()));
    const old=JSON.stringify((state.data.messages||[]).map(x=>[x.id,x.read_at]));
    const neu=JSON.stringify((r.messages||[]).map(x=>[x.id,x.read_at]));
    state.data.messages=r.messages||[];
    if(old!==neu){const el=$('#chatMessages');if(el){const near=el.scrollHeight-el.scrollTop-el.clientHeight<180;el.innerHTML=state.data.messages.map(messageHtml).join('');scrollChat(forceScroll||near)}}
    await markRead();
  }catch(e){}finally{chatPolling=false}
}
function startChatPolling(){if(chatPoll)clearInterval(chatPoll);chatPoll=setInterval(()=>refreshMessages(false),1200);refreshMessages(true)}
async function startScanner(){const video=$('#qrVideo'),manual=$('#manualInvite'),btn=$('#manualInviteBtn');btn.onclick=()=>checkInvite(manual.value.trim());if(!('BarcodeDetector'in window)){toast('自動QR認識に未対応です。招待コードを入力してください');return}try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'}});video.srcObject=stream;const det=new BarcodeDetector({formats:['qr_code']});const timer=setInterval(async()=>{if(!document.body.contains(video)){clearInterval(timer);stream.getTracks().forEach(t=>t.stop());return}try{const r=await det.detect(video);if(r[0]){const raw=r[0].rawValue,m=raw.match(/[?&]invite=([^&]+)/);checkInvite(m?decodeURIComponent(m[1]):raw);clearInterval(timer);stream.getTracks().forEach(t=>t.stop())}}catch{}},700)}catch{toast('カメラを利用できません')}}
async function checkInvite(code){try{const i=await api('/api/invite?code='+encodeURIComponent(code));alert(`${i.facility_name}\n利用者: ${i.resident_name}\n続柄: ${i.relation}\n状態: ${i.valid?'有効':'無効'}`)}catch{toast('招待コードが見つかりません')}}
async function refreshAppData(){
  if(appPolling||!state.token||!state.data||state.view==='chat'||state.modal)return;appPolling=true;
  try{
    const r=await api('/api/sync');
    const oldNews=JSON.stringify((state.data.news||[]).map(x=>[x.id,x.title,x.body,x.important,x.image_url]));
    const newNews=JSON.stringify((r.news||[]).map(x=>[x.id,x.title,x.body,x.important,x.image_url]));
    const oldProducts=JSON.stringify((state.data.products||[]).map(x=>[x.id,x.name,x.price,x.vendor,x.external_url,x.featured,x.image_url]));
    const newProducts=JSON.stringify((r.products||[]).map(x=>[x.id,x.name,x.price,x.vendor,x.external_url,x.featured,x.image_url]));
    const oldVendors=JSON.stringify((state.data.vendors||[]).map(x=>[x.id,x.name,x.order_url,x.active]));
    const newVendors=JSON.stringify((r.vendors||[]).map(x=>[x.id,x.name,x.order_url,x.active]));
    if(oldNews!==newNews||oldProducts!==newProducts||oldVendors!==newVendors){state.data.news=r.news||[];state.data.products=r.products||[];if(state.data.user.role==='admin')state.data.vendors=r.vendors||[];render()}
  }catch(e){}finally{appPolling=false}
}
function startAppPolling(){if(appPoll)clearInterval(appPoll);appPoll=setInterval(refreshAppData,1800)}
async function load(){try{state.data=await api('/api/bootstrap');if(state.data.user.role==='admin'&&!state.activeChatUserId){const u=(state.data.family_users||[])[0];state.activeChatUserId=u?u.id:null}render();startAppPolling()}catch{localStorage.removeItem('cc_token');state.token='';state.data=null;render()}}
if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
try{history.replaceState({view:state.view},'',location.pathname+'?view='+encodeURIComponent(state.view))}catch{}
window.addEventListener('popstate',e=>{const v=e.state?.view;if(v&&['home','talk','chat','news','shop','me'].includes(v)){state.view=v;state.modal=null;render()}else if(state.token){state.view='home';render()}});
if(state.token)load();else render();
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e});
window.addEventListener('appinstalled',()=>{installPrompt=null;toast('ITTOKAIをインストールしました')});
window.addEventListener('load',()=>setTimeout(()=>document.querySelector('#startup-splash')?.classList.add('hide'),450));
