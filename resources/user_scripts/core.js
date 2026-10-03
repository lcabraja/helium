// Copyright 2026 The Helium Authors. GPL-3.0.
export const RUNTIME_KEY = 'helium.user-scripts.runtime.v1';
export const REGISTRATION_IDS = ['helium-document-start', 'helium-after-load'];
export const MAX_SCRIPTS = 500;

export function supportedUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) &&
      url.hostname !== 'chromewebstore.google.com' &&
      !(url.hostname === 'chrome.google.com' && url.pathname.startsWith('/webstore'));
  } catch { return false; }
}

export function matchUrl(pattern, value) {
  if (!supportedUrl(value)) return {matches: false, protected: true};
  try { return {matches: new RegExp(pattern).test(new URL(value).href), protected: false}; }
  catch (error) { return {matches: false, error: error.message, protected: false}; }
}

// Code is compiled by Chromium's userScripts API, never by eval or a DOM script
// element. An ordinary function gives scripts their own local declarations;
// window and the DOM are the page's actual main-world objects.
export function runnerSource(scripts, revision, reason, routeUrl) {
  const enabled = scripts.filter(script => script.enabled === true);
  const definitions = enabled.map(script => `{
    id: ${JSON.stringify(script.id)}, name: ${JSON.stringify(script.name)},
    pattern: ${JSON.stringify(script.pattern)}, timing: ${JSON.stringify(script.timing)},
    run: function heliumUserScript() {\n${script.code}\n}
  }`).join(',\n');
  return `(() => {
    const supportedUrl = ${supportedUrl.toString()};
    if (window.top !== window || !supportedUrl(location.href)) return;
    const key = Symbol.for(${JSON.stringify(RUNTIME_KEY)});
    const revision = ${JSON.stringify(revision)};
    const previous = globalThis[key];
    if (previous && previous.revision !== revision) previous.cancelled = true;
    const state = previous && previous.revision === revision && !previous.cancelled
      ? previous : {revision, cancelled: false, visits: new Map()};
    globalThis[key] = state;
    const url = ${JSON.stringify(routeUrl)} || location.href;
    const results = [];
    for (const script of [${definitions}]) {
      // Record nonmatches too, so matching A -> nonmatching B -> A runs again.
      const visitKey = script.id;
      if (state.visits.get(visitKey)?.url === url) continue;
      const visit = {url};
      state.visits.set(visitKey, visit);
      if (!new RegExp(script.pattern).test(url)) continue;
      const execute = () => {
        if (state.cancelled || location.href !== url ||
            state.visits.get(visitKey) !== visit) return;
        const label = '[Helium User Scripts: ' + script.name + ']';
        try {
          const result = script.run.call(globalThis);
          if (result && typeof result.then === 'function') {
            Promise.resolve(result).catch(error => console.error(label, error));
          }
          results.push({id: script.id, status: 'executed', reason: ${JSON.stringify(reason)}});
        } catch (error) {
          console.error(label, error);
          results.push({id: script.id, status: 'error', message: String(error)});
        }
      };
      if (script.timing === 'load' && document.readyState !== 'complete') {
        window.addEventListener('load', execute, {once: true});
      } else execute();
    }
    return results;
  })();\n//# sourceURL=helium-user-scripts/${revision}/${reason}.js`;
}

export function registrations(scripts, revision) {
  return ['start', 'load'].flatMap((timing, index) => {
    const selected = scripts.filter(script => script.enabled === true && script.timing === timing);
    if (!selected.length) return [];
    return [{id: REGISTRATION_IDS[index], matches: ['http://*/*', 'https://*/*'],
      excludeMatches: ['*://chromewebstore.google.com/*', '*://chrome.google.com/webstore*'],
      allFrames: false, world: 'MAIN', runAt: 'document_start',
      js: [{code: runnerSource(selected, revision, timing)}]}];
  });
}

export function cancellationSource(currentRevision) {
  return `(() => { const state = globalThis[Symbol.for(${JSON.stringify(RUNTIME_KEY)})];
    if (state && state.revision !== ${JSON.stringify(currentRevision)}) state.cancelled = true; })();`;
}
