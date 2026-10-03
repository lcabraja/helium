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

## Still to verify

The full isolated native build is in progress. The compiled component's default
API permission and first-launch toolbar pin, native app packaging/signing,
restart persistence in the compiled app, and the final download are pending.
Further browser checks for slow-load cancellation and incognito behavior are
pending. Unit tests cover cancellation. Native guards exclude in-memory
partitions, including independent incognito tabs inside a regular profile.

No production profile or update feed is used for these tests. The experimental
build disables Sparkle and will use a separate app/profile identity.
