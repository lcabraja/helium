# Container tabs

Containers keep separate site sessions inside one Helium profile. Each container
has its own cookies, local storage, IndexedDB, service workers, Cache Storage,
HTTP cache and HTTP authentication cache. Bookmarks, history and saved passwords
remain part of the browser profile.

The starting containers are Personal, Work, Banking and Shopping. Names, colors
and icons can be edited. New containers receive permanent random identifiers;
renaming a container keeps its sessions, and deleting one never recycles its
identifier.

## Opening tabs

- Use **New container tab** from the application menu or tab context menu.
- Right-click or hold the new-tab button to choose a container. Both tab-strip
  implementations support this.
- Press **Ctrl+Alt+T**, or **Command+Option+T** on macOS, for the container picker.
- Link, image, audio and video context menus can open their target in a chosen container.
- Bookmark menus, the bookmark manager, bookmark side panel, history menu and
  Reading List offer container actions.
- Select one or more tabs and use **Reopen in container** to change their
  container. This reloads the page in a separate browsing context. It does not
  transfer the original page's credentials, opener or referrer.

Links opened from a container inherit it. A regular new-tab command opens outside
containers unless **Select a container for each new tab** is enabled. A tab keeps
its container across navigation, duplication, movement between windows,
hibernation and session restoration. Container names appear in the tab label and
a thin, rounded line at the top identifies the container even when a tab is
pinned. It uses the same thickness as the tab-group underline.

Origin-bound `blob:` and `filesystem:` URLs and JavaScript bookmarklets cannot be
moved to another container. Reopening an unsupported target leaves the original
tab open.

## Incognito tabs

Choose **New incognito tab** from the new-tab button's context menu, or
**Incognito tab** in any container picker. Every new incognito tab gets its own
in-memory cookies, local storage, IndexedDB, service workers and caches. Links
opened in another tab and popups get fresh identities. **Duplicate** shares the
original tab's identity. Navigating, moving or hibernating an existing tab keeps
its identity.

Closing the last related tab starts a five-minute grace period. Reopening it
with Command+Shift+T during that period recovers its sessions. Reopening after
expiry loads the URL with a fresh, empty identity. The browser keeps at most 25
closed identities eligible for recovery, evicting the oldest first. Closing
Helium ends all temporary identities immediately. They are never added to the
saved container list.

These tabs do not add page visits to normal history or persist their open and
recently closed session entries. Saved tab groups retain blank placeholders
instead of their private URLs. Bookmarks and downloaded files explicitly saved
by the user remain. Profile settings and extensions are shared with ordinary
tabs. This provides temporary, isolated site storage inside the same profile;
it does not create a separate off-the-record profile for each tab.

Expiry clears partition data and caches. Chromium retains the empty partition
objects until the profile shuts down, so this does not promise that every byte
of partition bookkeeping is freed exactly at five minutes.

## Management

Open **Manage containers** from a container menu or Settings → Appearance. The
manager provides names, colors, seven monochrome icons, creation, deletion, the
enable switch and the new-tab picker preference. It fits small lists and scrolls
for larger lists, with a limit of 500 containers. Existing umbrella selections
become dots without changing the container identity or its stored sessions. Container creation is unavailable in private or
guest windows.

Deleting a container asks to close its tabs and delete its site data. Pages with
unsaved changes can block closure; their data is retained until the tabs close.
Disabling container creation preserves existing tabs and data. Clearing browsing
data includes saved containers and respects the selected sites and time range.

Restoring a deleted or malformed container identity uses an empty memory-only
partition. It never falls back to the normal profile's authenticated partition.

## Implementation and validation

The implementation is maintained in
`patches/helium/core/container-tabs.patch`, after the existing common patch series.
It uses Chromium's `SiteInstance::CreateForFixedStoragePartition` with the storage
domain `helium-containers`. Session records store the identifier under
`helium.container_id`. Session-storage namespaces use the same partition as the
restored page. Chromium's storage garbage collector preserves registered
container partitions.

This implements native Firefox-style containers. Mozilla's Multi-Account
Containers extension adds separate features such as site assignments, account
sync, proxy configuration and VPN integration; those services are outside this
patch.

The release source archive excludes `chrome/test/data`. For a full Chromium
checkout that includes WebUI tests, also apply
`docs/container-tabs-webui-tests.patch` to update the bookmark side-panel test
proxy. Keep that test-only patch out of the release patch series.

The patch adds `ContainerBrowserTest` to Chromium's `browser_tests` target. After
preparing a matching Chromium source tree and applying the common and platform
patches, build and run:

```sh
autoninja -C out/Default browser_tests
out/Default/browser_tests --gtest_filter='ContainerBrowserTest.*'
```

For the macOS development build, apply the supplemental patches and use
`helium_development_tests` as described in `docs/macos-development-build.md`.
The full upstream `browser_tests` executable does not currently link against
Helium's removed Google services.
The tests cover storage
separation, same-container sharing, BroadcastChannel separation, cross-site
navigation, link and popup inheritance, duplicate and closed-tab restore,
hibernation, profile restart, editing validation and deleted-identity handling.
The suite also checks site- and time-filtered cookie removal for containers
without open tabs, plus partition-specific removal that must preserve the other
containers and the ordinary profile partition.

Before release, also check the native UI in both horizontal and vertical layouts:

1. Open each menu and verify keyboard navigation, long-click and cancellation.
2. Create, rename and recolor a container with tabs in two windows.
3. Reopen pinned, grouped and selected tabs, checking order and container labels.
4. Cancel a page's before-unload prompt during container deletion; verify its
   cookies remain until closure succeeds.
