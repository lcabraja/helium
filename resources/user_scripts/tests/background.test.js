import {expect,test} from 'bun:test';
const ID='eibeagacednihaofabnkbniopkfjghng', manager=`chrome-extension://${ID}/manager.html`;
let sequence=0;
const script=(extra={})=>({id:'script-a',name:'My script',pattern:'^https://fixture\\.test/',timing:'start',enabled:true,code:'window.myScript=1;',...extra});
async function service(initial={}){
 const events={},data=structuredClone(initial),regs=new Map(),executions=[];
 let failRegistration=false;
 const event=name=>({addListener:fn=>{events[name]=fn;}});
 globalThis.chrome={
  runtime:{id:ID,getURL:path=>`chrome-extension://${ID}/${path}`,onMessage:event('message'),onInstalled:event('installed'),onStartup:event('startup')},
  storage:{local:{get:async keys=>Object.fromEntries(keys.filter(k=>k in data).map(k=>[k,structuredClone(data[k])])),
   set:async values=>Object.assign(data,structuredClone(values)),remove:async key=>{delete data[key];}}},
  userScripts:{getScripts:async()=>[...regs.values()],register:async scripts=>{if(failRegistration)throw Error('permission denied');scripts.forEach(s=>regs.set(s.id,s));},
   update:async scripts=>{if(failRegistration)throw Error('permission denied');scripts.forEach(s=>regs.set(s.id,s));},
   unregister:async({ids})=>ids.forEach(id=>regs.delete(id)),execute:async request=>{executions.push(request);return []; }},
  tabs:{query:async()=>[{id:1,url:'https://fixture.test/',incognito:false},{id:2,url:'chrome://settings',incognito:false},{id:3,url:'https://fixture.test/',incognito:true}],
   get:async id=>({id,incognito:false})},windows:{},action:{onClicked:event('clicked')},
  webNavigation:{onHistoryStateUpdated:event('route'),onReferenceFragmentUpdated:event('fragment')}
 };
 await import('../background.js?test='+sequence++);
 const request=(type,body={})=>new Promise(resolve=>events.message({type,...body},{id:ID,url:manager},resolve));
 await request('list');
 return {data,regs,events,executions,request,fail:()=>{failRegistration=true;}};
}

test('rehydrates persisted scripts and MAIN registration after worker startup',async()=>{
 const s=await service({scripts:[script()],revision:'saved-revision'});
 expect(s.regs.size).toBe(1); expect(s.regs.get('helium-document-start').world).toBe('MAIN');
 expect((await s.request('list')).value.scripts).toHaveLength(1);
});
test('create, update, disable and delete persist and update native registrations',async()=>{
 const s=await service();
 let reply=await s.request('save',{revision:'initial',scripts:[script()]});expect(reply.ok).toBe(true);expect(s.regs.size).toBe(1);
 reply=await s.request('save',{revision:reply.value.revision,scripts:[script({name:'Renamed',enabled:false})]});
 expect(reply.value.scripts[0].name).toBe('Renamed');expect(s.regs.size).toBe(0);
 expect(s.executions.every(e=>e.target.tabId===1)).toBe(true);
 reply=await s.request('save',{revision:reply.value.revision,scripts:[]});
 expect(reply.value.scripts).toEqual([]);expect(s.data.scripts).toEqual([]);
});
test('invalid syntax and a stale editor cannot overwrite existing source',async()=>{
 const original=script();const s=await service({scripts:[original],revision:'existing'});
 expect((await s.request('save',{revision:'initial',scripts:[]})).ok).toBe(false);
 expect((await s.request('save',{revision:'existing',scripts:[script({code:'let = ;'})]})).ok).toBe(false);
 expect(s.data.scripts).toEqual([original]);expect(s.data.revision).toBe('existing');
});
test('registration failure keeps source but removes stale active scripts',async()=>{
 const s=await service({scripts:[script()],revision:'existing'});s.fail();
 const next=script({name:'Edited script',code:'window.myScript=2;'});
 const reply=await s.request('save',{revision:'existing',scripts:[next]});
 expect(reply.ok).toBe(false);expect(reply.error).toContain('Saved, but');expect(s.data.scripts).toEqual([next]);
 expect(s.regs.size).toBe(0);expect(s.data.registrationError).toContain('permission denied');
});
test('corrupt stored source disables injection and reports the startup problem',async()=>{
 const s=await service({scripts:[script({pattern:'['})],revision:'existing'});
 expect(s.regs.size).toBe(0);expect(s.data.registrationError).toContain('URL regex');
});
test('page and foreign extension senders cannot mutate scripts',async()=>{
 const s=await service();let responded=false;
 for(const sender of [{id:ID,url:'https://fixture.test/'},{id:'foreign',url:manager},{}]){
  expect(s.events.message({type:'save',revision:'initial',scripts:[script()]},sender,()=>{responded=true;})).toBeUndefined();
 }
 await s.request('list');expect(responded).toBe(false);expect(s.data.scripts).toBeUndefined();
});
test('SPA events target the exact main-frame document and skip protected routes',async()=>{
 const s=await service({scripts:[script()],revision:'existing'});
 s.events.route({frameId:0,url:'https://fixture.test/watch',tabId:1,documentId:'doc-1'});await s.request('list');
 expect(s.executions).toHaveLength(1);expect(s.executions[0].target).toEqual({tabId:1,documentIds:['doc-1']});
 s.events.route({frameId:2,url:'https://fixture.test/watch',tabId:1,documentId:'doc-2'});
 s.events.fragment({frameId:0,url:'chrome://settings',tabId:1,documentId:'doc-3'});await s.request('list');
 expect(s.executions).toHaveLength(1);
});
