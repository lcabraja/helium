# Local macOS releases

On Katal, commit and push your patch changes, then run this from the repository:

```sh
./packaging/macos/release.sh
```

The command replays the common and platform patches, applies branding and
translations, copies changed source files, and builds with the existing Siso
cache. It packages `Helium Fork.app` with the stable Developer ID, notarizes it,
staples Apple's ticket, and verifies the extracted archive with codesign and
Gatekeeper. It then generates and verifies Sparkle's archive and feed signatures.

After verification it uploads a draft GitHub Release, makes the download public,
checks the public download's SHA-256, and publishes the signed appcast on the
`gh-pages` branch. The command creates GitHub Pages for that branch on its first
run and waits until Pages serves the exact signed feed. No Chromium build runs
in GitHub Actions. GitHub's small Pages deployment still runs there.

Downloads: <https://github.com/lcabraja/helium/releases>

Feed: <https://lcabraja.github.io/helium/mac/appcast-arm64.xml>

Only Apple Silicon is supported by this recipe. The app requires macOS 15 or
newer. Keep the bundle ID `eu.cabraja.helium`, Apple team and profile directory
stable. Install the first updater-enabled build manually once. Browser updates
respect the existing Helium Services consent and browser-update preference.
Enable browser updates in Settings → Privacy and security → Helium services.
Updates download in the background and install on quit or through the About
page's relaunch button.

## Requirements

Use the prepared `helium-macos` platform workspace containing this repository
as `helium-chromium` and a full, pinned Chromium Git checkout at `build/src`.
The recipe does not download a new Chromium version, change DEPS, reset your
checkout, or discard `out/Default`. Chromium upgrades and changes to global
domain/name substitution rules require the normal full platform preparation.
Do not edit generated source files independently of maintained patches. The
publisher detects such edits after its first source replay and stops.

Katal's `build-env.sh` selects its pinned Python dependencies, Xcode and tools.
For another machine, set `HELIUM_PLATFORM_TREE`, provide Python 3.13 with the
platform build dependencies, install GNU patch and GitHub CLI with Homebrew,
and import the signing identities. Authenticate `gh` with access to the fork,
GitHub Releases and Pages. Set Git's commit name and email for the Pages branch.

`release-config.json` contains public configuration only. Apple signing and
notarization credentials stay in Keychain. Sparkle uses the Keychain account
`eu.cabraja.helium`. Its public key is committed; its private key is never
committed, logged, sent to GitHub, or passed in a process argument. Back up
`Sparkle-update-private-key.txt` from the Desktop signing folder to 1Password
alongside the existing Developer ID backup. Import it on another builder with
Sparkle's `generate_keys --account eu.cabraja.helium -f /private/path/to/key.txt`.
Never generate a new key just to make a release.

The script downloads Sparkle 2.10.0 publishing tools from the official release
and verifies the pinned SHA-256. The app's framework comes from the matching
platform's Sparkle source, built without optional XPC services. The packager
signs Autoupdate and Updater.app before Sparkle and the containing frameworks.

## Options and recovery

```sh
# Supply public release notes.
./packaging/macos/release.sh --notes-file /absolute/path/to/notes.md

# Build and verify locally without publishing.
./packaging/macos/release.sh --build-only

# Publish a completed build after fixing a network or GitHub failure.
./packaging/macos/release.sh --publish-only /absolute/path/to/completed-run

# Replay source patches only, including uncommitted development changes.
./packaging/macos/release.sh --prepare-only

# Test the publisher's failure handling.
python3 -m unittest discover -s packaging/macos -p 'test_*.py'
```

Each run prints its output directory, which contains `release.log`, the signed
app, archive, checksum, notarization result and release metadata. Source files
overwritten during replay are backed up there. The public release receives only
the archive, checksum and release metadata, never the source backup or log.

Build numbers are integers, allocated above both the last feed version and the
local counter in `platform/build/local-release-counter.txt`. Failed runs may
leave gaps. The human-readable Helium version remains separate. Published
archives are immutable; retrying publication never replaces a public archive.
The feed is updated only after the public archive passes its checksum check.
A failed upload leaves the previous feed usable. A failed Pages deployment can
be retried with `--publish-only`, without another build or notarization.

The script takes a local lock and never force-pushes Pages. If another machine
publishes a newer build, rebuild with the next allocated version. Keep the
source commit available on the configured fork before releasing. Tags use
`macos-N`, separately from the upstream source-version release workflow.
