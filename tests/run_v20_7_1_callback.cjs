const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(__dirname+'/../static/app.js','utf8');
const fn=source.slice(source.indexOf('async function completeLineLink('));
(async()=>{
let checks=0;
for(const role of ['family','staff','middle_manager','admin','hq','caredo','sponsor']){
 const store=new Map(),calls=[];
 const state={data:{user:{id:role},line_notification:{liff_id:'configured'}},token:'session'};
 let logged=false;
 const c={state,sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},window:{liff:{}},liff:{init:async()=>{},isLoggedIn:()=>logged,login:o=>calls.push(o),getIDToken:()=> 'id-token'},location:{origin:'https://app.test',pathname:'/'},api:async(path,opt)=>{calls.push(path);return path.endsWith('bootstrap')?{user:{id:role},line_notification:{linked:true,liff_id:"configured"}}:{linked:true}},render:()=>{},toast:()=>{},Date,JSON,Error};
 vm.createContext(c);vm.runInContext(fn,c);
 await c.completeLineLink(true);assert(store.size===1);assert(calls[0].redirectUri==='https://app.test/?view=me');checks+=2;
 logged=true;await c.completeLineLink(false);assert(state.data.line_notification.linked);assert(store.size===0);assert(calls.includes('/api/line/link'));checks+=3;
 c.api=async()=>{throw Error('LINE_SAVE_FAILED')};await c.completeLineLink(true);assert(state.lineError.includes('LINE_SAVE_FAILED'));checks++;
 store.set('ittokai_line_pending',JSON.stringify({uid:'different-user',at:Date.now()}));await c.completeLineLink(false);assert(state.lineError.includes('ログインユーザー'));checks++;
}
const report={version:'20.7.1',result:'PASS',assertions:checks,scope:'LIFF redirect/resume/UI failure/session user binding; mocked SDK and API, Node VM'};
fs.writeFileSync(__dirname+'/../TEST_RESULT_v20.7.1_UI.json',JSON.stringify(report,null,2));console.log(report);
})().catch(e=>{console.error(e);process.exitCode=1});

