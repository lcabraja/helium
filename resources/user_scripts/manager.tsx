import React, {useEffect, useMemo, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import {Theme} from '@astryxdesign/core/theme';
import {neutralTheme} from '@astryxdesign/theme-neutral/built';
import {SidebarLayout} from '@da-facility/ui';
import '@da-facility/ui/style.css';
import {matchUrl, supportedUrl} from './core.js';
import {validateScript} from './validation.js';
import './manager.css';

type Script = {id: string; name: string; pattern: string; timing: 'start' | 'load'; enabled: boolean; code: string};
type Snapshot = {scripts: Script[]; revision: string; registrationError: string};
type Tab = {id: number; title: string; url: string};

async function request<T>(type: string, body: object = {}): Promise<T> {
  if (import.meta.env.MODE === 'demo') {
    const {demoRequest} = await import('./preview/demo-service');
    return demoRequest(type, body) as Promise<T>;
  }
  const reply = await chrome.runtime.sendMessage({type, ...body});
  if (!reply?.ok) throw new Error(reply?.error || 'The script service did not respond. Reopen this page.');
  return reply.value;
}

const exactRegex = (url: string) => '^' + url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$';
const EXAMPLES = [
  {name: 'YouTube watch page', pattern: '^https://www\\.youtube\\.com/watch\\?v=VIDEO_ID(?:&.*)?$',
    code: '// Replace VIDEO_ID in the URL regex, then enable this script.\nconsole.log("My YouTube tweak", location.href);\ndocument.documentElement.dataset.heliumTweak = "enabled";'},
  {name: 'YouTube Studio livestream', pattern: '^https://studio\\.youtube\\.com/video/[^/?#]+/livestreaming(?:[?#].*)?$',
    code: 'console.log("Livestream tools ready", location.href);\n// Add your page changes here. Runs again when the route changes.'},
];

function App() {
  const [state, setState] = useState<Snapshot>({scripts: [], revision: 'initial', registrationError: ''});
  const [draft, setDraft] = useState<Script | null>(null);
  const [query, setQuery] = useState('');
  const [testUrl, setTestUrl] = useState(new URL(location.href).searchParams.get('url') || 'https://www.youtube.com/watch?v=VIDEO_ID');
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(true);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const deleteDialog = useRef<HTMLDialogElement>(null);
  const [dark, setDark] = useState(matchMedia('(prefers-color-scheme: dark)').matches);
  const persisted = state.scripts.find(script => script.id === draft?.id);
  const dirty = !!draft && JSON.stringify(draft) !== JSON.stringify(persisted);
  const validation = useMemo(() => {
    if (!draft) return '';
    try { validateScript(draft); return ''; } catch (error) { return (error as Error).message; }
  }, [draft]);
  const match = draft ? matchUrl(draft.pattern, testUrl) : null;
  const shown = state.scripts.filter(script => script.name.toLowerCase().includes(query.toLowerCase()));

  useEffect(() => {
    let active = true;
    const refreshTabs = () => {
      if (document.visibilityState !== 'visible') return;
      request<Tab[]>('tabs').then(open => { if (active) setTabs(open); })
        .catch(error => { if (active) setError('Could not refresh open tabs: ' + error.message); });
    };
    document.addEventListener('visibilitychange', refreshTabs);
    window.addEventListener('focus', refreshTabs);
    Promise.all([request<Snapshot>('list'), request<Tab[]>('tabs')]).then(([saved, open]) => {
      setState(saved); setTabs(open); if (saved.scripts[0]) setDraft(saved.scripts[0]);
    }).catch(error => setError(error.message)).finally(() => setBusy(false));
    const media = matchMedia('(prefers-color-scheme: dark)');
    const changed = () => setDark(media.matches);
    media.addEventListener('change', changed);
    return () => {
      active = false;
      media.removeEventListener('change', changed);
      document.removeEventListener('visibilitychange', refreshTabs);
      window.removeEventListener('focus', refreshTabs);
    };
  }, []);
  useEffect(() => {
    if (!dirty) return;
    const unload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    addEventListener('beforeunload', unload);
    return () => removeEventListener('beforeunload', unload);
  }, [dirty]);
  const canLeave = () => !dirty || confirm('Discard your unsaved changes?');
  useEffect(() => { if (deleteOpen) deleteDialog.current?.showModal(); }, [deleteOpen]);
  function choose(script: Script) {
    if (!canLeave()) return;
    setDraft({...script}); setError(''); setNotice('');
  }
  function create(example?: typeof EXAMPLES[number]) {
    if (!canLeave()) return;
    setDraft({id: crypto.randomUUID(), name: example?.name || 'Untitled script',
      pattern: example?.pattern || (supportedUrl(testUrl) ? exactRegex(testUrl) : '^https://example\\.com/'),
      timing: 'load', enabled: false,
      code: example?.code || 'console.log("Hello from Helium", location.href);'});
    setError(''); setNotice('New scripts start disabled.');
  }
  async function save() {
    if (!draft) return;
    if (validation) { setError(validation); return; }
    setBusy(true); setError(''); setNotice('');
    try {
      const scripts = persisted ? state.scripts.map(script => script.id === draft.id ? draft : script) : [...state.scripts, draft];
      const saved = await request<Snapshot>('save', {scripts, revision: state.revision});
      setState(saved); setDraft(saved.scripts.find(script => script.id === draft.id) || null);
      setNotice(import.meta.env.MODE === 'demo' ? 'Saved in this editor preview. The native app runs scripts on websites.' :
        draft.enabled ? 'Saved and enabled. Reload matching pages to apply this version.' : 'Saved. This script is disabled.');
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!draft) return;
    setBusy(true); setDeleteOpen(false); setError('');
    try {
      const saved = await request<Snapshot>('save', {scripts: state.scripts.filter(script => script.id !== draft.id), revision: state.revision});
      setState(saved); setDraft(saved.scripts[0] || null); setNotice('Script deleted. Reload pages to undo changes it already made.');
    } catch (error) { setError((error as Error).message); }
    finally { setBusy(false); }
  }
  function edit(changes: Partial<Script>) { if (draft) { setDraft({...draft, ...changes}); setNotice(''); } }
  const navigation = <div className="script-navigation">
    <label className="sr-only" htmlFor="script-search">Search scripts</label>
    <input id="script-search" type="search" placeholder="Search scripts" value={query} onChange={event => setQuery(event.target.value)}/>
    <div className="navigation-label">YOUR SCRIPTS <span>{state.scripts.length}</span></div>
    {shown.map(script => <button key={script.id} className={'script-link ' + (draft?.id === script.id ? 'selected' : '')}
      onClick={() => choose(script)} aria-current={draft?.id === script.id ? 'page' : undefined}>
      <span className={'status-dot ' + (script.enabled ? 'on' : '')}/><span>{script.name}</span>
    </button>)}
    {!shown.length && <p className="muted navigation-empty">{query ? 'No matching scripts.' : 'Your scripts will appear here.'}</p>}
  </div>;
  return <Theme theme={neutralTheme} mode={dark ? 'dark' : 'light'}>
    <SidebarLayout title="User Scripts" navigation={navigation} navigationLabel="Scripts"
      navigationHeader={<div className="brand"><span className="brand-icon">{'</>'}</span><span>Helium<span className="brand-caption">Personal scripts</span></span></div>}
      navigationFooter={<div className="navigation-footer"><span className="status-dot on"/>{state.scripts.filter(script => script.enabled).length} enabled · stored in this profile</div>}
      navigationKey={draft?.id} headerActions={<button className="primary" onClick={() => create()} disabled={busy}>+ New script</button>}
      footer={draft && <div className="save-bar"><span className="muted">{dirty ? 'Unsaved changes' : 'All changes saved'}</span><div><button className="danger-text" disabled={busy} onClick={() => persisted ? setDeleteOpen(true) : setDraft(null)}>Delete</button><button className="primary" onClick={save} disabled={busy || !dirty}>{busy ? 'Saving…' : 'Save script'}</button></div></div>}>
      <div className="workspace">
        {import.meta.env.MODE === 'demo' && <div className="message demo-note">Interactive preview. Scripts are saved in this browser for trying the editor. They do not run on websites here. <a href="/">Get the native Helium build</a> for execution.</div>}
        {(error || state.registrationError) && <div role="alert" className="message error">{error || state.registrationError}</div>}
        {notice && <div role="status" className="message success">{notice}</div>}
        {!draft ? <section className="welcome"><div className="eyebrow">YOUR BROWSER, YOUR CHANGES</div><h1>Make this page yours.</h1><p>Run your JavaScript on the pages you choose. A small tweak, a missing shortcut, a quieter workspace.</p><button className="primary" onClick={() => create()} disabled={busy}>Create your first script</button><div className="example-grid">{EXAMPLES.map(example => <button key={example.name} className="example" onClick={() => create(example)}><span className="eyebrow">START FROM AN EXAMPLE</span><strong>{example.name}</strong><span>Review, edit, then enable →</span></button>)}</div></section> : <>
          <div className="editor-heading"><div><div className="eyebrow">PERSONAL SCRIPT</div><h1>{draft.name || 'Untitled script'}</h1></div><label className="enable-switch"><input type="checkbox" checked={draft.enabled} onChange={event => edit({enabled: event.target.checked})}/><span>{draft.enabled ? 'Enabled' : 'Disabled'}</span></label></div>
          <section className="card"><label htmlFor="script-name">Name</label><input id="script-name" maxLength={120} value={draft.name} onChange={event => edit({name: event.target.value})}/>
            <div className="field-heading"><label htmlFor="script-regex">URL regex</label><button className="text-button" onClick={() => supportedUrl(testUrl) && edit({pattern: exactRegex(testUrl)})}>Use exact test URL</button></div>
            <input id="script-regex" className="mono" spellCheck={false} value={draft.pattern} onChange={event => edit({pattern: event.target.value})}/>
            <p className="hint">A JavaScript regular expression, without surrounding slashes. Use ^ and $ to match the whole URL.</p>
            <label htmlFor="test-url">Test a URL</label><div className="test-row"><input id="test-url" type="url" list="open-tabs" value={testUrl} onChange={event => setTestUrl(event.target.value)}/><span role="status" className={'match-badge ' + (match?.matches ? 'yes' : '')}>{match?.error ? 'Invalid regex' : match?.protected ? 'Protected / unsupported' : match?.matches ? 'Matches' : 'No match'}</span></div>
            <datalist id="open-tabs">{tabs.map(tab => <option key={tab.id} value={tab.url}>{tab.title}</option>)}</datalist>
            {!!tabs.length && <details className="open-tabs"><summary>Matching open tabs · {tabs.filter(tab => matchUrl(draft.pattern, tab.url).matches).length}</summary>{tabs.filter(tab => matchUrl(draft.pattern, tab.url).matches).map(tab => <button key={tab.id} onClick={() => setTestUrl(tab.url)}>{tab.title}<small>{tab.url}</small></button>)}</details>}
          </section>
          <section className="card"><label htmlFor="script-timing">When to run</label><div className="timing-options" id="script-timing">{[{id: 'start', title: 'Document start', detail: 'The earliest Chromium injection point for a new document.'}, {id: 'load', title: 'After page load', detail: 'Wait until the page and its resources have finished loading.'}].map(option => <label key={option.id} className={'timing-option ' + (draft.timing === option.id ? 'selected' : '')}><input type="radio" name="timing" value={option.id} checked={draft.timing === option.id} onChange={() => edit({timing: option.id as Script['timing']})}/><span><strong>{option.title}</strong><small>{option.detail}</small></span></label>)}</div><p className="hint">On single-page apps, enabled scripts run again after the URL changes. Disabling a script stops future runs; reload to undo changes it already made.</p></section>
          <section className="card code-card"><div className="field-heading"><label htmlFor="script-code">JavaScript</label><span className="eyebrow">PAGE MAIN WORLD</span></div><textarea id="script-code" className="code-editor" spellCheck={false} autoCapitalize="off" autoCorrect="off" value={draft.code} onChange={event => edit({code: event.target.value})} onKeyDown={event => {if (event.key === 'Tab') {event.preventDefault(); const field = event.currentTarget; const a=field.selectionStart,b=field.selectionEnd; edit({code: draft.code.slice(0,a)+'  '+draft.code.slice(b)}); requestAnimationFrame(() => {field.selectionStart=field.selectionEnd=a+2;});}}}/>
            <div className={'code-status ' + (validation ? 'invalid' : '')} role="status">{validation || 'Syntax valid'}</div><p className="hint">Use window to share values with the page. console.log and runtime errors appear in that page’s DevTools console. The page’s security policy still applies to operations such as eval and external script loading.</p></section>
          <p className="boundary-note">Scripts run in the top-level HTTP or HTTPS page. Browser settings, extension pages, the Chrome Web Store and incognito tabs and windows are excluded. Already open documents need a reload for document-start changes.</p>
        </>}
      </div>
      {deleteOpen && <dialog ref={deleteDialog} className="delete-dialog" role="alertdialog" aria-labelledby="delete-title" onCancel={() => setDeleteOpen(false)}><h2 id="delete-title">Delete this script?</h2><p>"{draft?.name}" will be removed from this profile.</p><div><button autoFocus onClick={() => setDeleteOpen(false)}>Cancel</button><button className="danger" onClick={remove}>Delete script</button></div></dialog>}
    </SidebarLayout>
  </Theme>;
}

createRoot(document.getElementById('root')!).render(<App/>);
