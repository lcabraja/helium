# Building the container-tab development app

Use the current fork's `main` together with the matching
[`imputnet/helium-macos`](https://github.com/imputnet/helium-macos) platform tools.
The September 2026 rebase uses Chromium `154.0.8037.57` and was checked against
platform commit `c464a10`. Follow that repository's build instructions, including
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
2. Resolve patch, GN, compiler and linker failures in the maintained patches.
   Reapply patches to confirm fixes survive a fresh build. Do not leave fixes
   only in the generated Chromium tree.
3. For a source checkout containing Chromium's test data, apply
   `docs/container-tabs-webui-tests.patch`. Build `browser_tests` and run
   `ContainerBrowserTest.*`, including the `PRE_` restart test. Run the modified
   bookmark, history and settings WebUI checks.
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
