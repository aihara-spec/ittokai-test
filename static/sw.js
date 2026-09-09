const CACHE='ittokai-v13-flight';
const SHELL=['/','/styles.css','/app.js','/manifest.webmanifest','/assets/icon-192.png','/assets/icon-512.png','/assets/icon-180.png','/assets/favicon.png','/assets/cards/news-event.svg','/assets/cards/news-important.svg','/assets/cards/product-pants.svg','/assets/cards/product-pad.svg','/assets/cards/product-tissue.svg','/assets/cards/product-jelly.svg'];
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)))});
self.addEventListener('activate',e=>{e.waitUntil((async()=>{for(const k of await caches.keys())if(k!==CACHE)await caches.delete(k);await self.clients.claim()})())});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.pathname.startsWith('/api/'))return;
  e.respondWith((async()=>{
    try{const r=await fetch(e.request);const c=await caches.open(CACHE);c.put(e.request,r.clone());return r}
    catch{return (await caches.match(e.request))||(await caches.match('/'))}
  })());
});
