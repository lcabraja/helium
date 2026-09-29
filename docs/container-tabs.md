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
an accent identifies the container even when a tab is pinned.

Origin-bound `blob:` and `filesystem:` URLs and JavaScript bookmarklets cannot be
moved to another container. Reopening an unsupported target leaves the original
tab open.

## Management

Open **Manage containers** from a container menu or Settings → Appearance. The
manager provides names, colors, icons, creation, deletion, the enable switch and
the new-tab picker preference. Container creation is unavailable in private or
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
