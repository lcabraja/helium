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
2. Resolve patch, GN, compiler and linker failures in the maintained patches.
   Reapply patches to confirm fixes survive a fresh build. Do not leave fixes
   only in the generated Chromium tree.
3. For a source checkout containing Chromium's test data, apply
   `docs/container-tabs-webui-tests.patch`. Build `browser_tests` and run
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

## Deliver to Mitsuha

Package the app as a DMG or a ZIP that preserves macOS bundle metadata and
symlinks, for example with `ditto -c -k --sequesterRsrc --keepParent`. Include a
SHA-256 checksum and a short report listing architecture, macOS deployment
target, Xcode version, source revisions and test results.

Discover Mitsuha in `tailscale status` and use Taildrop to send the archive,
checksum and report to `mitsuha`. This build is for local development. Keep its
profile separate from the user's regular browser data.

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
The build uses the macOS 27.0 SDK with a macOS 15.0 deployment target and a
non-component arm64 configuration. A complete build and runtime validation
are still required; successful patch application does not establish either.
