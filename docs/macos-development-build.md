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
   `docs/macos-development-cpp-tests.patch`. Build `helium_development_tests` and run
   `ContainerBrowserTest.*`, including the `PRE_` restart test, and
   `HeliumNewTabMenuBrowserTest.*`. Run the modified
   bookmark, history and settings WebUI checks.
   The small checkout also omits the non-Git test-font archive. Fetch the
   `src/third_party/test_fonts/test_fonts` object specified in Chromium's
   `DEPS`, verify its declared SHA-256 and size, and extract it into that exact
   directory before building the regression executable. Do not substitute system fonts.
4. Launch the built app with a separate development profile. Follow the UI and
   storage-isolation checks in `docs/container-tabs.md`. Record any check that
   could not run, rather than reporting it as passed.
5. Use the stable Developer ID packaging procedure below for this fork. Verify
   the app's signature and bundled library paths. Use ad-hoc signing only for
   disposable local tests, since it cannot preserve the installed app's identity.
6. Commit and push any build fixes to the user's fork using a summary, detailed
   explanation and file-by-file commit body. Record the final commit in the app
   archive name and build report.

## Deliver with Taildrop

Package the app as a DMG or a ZIP that preserves macOS bundle metadata and
symlinks, for example with `ditto -c -k --sequesterRsrc --keepParent`. Include a
SHA-256 checksum and a short report listing architecture, macOS deployment
target, Xcode version, source revisions and test results.

Discover the requested recipient in `tailscale status` and use Taildrop to send
the archive, checksum and report. The latest requested recipient is Mitsuha,
listed as `mitsuha` / `mitsuha.tail7c7833.ts.net`. This build is for local
development. Keep its profile separate from the user's regular browser data.

## Notifications

Configure `pushover-cli` outside the repository. Credentials are provisioned
privately and must never appear in commits, build reports, logs or task prompts.
Use Keychain when available; protect any fallback credential file with mode
`0600`. Remove the credential-transfer archive after importing it.

Send a notification when a build needs user action and after successful Taildrop
delivery:

```sh
pushover-cli send --title Codex 'Helium development build sent to Mitsuha'
```

Only send that completion message after the build and transfer succeed.

## Reproducible toolchain and test scope

The 29 September build uses common upstream `0dbe337`, macOS platform `24af304`
and Chromium `154.0.8037.57`, commit
`73c14f6228d7cd537c855007e8f88678969cc0eb`. Xcode 27.0 build `27A266a`, its macOS
27.0 SDK and Metal toolchain are installed on Katal. Use Chromium's pinned
Clang, Rust, GN, Siso, Node and DEPS, with `docs/macos-development.gn`.

Retain the complete source checkout. The platform's normal pruning step removes
browser-test fixtures. Apply the three supplemental patches in the order above;
they are outside the production series because release source archives omit
these files. Production and test TypeScript checking remain enabled.

`helium_development_tests` links the container browser tests and selected WebUI
runners using Chromium's normal test launcher and the production browser. Its
WebUI runners load the existing compiled JavaScript suites for bookmarks,
history, appearance, personalization, extensions, the Helium new-tab page and
the wallpaper panel. The settings runners use an ordinary signed-out profile.
The container tests include storage isolation, navigation inheritance, explicit
switching, duplication/restoration, hibernation, deletion, filtered cookie
clearing and persistence across a restart.

The full upstream `browser_tests` executable still contains fixtures that link
against Google sign-in, Safe Browsing and enterprise-analysis services removed
by Helium. It does not currently link in this configuration. The focused target
does not claim full Chromium browser-suite coverage or change production flags.

The C++ supplemental patch adapts shared fixtures to Helium's required noise
maps, disconnected search-engine URL-loader factories and service preferences.
It also updates older fixtures for Helium's defaults and disabled services.
WebUI patches provide the retained interfaces and preferences, and replace
assertions for removed UI with checks of the retained behavior.

Native checks found and fixed container-specific issues in the production
series: the Cocoa shortcut and its settings label, storage inheritance for
noopener windows and links, initial blank-page partition assignment, and parent
relationships for nested macOS sheets.
The popup regression covers both script-created windows and target-blank links.
Blank-page tests check the partition before and after the first navigation,
including deleted or malformed identities. The hibernation fixture explicitly
sets browser focus and waits for the resume navigation.
The normal series also fixes About-page update types and the managed-wallpaper
guard exposed by TypeScript compilation.

Record actual test results in the delivered build report. Compilation or a
successful patch replay alone is not a runtime test result. The bundle declares
macOS 15.0 or newer; the current runtime checks use macOS 27.0. Audit deployment
targets and bundled dependencies, and report older macOS versions as untested
unless the app has actually run there.

