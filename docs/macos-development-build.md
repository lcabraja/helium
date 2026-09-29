# Building the container-tab development app

Use the current fork's `main` together with the matching
[`imputnet/helium-macos`](https://github.com/imputnet/helium-macos) platform tools.
The September 2026 rebase uses Chromium `154.0.8037.57` and was checked against
platform commit `24af304`. Follow that repository's build instructions, including
Xcode 26 or newer, its Metal toolchain, and pinned compiler/dependency downloads.
Record both Git revisions in the build report.

The platform repository's `helium-chromium` submodule must point to the commit
from `lcabraja/helium` being built. A default recursive clone points to upstream
and does not contain this feature. Keep `AGENTS.md` and `CLAUDE.md` deleted in the
fork.

If Google's matching source archive is unavailable, use a source checkout at the
exact Chromium tag with its pinned DEPS. A GitHub Chromium source archive alone
does not include those dependencies. Do not substitute another Chromium release
or mix dependency versions to make configuration pass.

## Build and verify

1. Build for Apple Silicon with a deployment target compatible with macOS 15.5.
   Use a non-component build or package all required component libraries. The
   delivered app must work after removal from its original build directory.
   Append `docs/macos-development.gn` after the common and macOS platform GN
   flags. It records this development configuration and disables precompiled
   headers, whose Chromium 154 Apple build rules produce incorrect output
   paths. Run GN with `--fail-on-unused-args` before compiling.
   Keep Chromium's macOS 13.0 compile-time deployment target and use the
   separate `mac_min_system_version = "15.0"` launch requirement. Raising the
   compiler target to 15.0 makes CoreGraphics APIs used by WebRTC's compiled
   legacy capture backends unavailable. This is separate from the SDK version;
   the build still uses the current Xcode SDK and retains ScreenCaptureKit.
2. Resolve patch, GN, compiler and linker failures in the maintained patches.
   Reapply patches to confirm fixes survive a fresh build. Do not leave fixes
   only in the generated Chromium tree.
3. For a source checkout containing Chromium's test data, apply
   `docs/container-tabs-webui-tests.patch`, followed by
   `docs/macos-development-webui-tests.patch` and
   `docs/macos-development-cpp-tests.patch`. Build `browser_tests` and run
   `ContainerBrowserTest.*`, including the `PRE_` restart test. Run the modified
   bookmark, history and settings WebUI checks.
   The small checkout also omits the non-Git test-font archive. Fetch the
   `src/third_party/test_fonts/test_fonts` object specified in Chromium's
   `DEPS`, verify its declared SHA-256 and size, and extract it into that exact
   directory before building `browser_tests`. Do not substitute system fonts.
4. Launch the built app with a separate development profile. Follow the UI and
   storage-isolation checks in `docs/container-tabs.md`. Record any check that
   could not run, rather than reporting it as passed.
5. Use the platform's development/ad-hoc signing flow. Verify the app's signature
   and bundled library paths. Do not use production signing identities or
   notarization credentials unless separately authorized.
6. Commit and push any build fixes to the user's fork using a summary, detailed
   explanation and file-by-file commit body. Record the final commit in the app
   archive name and build report.

## Deliver with Taildrop

Package the app as a DMG or a ZIP that preserves macOS bundle metadata and
symlinks, for example with `ditto -c -k --sequesterRsrc --keepParent`. Include a
SHA-256 checksum and a short report listing architecture, macOS deployment
target, Xcode version, source revisions and test results.

Discover the requested recipient in `tailscale status` and use Taildrop to send
the archive, checksum and report. The current requested recipient is Nausicaa,
listed as `Nausicaä` / `nausica.tail7c7833.ts.net`. This build is for local
development. Keep its profile separate from the user's regular browser data.

## Notifications

Configure `pushover-cli` outside the repository. Credentials are provisioned
privately and must never appear in commits, build reports, logs or task prompts.
Use Keychain when available; protect any fallback credential file with mode
`0600`. Remove the credential-transfer archive after importing it.

Send a notification when a build needs user action and after successful Taildrop
delivery:

```sh
pushover-cli send --title Codex 'Helium development build sent to Nausicaa'
```

Only send that completion message after the build and transfer succeed.

## Katal preparation on 27 September 2026

The complete Chromium 154.0.8037.57 checkout and pinned DEPS were fetched on
Katal, using Chromium's GitHub mirror for the root repository. Both Google and
GitHub resolve that tag to `73c14f6228d7cd537c855007e8f88678969cc0eb`.
The common and macOS c464a10 patch series applied without fuzz, 365 patches
in total. The additional WebUI test patch required its context to use Chromium
154's `contextMenuOpenBookmarkInOffTheRecordWindow` name. After correction,
it applied without fuzz and its reverse round trip restored the original file.

Retain the full checkout for browser tests. The platform's normal
`prune_binaries.py` step removes `chrome/test/data` and other test fixtures;
it was intentionally skipped for this development checkout.

The pinned Clang, Rust, GN, Siso, TypeScript, Go and Node tools were downloaded,
along with Helium's verified platform resources. GN configuration stopped in
`build/config/apple/sdk_info.py` because only Command Line Tools were installed:
`xcodebuild -version` requires full Xcode. Xcode and its Metal component remain
required. No app compilation, browser tests, UI checks, signing or app delivery
has completed. The proposed non-component arm64 build targets macOS 15.0 so
that it can run on Mitsuha's macOS 15.5; that target still needs validation in
the built binaries.

## Katal rebase on 29 September 2026

The container-tab commits are rebased onto upstream `0dbe337`, retaining
Chromium `154.0.8037.57`. The macOS platform is updated to `24af304`, including
its window-resize fix. The common, macOS and additional WebUI test patches all
apply to pristine pinned source files without fuzz, 369 patches in total.
The fork's configuration validation and whitespace checks pass.

Xcode 27.0, build `27A266a`, and its Metal toolchain are installed on Katal.
The build uses the macOS 27.0 SDK with Chromium's macOS 13.0 compiler target,
a macOS 15.0 minimum launch version and a non-component arm64 configuration.
A complete build and runtime validation
are still required; successful patch application does not establish either.

## Chromium 154 test fixture compatibility

The full checkout's WebUI tests need a separate test-only compatibility patch,
`docs/macos-development-webui-tests.patch`. Release archives omit these test
sources, so this patch is deliberately outside `patches/series`.

The patch fills in Helium's avatar, import, search-engine and system-settings
interfaces in test doubles. Sync component tests import their types directly
because Helium no longer re-exports them from `lazy_load.ts`. History tests use
direct navigation for the synced-tabs route whose sidebar link was removed.
Assertions for removed extension-store, sign-in and color-scheme controls now
check their absence.

Appearance fixtures include Helium's layout and zen-mode preferences. Tests
exercise layout-dependent controls, independent zen-mode pin preferences and
the native container-management message. The removed Chromium tab-strip
settings are covered by Helium's layout suite instead. Type-only Sync imports
have explicit GN path mappings and do not introduce runtime imports of unbundled
modules.

The new-tab app and wallpaper-panel test registrations select Helium-specific
suites. Chromium's original suites remain in the source checkout for reference,
but their Google logo, search, AI, module and wallpaper-search controls are not
in Helium's templates. The replacement suites check the retained shortcuts,
customization preferences, background/attribution updates, local wallpaper
selection, reset, device theme, third-party themes and managed-theme guards.
Production and test TypeScript checking remain enabled.

Compilation exposed two production inconsistencies: restored About-page update
controls still had disabled type declarations, and the local wallpaper action
did not check the managed-theme guard. Both fixes are in the normal patch series.
The 37 modified container C++/Objective-C++ translation units and the WebUI test
resources compile with the current Xcode toolchain. Runtime validation remains
required.

The full test build also needs `docs/macos-development-cpp-tests.patch`.
It passes explicit empty noise-token maps when standalone Blink fixtures create
pages and web views, and adds the noise-token update method to page-broadcast
test doubles. These fixtures have no browser-provided noise tokens. Production
callers still supply their tokens through the required constructor arguments.

The same C++ test patch supplies disconnected URL-loader factories to search
engine fixtures and registers their Helium service preferences. Bang requests
cannot reach a live service from these fixtures. Production search-engine
services retain their profile-provided network factory.

The C++ compatibility patch also updates browser-process and omnibox test doubles,
DNS-SD and extension helpers, search-edit arguments, and the retained Google
engine symbol. Safe Browsing-specific assertions follow its disabled build flag,
and vertical-tab tests cover Helium's remaining bottom container. These changes
allow shared test support to compile without restoring removed product features.

Native UI checks found two container issues: macOS needs its shortcut in the
Cocoa accelerator table and a label in shortcut settings. Noopener windows must
preserve a fixed storage
partition when creating a new browsing instance. Both fixes are in the normal
patch series. The popup regression test now checks storage identity, cookie
sharing and a null opener for script-created windows and target-blank links.

The manager, editor and deletion dialogs now use the initiating dialog as their
parent. On macOS, attaching every dialog to the main window queued child sheets
behind the manager, making Edit and Add appear unresponsive. The picker's
Manage containers action also keeps the correct parent relationship.

The full-checkout fixtures use Helium's disabled-by-default preloading, error
pages and search suggestions, and verify changed values survive a restart.
Layout fixtures use Helium's layout preference and remaining separators. Hover
expansion is disabled in Helium, so its upstream scenarios are replaced by a
check that the setting cannot enable it. The four renderer reading-mode suites
are omitted because the upstream disable-AI patch removes their implementation
files from the renderer target. Other renderer suites remain in the test build.
