# User scripts validation

Experiment branch: `feat/user-scripts` from fork main `286cef19819c27685b1a2b64b84e7a5fbc5cac1a`.
Platform baseline: `24af304308bd2f1e0cd0c0557c77a4562c818f73`.
Prepared Chromium baseline: `73c14f6228d7cd537c855007e8f88678969cc0eb`.

## Passed

- TypeScript checking and production/demo bundles.
- 23 Bun tests for the execution service, validation and persistence.
- The fork's patch-series lint.
- 12 existing macOS release-script tests.
- GN resource-only build, including GRIT resource headers/map and compiled map.
- Computer-use checks in a disposable browser profile for create, edit, disable,
  delete, invalid regex feedback, match/nonmatch feedback, and reload persistence.
- Real native `chrome.userScripts` registration/execution using the same packaged
  worker as an unpacked test extension in the existing Chromium 154 Helium build.
  The disposable profile explicitly enabled user scripts for that test extension.
- Document start set a marker while `document.readyState` was `loading`; the
  fixture's first page script observed that marker.
- After-load code observed `complete`, read the page's `window.fixture.pageValue`
  of 41, and wrote 42 to both `window` and the visible DOM.
- SPA routes AAA to BBB incremented both counters; a nonmatching route kept them
  unchanged; returning to AAA incremented both again.
- A strict-CSP fixture allowed native MAIN-world injection for both timings.
- The page DevTools console visibly showed script logs and the expected order:
  user document-start log, first page-script log, user after-load log, page load.

- Synchronous exceptions and rejected Promises appeared in the page console with
  the script name; later scripts and the fixture continued running.
- Disabling the after-load script prevented execution after both reload and SPA
  navigation, including a fragment route.

- On a fixture whose image delays window load by 15 seconds, document-start code
  ran while the page was interactive and after-load remained at zero. Leaving
  the matching route before load completed cancelled the old callback.
- Disabling the after-load script in the manager while the fixture was loading
  also kept its count at zero after window load completed.

- All eight changed C++ translation units passed a direct Clang syntax check
  with their generated build flags and resource headers.
- The refreshed editor preview retained the saved example when Escape dismissed
  its focused delete dialog.
- The manager refreshed its matching-tab count from one to two and back to one
  after opening and closing a fixture tab. An unsaved name edit survived both
  refreshes. Saved document-start code still ran on the next fixture navigation.

- Replaying all 383 maintained patches and resources reproduced the prepared
  source exactly, with zero source-file changes.
- Isolated packaging configuration preserves the separate app name, profile
  directory and helper bundle identifiers.

## Native app verification

The native app was built from `9cd4569aad4a716639320f22a65f4edc7ef8ba9d`
and tested on 2026-10-03. The full build completed 34,779 steps in 3h38m53s.
A final incremental build incorporated the manager refresh change in 17 seconds.

Computer-use checks in a fresh disposable profile passed:

- The User Scripts button appeared automatically on first launch. Creating,
  saving and enabling scripts required no manual extension permission setting.
- Both saved scripts ran in ordinary tabs and a Personal container tab.
  The first page script observed the document-start marker while loading.
  After-load code read page state and displayed `42 / complete` in the DOM.
- The page console visibly showed the user document-start log, the first page
  script, the user after-load log, and the page load log in that order.
- SPA changes ran each matching script once more in an ordinary tab.
- Neither script ran in an independent incognito tab, on initial navigation,
  an SPA route change, or after hibernating and reopening that tab.
- The manager excluded the private tab from its matching-tab suggestions,
  including while the private tab was hibernated. Opening the manager from
  the private tab did not copy its URL into the manager URL or test field.
- A separate incognito window had no User Scripts toolbar component, and
  neither script ran on navigation or an SPA route change.
- After quitting and restarting the app, both saved scripts ran on the first
  fixture navigation. Both remained enabled in the manager.
- Unpinning the toolbar button survived the restart. The manager remained
  accessible through the Extensions menu.

The test app is `Helium User Scripts`, with bundle identifier and profile
directory `eu.cabraja.helium.userscripts`. It targets Apple Silicon and macOS 15
or later. The disposable test profile used `--use-mock-keychain` and contained
no real credentials. No production app, profile or update feed was modified.

## Signing and artifact

Developer ID signing used the existing Keychain identity for team `GJP8JC4Y23`.
No new Keychain approval prompt appeared, and no exported private key was used.
Apple accepted notarization; stapling, ticket validation, strict deep code
signature verification and Gatekeeper assessment passed.

The application contains no Sparkle framework, linked Sparkle dependency or
Sparkle Info.plist keys. Automatic updates are disabled for this experiment.

Archive: `Helium-User-Scripts-9cd4569-arm64.zip`.

SHA-256:
`e4587bbc39bbcb2c7235045db8bd528b874ad7433d436339bf5f8d4563e9d95e`.

## Scope limits

Scripts run only in top-level matching HTTP and HTTPS pages. GM APIs are not
implemented; asynchronous code can use an async IIFE. The editor-only web
preview saves examples locally but cannot inject into other websites.
Intel macOS builds and other operating systems were not built in this run.
