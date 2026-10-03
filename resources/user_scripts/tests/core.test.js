import {describe, expect, test} from 'bun:test';
import vm from 'node:vm';
import {cancellationSource, matchUrl, registrations, runnerSource, supportedUrl} from '../core.js';
import {validateScript, validateScripts} from '../validation.js';

const script = (changes = {}) => ({id:'test-one', name:'Test script', pattern:'^https://fixture\\.test/watch',
  timing:'start', enabled:true, code:'window.runs = (window.runs || 0) + 1;', ...changes});
function page(url = 'https://fixture.test/watch?a=1', readyState = 'complete') {
  const listeners = new Map(), logs = [], errors = [];
  const context = vm.createContext({URL, location:{href:url}, document:{readyState},
    console:{log:(...args)=>logs.push(args), error:(...args)=>errors.push(args)}});
  context.window=context; context.top=context;
  context.addEventListener = (name, callback) => listeners.set(name, [...(listeners.get(name)||[]), callback]);
  return {context,logs,errors, run:(scripts, revision='one', reason='start')=>vm.runInContext(runnerSource(scripts,revision,reason),context),
    load:()=>{context.document.readyState='complete'; for(const callback of listeners.get('load')||[])callback();}};
}

describe('URL regular expressions and source validation', () => {
  test('matches full JavaScript regex, including query strings and alternation', () => {
    const pattern='^https://(?:www\\.)?youtube\\.com/watch\\?v=(?:AAA|BBB)(?:&.*)?$';
    expect(matchUrl(pattern,'https://www.youtube.com/watch?v=AAA&t=30').matches).toBe(true);
    expect(matchUrl(pattern,'https://www.youtube.com/watch?v=CCC').matches).toBe(false);
    expect(matchUrl(pattern,'https://www.youtube.com/shorts/AAA').matches).toBe(false);
    expect(matchUrl('^https://studio\\.youtube\\.com/video/[^/]+/livestreaming$',
      'https://studio.youtube.com/video/AAA/livestreaming').matches).toBe(true);
  });
  test('blocks internal, extension, file and store URLs even for broad patterns', () => {
    for(const url of ['chrome://settings','chrome-extension://abc/page.html','file:///tmp/a.html','data:text/html,Hi',
      'https://chromewebstore.google.com/detail/test','https://chrome.google.com/webstore']) {
      expect(supportedUrl(url)).toBe(false);
      expect(matchUrl('.*',url)).toMatchObject({matches:false,protected:true});
    }
    expect(matchUrl('.*','https://example.com/').matches).toBe(true);
  });
  test('rejects invalid regex, syntax and wrapper escape before registration', () => {
    expect(()=>validateScript(script({pattern:'['}))).toThrow('URL regex');
    expect(()=>validateScript(script({code:'const = broken'}))).toThrow('JavaScript line 1');
    expect(()=>validateScript(script({code:'}\nwindow.escaped=true;\nfunction another(){'}))).toThrow('one script body');
    expect(()=>validateScripts([script(),script()])).toThrow('Duplicate');
    expect(validateScript(script({code:'return Promise.resolve(1);'})).code).toContain('return');
  });
});

