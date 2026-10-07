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
mainline_profile_path() { printf '%s\n' "$fixture/Mainline profile"; }
mainline_browser_version() { printf '154.0.8037.57\n'; }
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }

[[ $(printf '%s\n' '/Applications/Helium.app/Contents/MacOS/Helium' | classify_helium_processes) == 1 ]] || fail 'Mainline process missed'
[[ $(printf '%s\n' '/Applications/Helium Fork.app/Contents/MacOS/Helium' | classify_helium_processes) == 1 ]] || fail 'Fork process missed'
[[ $(printf '%s\n' '/Applications/Helium-3.app/Contents/MacOS/Helium' | classify_helium_processes) == 1 ]] || fail 'Renamed app process missed'
[[ $(printf '%s\n' '/Applications/Helium.app/Contents/Frameworks/Helium Helper.app/Contents/MacOS/Helium Helper (Renderer)' | classify_helium_processes) == 1 ]] || fail 'Helper process missed'
[[ $(printf '%s\n' '/bin/bash' '/Applications/Other.app/Contents/MacOS/Other' | classify_helium_processes) == 0 ]] || fail 'Unrelated process blocked'

mainline="$fixture/Mainline profile"
/bin/mkdir -p "$mainline/Default/Sessions" "$mainline/Profile 1" "$fixture/Downloads" "$fixture/Fork profile"
printf '{"fixture":true}\n' > "$mainline/Local State"
printf '154.0.8037.57' > "$mainline/Last Version"
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
previous=("$fixture"/Fork\ profile.before-migration-*)
[[ ${#previous[@]} == 1 && -f "${previous[0]}/keep-me" ]] || fail 'Previous destination was not preserved'
[[ $(/usr/bin/stat -f %Lp "$backup") == 700 ]] || fail 'Backup directory not private'
[[ $(/usr/bin/stat -f %Lp "${archives[0]}") == 600 ]] || fail 'Archive not private'
[[ ! -e "$backup/.work" ]] || fail 'Successful migration retained staging data'

# Simulate the reported failure after ZIP verification but before installation.
/bin/mkdir "$fixture/Interrupted backups" "$fixture/Resume profile"
fork_profile_path() { printf '%s\n' "$fixture/Resume profile"; }
if (install_profile_copy() { exit 73; }; main --profile-dir "$mainline" --output-dir "$fixture/Interrupted backups" --migrate-to helium-3) > "$fixture/interrupted.log"; then
  fail 'Simulated interrupted migration unexpectedly succeeded'
fi
interrupted=("$fixture/Interrupted backups"/Helium-profile-backup-*)
resume="${interrupted[0]}"
resume_archives=("$resume"/*.zip)
resume_archive="${resume_archives[0]}"
[[ -f "$resume/.work/Profile/Local State" ]] || fail 'Interrupted migration lost complete staging copy'
staging_inode=$(/usr/bin/stat -f %i "$resume/.work/Profile")
printf 'destination must survive failed resume\n' > "$fixture/Resume profile/resume-sentinel"

# Invalid archives, changed staging or live data, and repeated installation fail
# before changing either profile. Restore each synthetic input after rejection.
original_digest=$(/bin/cat "$resume_archive.sha256")
printf '%064d  ignored-name.zip\n' 0 > "$resume_archive.sha256"
if (main --resume-backup "$resume" --migrate-to helium-3) > /dev/null 2>&1; then fail 'Bad checksum accepted'; fi
printf '%s\n' "$original_digest" > "$resume_archive.sha256"
printf 'changed\n' > "$resume/.work/Profile/Local State"
if (main --resume-backup "$resume" --migrate-to helium-3) > /dev/null 2>&1; then fail 'Changed staging accepted'; fi
/bin/cp -p "$mainline/Local State" "$resume/.work/Profile/Local State"
printf 'new browsing data\n' > "$mainline/new-data"
if (main --resume-backup "$resume" --migrate-to helium-3) > /dev/null 2>&1; then fail 'Changed live profile accepted'; fi
/bin/rm "$mainline/new-data"
printf 'previous installation\n' > "$resume/MIGRATION.txt"
if (main --resume-backup "$resume" --migrate-to helium-3) > /dev/null 2>&1; then fail 'Already installed backup accepted'; fi
/bin/rm "$resume/MIGRATION.txt"
if (main --resume-backup "$resume") > /dev/null 2>&1; then fail 'Resume without direction accepted'; fi
[[ -f "$fixture/Resume profile/resume-sentinel" ]] || fail 'Failed resume changed destination'

# Same-volume recovery must move the completed copy without copying or archiving
# again. The directory inode proves it reused the staging copy, not the source.
(copy_profile() { fail 'Resume attempted another profile copy'; }; main --resume-backup "$resume" --migrate-to helium-3) > "$fixture/resume.log"
[[ $(/usr/bin/stat -f %i "$fixture/Resume profile") == "$staging_inode" ]] || fail 'Resume did not reuse staging copy'
[[ -d "$mainline" && -L "$mainline/SingletonLock" ]] || fail 'Resume moved or modified the original profile'
verify_copy "$mainline" "$fixture/Resume profile"
[[ -f "$resume_archive" && ! -e "$resume/.work" ]] || fail 'Resume removed ZIP or left staging data'
[[ -f "$(/usr/bin/sed -n 's/^Previous destination profile: //p' "$resume/MIGRATION.txt")/resume-sentinel" ]] || fail 'Resume lost previous destination'
if (main --resume-backup "$resume" --migrate-to helium-3) > /dev/null 2>&1; then fail 'Completed resume accepted again'; fi

fork_profile_path() { printf '%s\n' "$fixture/Fork profile"; }

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
/bin/mkdir -p "$fixture/Symlink backup/.work"
copy_profile "$mainline" "$fixture/Symlink backup/.work/Profile"
if (install_profile_copy "$fixture/Symlink backup/.work/Profile" "$fixture/Linked profile" "$fixture/Symlink backup" fixture) > /dev/null 2>&1; then fail 'Symlink destination accepted'; fi
[[ -f "$fixture/Symlink backup/.work/Profile/Local State" ]] || fail 'Rejected destination consumed staging data'

# Reverse migration brings new fork data back and retains the mainline state.
printf 'new fork bookmark\n' > "$fixture/Fork profile/Default/new-bookmark"
printf 'mainline sentinel\n' > "$mainline/sentinel"
/bin/mkdir "$fixture/Reverse backups"
(main --reverse-from helium-3 --output-dir "$fixture/Reverse backups") > "$fixture/reverse.log"
[[ -f "$mainline/Default/new-bookmark" ]] || fail 'Reverse migration missed new data'
preserved=("$fixture"/Mainline\ profile.before-migration-*)
[[ ${#preserved[@]} == 1 && -f "${preserved[0]}/sentinel" ]] || fail 'Reverse migration lost original mainline'
[[ -f "$fixture/Fork profile/Default/new-bookmark" ]] || fail 'Reverse migration changed source'

# A Chromium downgrade or ambiguous direction is refused before backup/install.
printf '155.0.1.1' > "$fixture/Fork profile/Last Version"
if (main --reverse-from helium-3 --output-dir "$fixture/Reverse backups") > /dev/null 2>&1; then fail 'Downgrade accepted'; fi
[[ $(/bin/cat "$mainline/Last Version") == 154.0.8037.57 ]] || fail 'Downgrade changed destination'
if (main --reverse-from helium-3 --migrate-to helium-3 --output-dir "$fixture/Downloads") > /dev/null 2>&1; then fail 'Ambiguous direction accepted'; fi
printf '154.0.8037.58' > "$fixture/Fork profile/Last Version"
if (check_reverse_version "$fixture/Fork profile") > /dev/null 2>&1; then fail 'Patch-version downgrade accepted'; fi
printf '154.0.8037.56' > "$fixture/Fork profile/Last Version"
check_reverse_version "$fixture/Fork profile"
printf 'PASS: backup, forward/reverse migration, interrupted recovery without recopying, integrity, preservation, permissions, process detection and downgrade guards\n'