5. Clear one site's data and a limited time range; verify other sites and
   containers retain data outside the requested range.
6. Restart with container tabs open and restore a closed container tab.

Patch application and build checks alone do not establish storage isolation.
The browser tests and UI checks must pass before treating the feature as ready
for use with separate signed-in accounts.

## Validation on 14 September 2026

- Rebased onto Helium upstream `fbd20c49`, Chromium `153.0.8010.36`.
- The complete common patch series and current macOS patch series apply cleanly.
- The repository's patch parser, series membership and whitespace checks pass.
- All 36 changed C++ translation units with macOS targets pass Clang type checking,
  including the browser-test source. The Linux D-Bus menu was inspected separately.
- `container_service.o` and `container_ui.o` compile successfully.
- Bookmarks, history, settings and bookmark-side-panel TypeScript builds and lint
  checks pass.
- Header dependency checks for the new container targets, bookmark targets and
  bookmark side panel pass. The wider browser check still reports existing
  dependency errors in upstream files unrelated to containers.

This Mac has Xcode 16.1 and the macOS 15.1 SDK. Local compilation used Clang modules
and precompiled headers disabled, plus two generated-build-only compatibility
aliases for newer SDK names in Chromium's existing Base and Skia code. None of
those SDK workarounds is included in the feature patch.

A complete Helium binary has **not** been built, and the 13 browser tests and
interactive UI checks have **not** been run. Finish those checks with the required
Xcode 26 toolchain before release. No functional isolation guarantee is inferred
from successful compilation.

## Chromium 154 rebase on 27 September 2026

Rebased onto upstream `03c44a6a`, Chromium `154.0.8037.57`. The container submenu
now lives in Chromium's extracted `NewTabButtonMenuModel`, which both new-tab
buttons share. The shared button retains Chromium's menu lifecycle callbacks and
Linux middle-click behavior. Bookmark commands use new enum values after the
upstream isolated-window commands. Restoring a container still selects its
storage partition before creating the tab, alongside upstream's lazy restoration.

All 77 files touched by the patch were checked against the matching Chromium
tag and the preceding common patches affecting those files. The refreshed patch
applies without rejects or fuzz. The overlapping patches from macOS platform
revision `c464a10` also apply. The WebUI test-proxy patch applies to the matching
Chromium 154 test source.

These patch checks do not validate the full Chromium 154 dependency tree. The
earlier Chromium 153 compilation results above are historical. Mitsuha still
has Xcode 16.1, so a complete Chromium 154 build and runtime tests remain required
on a Mac with the supported Xcode toolchain. See `docs/macos-development-build.md`
for the build and delivery requirements.

## Runtime validation on 29 September 2026

Rebased onto upstream `0dbe337` with macOS platform `24af304`, Chromium
`154.0.8037.57`, Xcode 27.0 and the macOS 27.0 SDK on Katal. The development
app, chromedriver and focused regression executable build successfully.

All 15 container cases and the PRE restart setup pass, for 16 executions. The
26 selected bookmark, history-list and appearance runners pass, as do the seven
new-tab, wallpaper, extension-sidebar, history-routing and personalization
runners. One upstream history test remains disabled and is not counted as a pass.
The 376 common, platform and supplemental patches replay with no fuzz. Exact
repository lint and the focused target's header dependency check pass.

Runtime testing found and fixed initial blank pages losing their container's
storage partition. Tests now check valid and invalid identities both before and
after the first navigation. The hibernation fixture controls browser focus and
waits for the resume navigation before checking storage.

Native checks verified container creation and editing, separate cookies/local
storage/IndexedDB/Cache Storage/service workers, rename and restart persistence,
target-blank inheritance, the macOS shortcut, nested management sheets, pinned
and grouped reopening, and cancellation of deletion when a page has unsaved
changes. Horizontal and vertical tab layouts were exercised. Multi-selection
reopening and edits across two windows were not checked in this run.

This is a development build. The full upstream `browser_tests` target still
fails to link fixtures for services removed by Helium, so the result is not full
Chromium test coverage. Runtime checks used macOS 27.0; macOS 15.5 remains
untested despite the audited deployment targets and bundle library paths.

## Incognito tabs and UI validation on 30 September 2026

The incognito lifecycle and UI updates are in
`patches/helium/core/container-tabs-incognito.patch`. The app, chromedriver and
focused test executable build with Xcode 27.0 on Katal. All 27 selected test
executions pass, including 23 container executions, the two native new-tab menu
regressions and the two appearance runners. The complete 379-patch common,
platform and supplemental series applies without fuzz. Repository lint and the
focused target's header dependency check pass.

New regression cases cover independent cookies and site storage, duplicate
sharing, the last-tab grace period, expiry cleanup and fresh restoration, links
and popups, the closed-identity limit, hibernation, history exclusion, saved-group
placeholders, legacy icons and the 500-container limit. The popup fixture watches
inserted tabs instead of all internal WebContents, so speculative contents do
not trigger a test-helper assertion.

Native computer-use checks confirmed duplicate sharing, independent child tabs,
restoration within the grace period, and empty cookies, local storage, IndexedDB,
Cache Storage and service workers after a real five-minute expiry. The test URL
was absent from the profile's history database after a clean exit. The app also
handled 22 open tabs and eight repeated new-tab menu openings without crashing.

The small manager fits its contents. A separate profile containing 500 containers
scrolls to the final row and allows editing that row. The final icon picker has
seven options, and a container's top line matches the tab-group underline's
thickness and rounded ends. Native visual checks used the horizontal layout;
the shared tab-view implementation receives the same drawing change.
