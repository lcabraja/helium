import {validateScripts} from '../validation.js';
const KEY='helium-user-scripts-editor-preview-v1';
export async function demoRequest(type: string, body: object) {
  const saved=JSON.parse(localStorage.getItem(KEY)||'{"scripts":[],"revision":"initial","registrationError":""}');
  if(type==='list')return saved;
  if(type==='tabs')return [{id:1,title:'Own test fixture',url:location.origin+'/fixtures/watch?v=AAA'},
    {id:2,title:'A different fixture',url:location.origin+'/fixtures/other'}];
  if(type==='save'){
    const input=body as {scripts:unknown;revision:string};
    if(input.revision!==saved.revision)throw new Error('The preview changed in another window. Reload before saving.');
    const next={scripts:validateScripts(input.scripts),revision:crypto.randomUUID(),registrationError:''};
    localStorage.setItem(KEY,JSON.stringify(next));return next;
  }
  throw new Error('Unknown preview operation.');
}