## New-tab menu crash regression

`container-tabs-menu-lifetime.patch` fixes repeated openings of the plus-button
menu in both classic and shared tab-strip buttons. A closed native menu runner
still retains its menu model. Destroy the runner before replacing that model,
stop any pending hold timer, and ignore another open request while the menu is
running. Keep Chromium's dangling-pointer checks enabled.

The macOS `HeliumNewTabMenuBrowserTest` cases use real Cocoa menus. Each button
opens and cancels its menu 16 times through mouse, keyboard and the 500 ms hold
timer. Every native opening also attempts a second open while the first menu is
active. The shared-button case checks that its show/close callbacks stay paired,
and both cases remove the owning view after the last menu closes. Run with
`--test-launcher-jobs=1 --test-launcher-retry-limit=0 --use-mock-keychain`.

Also use the packaged app with a disposable profile to open ordinary and
container tabs, cancel and reopen the plus menu, create tab groups and split
views, close and restore tabs, and switch between all four browser layouts. The dynamic toolbar uses a
separate new-tab control without this context menu; test tab creation and
restoration there rather than counting a no-op right-click as a menu check.
The native regression tests complement these manual checks.

The September 29 crash-fix validation reproduced the previous packaged build's
failure on the second right-click after dismissing the first menu. The fixed
package completed repeated menu checks in classic, compact and expanded and
collapsed vertical layouts, with more than 20 tabs across two windows. Work and
Banking container creation, pinning, groups, split views, tab restoration and
window closure also worked. Both native-menu regression cases passed, as did all
16 container executions including the PRE setup and the appearance WebUI suite,
with retries disabled. All 377 production/platform/supplemental patches replayed
without fuzz; repository lint and the focused GN header check passed.

## Profile-picker control on 30 September 2026

`patches/helium/core/customize-profile-picker.patch` adds **Show profile picker**
to the Appearance card in Customize Helium. It uses the existing
`helium.browser.show_avatar_button` preference and updates from changes made
through toolbar customization. The preference defaults to enabled.

The appearance regression checks callback updates and preference changes. Native
checks confirmed immediate hiding and persistence across a clean quit/restart.
The app, chromedriver and focused tests build, and all 27 selected regression
executions pass alongside the incognito/container changes.

## Stable Developer ID packaging

The fork uses bundle identifier `eu.cabraja.helium`, display name `Helium Fork`,
and profile directory `~/Library/Application Support/eu.cabraja.helium`. Keep
these values and the Apple team stable across releases. The separate profile
avoids modifying the official Helium installation. Installing the fork does not
migrate the official profile automatically. The browser's storage-key service is
unchanged; do not delete or replace its Keychain item during installation.

Create a Developer ID Application certificate through Xcode's Apple Accounts
settings using the paid development team. Back up the certificate and matching
private key together as an encrypted PKCS#12 file. Store its password separately
in the password manager. Do not commit the private key, export password,
notarization password or Keychain database. Import the same identity when moving
to another build machine. A replacement certificate from the same team should
retain the default designated requirement, but verify this before distributing a
renewal.

Build `chrome/installer/mac:mac` as well as `chrome` to generate the signing
entitlements. Store notarization credentials interactively in macOS Keychain:

```sh
xcrun notarytool store-credentials helium-fork --apple-id YOUR_APPLE_ID --team-id YOUR_TEAM_ID
```

Use an app-specific password at the prompt. Then package the compiled app:

```sh
python3 packaging/macos/sign_app.py \
  --chromium-src /absolute/path/to/build/src \
  --source-app /absolute/path/to/build/src/out/Default/Helium.app \
  --output-dir /absolute/path/to/new-release-directory \
  --identity CERTIFICATE_SHA1_FINGERPRINT \
  --team-id YOUR_TEAM_ID \
  --notary-profile helium-fork
```

The script copies the app, applies consistent outer and helper bundle IDs, and
signs nested code before its containing framework and application. It reads the
matching Chromium signing manifest and entitlement files. It rejects ad-hoc
identities and release entitlements that allow debugging. It verifies the whole
bundle, submits it to Apple, staples the accepted ticket, checks Gatekeeper and
creates a ZIP, SHA-256 file and package metadata.

`--sign-only` explicitly leaves notarization pending and records that state in
the metadata. A signed-only build is not a notarized release. The current script
packages Apple Silicon builds without Sparkle; it rejects a bundled Sparkle
framework until its updater signing is implemented. Automatic updates remain
disabled in this development configuration.

Replace the installed `Helium Fork.app` after quitting it. Reuse the same bundle
identifier and team on every build. macOS may request access again when moving
from official Helium or an ad-hoc build to this identity. Stable signing does not
transfer permissions granted to a different developer's application.
