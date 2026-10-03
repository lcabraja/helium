import {cancellationSource, registrations, runnerSource, supportedUrl, REGISTRATION_IDS} from './core.js';
import {validateScripts} from './validation.js';

let operations = Promise.resolve();
function serialized(task) {
  const operation = operations.then(task);
  operations = operation.catch(() => {});
  return operation;
}

async function snapshot() {
  const saved = await chrome.storage.local.get(['scripts', 'revision', 'registrationError']);
  return {scripts: saved.scripts || [], revision: saved.revision || 'initial',
    registrationError: saved.registrationError || ''};
}

async function registerScripts(scripts, revision) {
  const desired = registrations(scripts, revision);
  const current = await chrome.userScripts.getScripts();
  const removed = current.filter(script => REGISTRATION_IDS.includes(script.id) &&
    !desired.some(next => next.id === script.id)).map(script => script.id);
  if (removed.length) await chrome.userScripts.unregister({ids: removed});
  const updates = desired.filter(next => current.some(script => script.id === next.id &&
    JSON.stringify(script.js) !== JSON.stringify(next.js)));
  if (updates.length) await chrome.userScripts.update(updates);
  const additions = desired.filter(next => !current.some(script => script.id === next.id));
  if (additions.length) await chrome.userScripts.register(additions);
}

async function cancelPending(currentRevision) {
  const tabs = await chrome.tabs.query({});
  await Promise.all(tabs.filter(tab => !tab.incognito && supportedUrl(tab.url)).map(async tab => {
    try {
      await chrome.userScripts.execute({target: {tabId: tab.id}, world: 'MAIN',
        injectImmediately: true, js: [{code: cancellationSource(currentRevision)}]});
    } catch { /* A closed, navigating, or restricted tab has nothing to cancel. */ }
  }));
}

async function reconcile() {
  const saved = await snapshot();
  try {
    await registerScripts(validateScripts(saved.scripts), saved.revision);
    await chrome.storage.local.remove('registrationError');
  } catch (error) {
    // A broken configuration must not keep older enabled registrations alive.
    try { await chrome.userScripts.unregister({ids: REGISTRATION_IDS}); } catch {}
    await chrome.storage.local.set({registrationError: String(error.message || error)});
    console.error('[Helium User Scripts] Could not register scripts', error);
  }
}

async function save(message) {
  const before = await snapshot();
  if (message.revision !== before.revision) throw new Error('Scripts changed in another window. Reload the manager before saving.');
  const scripts = validateScripts(message.scripts);
  const revision = crypto.randomUUID();
  // Persist the user's source before changing registrations. Startup repairs
  // an interrupted operation from this same source, including disabled scripts.
  await chrome.storage.local.set({scripts, revision, registrationError: ''});
  try {
    await registerScripts(scripts, revision);
    await cancelPending(revision);
  } catch (error) {
    await chrome.storage.local.set({registrationError: String(error.message || error)});
    try { await chrome.userScripts.unregister({ids: REGISTRATION_IDS}); } catch {}
    await cancelPending();
    throw new Error('Saved, but could not apply scripts: ' + error.message);
  }
  return snapshot();
}

// Only our packaged manager can mutate source or request tab information.
// There is no content-script bridge or externally_connectable entry point.
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id ||
      !sender.url?.startsWith(chrome.runtime.getURL('manager.html'))) return;
  serialized(async () => {
    if (message.type === 'list') return snapshot();
    if (message.type === 'save') return save(message);
    if (message.type === 'tabs') return (await chrome.tabs.query({})).filter(tab =>
      !tab.incognito && supportedUrl(tab.url)).map(tab => ({id: tab.id, title: tab.title, url: tab.url}));
    throw new Error('Unknown request.');
  }).then(value => respond({ok: true, value}), error => respond({ok: false, error: error.message}));
  return true;
});

async function routeChanged(details) {
  if (details.frameId !== 0 || !supportedUrl(details.url)) return;
  const tab = await chrome.tabs.get(details.tabId).catch(() => null);
  if (!tab || tab.incognito) return;
  const saved = await snapshot();
  if (saved.registrationError || !saved.scripts.some(script => script.enabled)) return;
  try {
    await chrome.userScripts.execute({
      // Bind to the document that generated the event, never its replacement.
      target: {tabId: details.tabId, documentIds: [details.documentId]}, world: 'MAIN',
      injectImmediately: true, js: [{code: runnerSource(validateScripts(saved.scripts), saved.revision, 'route', details.url)}],
    });
  } catch (error) {
    console.debug('[Helium User Scripts] Route no longer available', error.message);
  }
}

chrome.webNavigation.onHistoryStateUpdated.addListener(details => {
  serialized(() => routeChanged(details)).catch(console.error);
});
chrome.webNavigation.onReferenceFragmentUpdated.addListener(details => {
  serialized(() => routeChanged(details)).catch(console.error);
});
chrome.runtime.onInstalled.addListener(() => serialized(reconcile));
chrome.runtime.onStartup.addListener(() => serialized(reconcile));
chrome.action.onClicked.addListener(async tab => {
  const manager = chrome.runtime.getURL('manager.html');
  const existing = (await chrome.tabs.query({url: manager + '*'}))[0];
  const url = manager + (!tab.incognito && supportedUrl(tab.url) ? '?url=' + encodeURIComponent(tab.url) : '');
  if (existing) {
    await chrome.tabs.update(existing.id, {active: true});
    await chrome.windows.update(existing.windowId, {focused: true});
  } else await chrome.tabs.create({url});
});
serialized(reconcile);
