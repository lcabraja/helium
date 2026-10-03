#!/bin/bash
# All profile data is synthetic. Never invokes or closes a real browser.
set -euo pipefail
umask 077
repo=$(cd "$(dirname "$0")/.." && pwd)
fixture=$(/usr/bin/mktemp -d /tmp/helium-profile-backup-test.XXXXXX)
trap '/bin/rm -rf "$fixture"' EXIT
source "$repo/scripts/backup-helium.sh"
helium_running() { return 1; }
fork_profile_path() { printf '%s\n' "$fixture/Fork profile"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

[[ $(printf '%s\n' '/Applications/Helium.app/Contents/MacOS/Helium' | classify_helium_processes) == 1 ]] || fail 'Mainline process missed'
[[ $(printf '%s\n' '/Applications/Helium Fork.app/Contents/MacOS/Helium' | classify_helium_processes) == 1 ]] || fail 'Fork process missed'
[[ $(printf '%s\n' '/Applications/Helium.app/Contents/Frameworks/Helium Helper.app/Contents/MacOS/Helium Helper (Renderer)' | classify_helium_processes) == 1 ]] || fail 'Helper process missed'
[[ $(printf '%s\n' '/bin/bash' '/Applications/Other.app/Contents/MacOS/Other' | classify_helium_processes) == 0 ]] || fail 'Unrelated process blocked'

mainline="$fixture/Mainline profile"
/bin/mkdir -p "$mainline/Default/Sessions" "$mainline/Profile 1" "$fixture/Downloads" "$fixture/Fork profile"
printf '{"fixture":true}\n' > "$mainline/Local State"
printf 'cookies-and-passwords-fixture\000\377\n' > "$mainline/Default/Login Data"
printf 'session-fixture\n' > "$mainline/Default/Sessions/Session_123"
printf 'second-profile\n' > "$mainline/Profile 1/Bookmarks"
printf 'existing fork data\n' > "$fixture/Fork profile/keep-me"
/bin/ln -s missing-socket "$mainline/SingletonSocket"
/bin/ln -s fixture-999999 "$mainline/SingletonLock"
printf '1234\n' > "$mainline/DevToolsActivePort"

(main --profile-dir "$mainline" --output-dir "$fixture/Downloads" --migrate-to fork) > "$fixture/run.log"
backups=("$fixture/Downloads"/Helium-profile-backup-*)
[[ ${#backups[@]} == 1 ]] || fail 'Expected one dated backup folder'
backup="${backups[0]}"
archives=("$backup"/*.zip)
[[ ${#archives[@]} == 1 ]] || fail 'Expected one complete archive'
(cd "$backup" && /usr/bin/shasum -a 256 -c "$(basename "${archives[0]}").sha256")
/usr/bin/ditto -x -k "${archives[0]}" "$fixture/Extracted"
verify_copy "$mainline" "$fixture/Extracted/Profile"
verify_copy "$mainline" "$fixture/Fork profile"
[[ -L "$mainline/SingletonLock" && -f "$mainline/DevToolsActivePort" ]] || fail 'Source lock files changed'
[[ ! -e "$fixture/Fork profile/SingletonLock" && ! -L "$fixture/Fork profile/SingletonLock" ]] || fail 'Copied lock survived'
previous=("$fixture"/Fork\ profile.before-mainline-*)
[[ ${#previous[@]} == 1 && -f "${previous[0]}/keep-me" ]] || fail 'Previous destination was not preserved'
[[ $(/usr/bin/stat -f %Lp "$backup") == 700 ]] || fail 'Backup directory not private'
[[ $(/usr/bin/stat -f %Lp "${archives[0]}") == 600 ]] || fail 'Archive not private'

# Default operation makes a backup without installing into the fork.
printf 'after-migration sentinel\n' > "$fixture/Fork profile/sentinel"
/bin/mkdir "$fixture/Backup only"
(main --profile-dir "$mainline" --output-dir "$fixture/Backup only") > "$fixture/backup-only.log"
[[ -f "$fixture/Fork profile/sentinel" ]] || fail 'Backup-only touched the fork'

# Reject incomplete and recursive input before writing a backup.
if (main --profile-dir "$fixture/No profile" --output-dir "$fixture/Downloads") > /dev/null 2>&1; then fail 'Missing profile accepted'; fi
if (main --profile-dir "$mainline" --output-dir "$mainline/Default") > /dev/null 2>&1; then fail 'Nested output accepted'; fi
if (main --profile-dir "$mainline" --output-dir "$fixture/Downloads" --migrate-to unknown) > /dev/null 2>&1; then
  fail 'Unknown migration target accepted'
fi

# A byte mismatch or a browser reopening must stop installation.
printf 'changed\n' >> "$fixture/Extracted/Profile/Local State"
if (verify_copy "$mainline" "$fixture/Extracted/Profile") > /dev/null 2>&1; then fail 'Changed copy accepted'; fi
if (helium_running() { return 0; }; assert_helium_closed) > /dev/null 2>&1; then fail 'Running browser accepted'; fi

# Refuse replacing symlinked destinations.
/bin/ln -s "$fixture/Fork profile" "$fixture/Linked profile"
if (install_profile_copy "$mainline" "$fixture/Linked profile" "$backup" fixture) > /dev/null 2>&1; then fail 'Symlink destination accepted'; fi
printf 'PASS: backup, archive integrity, complete migration, preservation, permissions, and failure guards\n'
