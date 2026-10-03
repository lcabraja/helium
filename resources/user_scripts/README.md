# Helium user scripts

The built-in User Scripts toolbar button opens a per-profile manager. Create a
script, enter a JavaScript URL regular expression, choose its timing, and save.
New scripts are disabled until explicitly enabled. Reload an existing page after
changing document-start code. The toolbar button is pinned on the first launch
that includes this component and remembers later pin/unpin choices.

The manager uses `@da-facility/ui` SidebarLayout and Meta Astryx. Its dependency is
pinned to UI commit `27b61261db77096d1c2611cbd0bfab0286528494`. JavaScript source is
stored in `chrome.storage.local` in the browser profile. No server, account,
remote script source, or telemetry is required.

## URL matching

Use a JavaScript regular expression without surrounding `/` delimiters. This is
not a Chrome match-pattern or a shell glob. The regex is tested against the full
URL, including query string and fragment. `^` and `$` anchor the whole URL. The
editor validates the regex and previews matching open tabs and a test URL.
The open-tab list refreshes when you return to the manager without replacing
unsaved script edits.

A specific YouTube watch page:

```text
^https://www\.youtube\.com/watch\?v=VIDEO_ID(?:&.*)?$
```

YouTube Studio livestream pages:

```text
^https://studio\.youtube\.com/video/[^/?#]+/livestreaming(?:[?#].*)?$
```

Only top-level HTTP and HTTPS documents are supported. Browser/internal pages,
extension pages, file/data URLs, the Chrome Web Store, incognito windows, and independent ephemeral container
tabs are excluded. Regular persistent container tabs use the same per-profile scripts.

## Timing and page access

Document start uses Chromium's native `chrome.userScripts` document-start hook.
It runs at the earliest supported injection point on a new document. After page
load registers at the same early point and waits for the window `load` event,
or runs immediately when the document is already complete.

Both modes use the page's MAIN world. `window`, DOM objects, and page globals are
shared with page code. `console.log` and runtime errors appear in that page's
DevTools console. Each script body has its own function scope, so use `window`
for values the page or another script should read. Return a Promise to attribute
asynchronous errors to the script, or use an async IIFE for `await`.

Browser `webNavigation` events handle `pushState`, `replaceState`, history and
fragment changes. Scripts rerun on a different matching URL. Repeated events for
the same URL are deduplicated; leaving a matching URL and returning runs again.
SPA execution happens after the URL change, not before the site's router, and
cannot promise the site's later asynchronous DOM work has finished. A script
can use `MutationObserver` when it needs to follow that work.

Disabling or deleting stops future runs and cancels pending load callbacks. It
cannot reverse DOM changes, requests or timers that code already started. Reload
the page to clear those effects. Native injection works on a strict-CSP fixture;
the page's security policy still applies to code operations such as `eval` and
loading external scripts. Tampermonkey `GM_*` APIs and metadata headers are not
implemented in this first version.

## Build

Bun is required in the build environment. The builder needs read access to the
pinned `da-facility/ui` repository through its normal Git credentials. Neither
credentials nor vendored dependencies enter the browser's resources or Git.

From this directory:

```sh
python3 setup_ui.py
bun run typecheck
bun run test
bun run build
```

`setup_ui.py` checks out the pinned UI revision, builds it, then installs this
package's frozen lockfile. GN packages the manager, worker, manifest and icon
into Chromium's resource bundle. `packaging/macos/release.py` runs setup after
replaying patches, so the existing manual release script includes this feature.
For a manual native build, run setup in the prepared source's
`components/helium_user_scripts` directory before invoking Ninja/Siso.

`patches/helium/core/user-scripts.patch` registers the component, packages its
resources, grants the userScripts API only to its fixed ID at a component
location, and seeds the toolbar pin once. It does not relax permission checks
for other extensions. The manifest public key fixes the component ID; it is not
a release-signing private key.

## Tests and private preview

`bun run test` covers regex/syntax validation, MAIN-world global access and logs,
start/load timing, SPA matching/nonmatching/deduplication, stale callbacks,
disabling, persistence rehydration, conflicting edits, registration failures,
and unauthorized message senders. The background service serializes mutations,
preserves source before applying registrations, and removes stale active
registrations if applying a saved version fails.

`bun run build:demo` builds an interactive editor preview. Copy `manager.html`
into `demo-dist`, then serve it with `preview/server.py` under a `demo` directory.
The demo stores edits in its own browser localStorage and never injects scripts
into websites. `preview/server.py` also provides `/fixtures/watch`,
`/fixtures/other`, `/fixtures/strict`, and `/fixtures/slow` for native QA. Bind the
server privately and use Tailscale Serve when sharing it.

Native QA must use a disposable profile and the fixture pages, not logged-in
sites. Verify the automatic toolbar pin/API grant in the compiled browser in
addition to testing the extension worker. Detailed results for this experiment
are in `docs/user-scripts-validation.md`.