describe('compiled MAIN-world execution', () => {
  test('start and load use MAIN, with no DOM injection or eval', () => {
    const regs=registrations([script(),script({id:'load',timing:'load'})],'one');
    expect(regs).toHaveLength(2);
    expect(regs.every(reg=>reg.world==='MAIN'&&reg.runAt==='document_start'&&!reg.allFrames)).toBe(true);
    expect(regs[0].js[0].code).not.toContain('eval(');
    expect(regs[0].js[0].code).not.toContain('createElement');
  });
  test('page globals and console are shared; local declarations are isolated', () => {
    const p=page(); p.context.pageValue=41;
    p.run([script({code:'const localOnly=99; window.answer=window.pageValue+1; console.log("page log", answer);'})]);
    expect(p.context.answer).toBe(42); expect(p.context.localOnly).toBeUndefined();
    expect(p.logs).toEqual([['page log',42]]);
  });
  test('disabled and nonmatching scripts never run', () => {
    const p=page(); p.run([script({enabled:false}),script({id:'other',pattern:'^https://elsewhere.test/'})]);
    expect(p.context.runs).toBeUndefined();
    expect(registrations([script({enabled:false})],'one')).toEqual([]);
  });
  test('after-load waits while document-start runs immediately', () => {
    const p=page(undefined,'loading');
    p.run([script(),script({id:'load',timing:'load',code:'window.loadState=document.readyState;'})]);
    expect(p.context.runs).toBe(1); expect(p.context.loadState).toBeUndefined();
    p.load(); expect(p.context.loadState).toBe('complete');
  });
  test('same-URL events deduplicate; matching A to nonmatching B to A reruns', () => {
    const p=page(); p.run([script()]); p.run([script()],'one','route');
    expect(p.context.runs).toBe(1);
    p.context.location.href='https://fixture.test/other'; p.run([script()],'one','route');
    expect(p.context.runs).toBe(1);
    p.context.location.href='https://fixture.test/watch?a=1'; p.run([script()],'one','route');
    expect(p.context.runs).toBe(2);
  });
  test('a different matching SPA URL executes again', () => {
    const p=page(); p.run([script()]); p.context.location.href='https://fixture.test/watch?a=2';
    p.run([script()],'one','route'); expect(p.context.runs).toBe(2);
  });
  test('disabling cancels a pending load without cancelling a new revision', () => {
    const p=page(undefined,'loading'); p.run([script({timing:'load'})]);
    vm.runInContext(cancellationSource('two'),p.context); p.load();
    expect(p.context.runs).toBeUndefined();
    const q=page(undefined,'loading'); q.run([script({timing:'load'})],'two');
    vm.runInContext(cancellationSource('two'),q.context); q.load(); expect(q.context.runs).toBe(1);
  });
  test('pending load for an old route is skipped', () => {
    const p=page(undefined,'loading'); p.run([script({timing:'load'})]);
    p.context.location.href='https://fixture.test/other'; p.load(); expect(p.context.runs).toBeUndefined();
  });
  test('A to B to A before load only runs the latest pending callback', () => {
    const p=page(undefined,'loading'), scripts=[script({timing:'load'})];
    p.run(scripts);
    p.context.location.href='https://fixture.test/other';p.run(scripts,'one','route');
    p.context.location.href='https://fixture.test/watch?a=1';p.run(scripts,'one','route');
    p.load();expect(p.context.runs).toBe(1);
  });
  test('queued SPA events remember skipped routes without running on the wrong URL', () => {
    const p=page(), scripts=[script()];p.run(scripts);
    vm.runInContext(runnerSource(scripts,'one','route','https://fixture.test/other'),p.context);
    expect(p.context.runs).toBe(1);
    vm.runInContext(runnerSource(scripts,'one','route',p.context.location.href),p.context);
    expect(p.context.runs).toBe(2);
  });
  test('runtime errors are named and do not prevent another script', async () => {
    const p=page(); p.run([script({code:'throw new Error("sync failure");'}),
      script({id:'async',code:'return Promise.reject(new Error("async failure"));'}),script({id:'good'})]);
    await new Promise(resolve=>setTimeout(resolve,0));
    expect(p.context.runs).toBe(1); expect(p.errors).toHaveLength(2);
    expect(p.errors[0][0]).toBe('[Helium User Scripts: Test script]');
    expect(String(p.errors[1][1])).toContain('async failure');
  });
  test('subframes and protected pages cannot run even a broad regex', () => {
    const p=page('chrome://settings'); p.run([script({pattern:'.*'})]); expect(p.context.runs).toBeUndefined();
    const q=page(); q.context.top={}; q.run([script()]); expect(q.context.runs).toBeUndefined();
  });
  test('a reload uses fresh document state', () => {
    const p=page(), q=page(); p.run([script()]); q.run([script()]);
    expect(p.context.runs).toBe(1); expect(q.context.runs).toBe(1);
  });
});
