#!/bin/bash
# macOS profile backup and optional same-account migration. No extra dependencies.
set -euo pipefail
umask 077

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage: bash backup-helium.sh [--migrate-to fork|user-scripts]
                             [--profile-dir PATH] [--output-dir PATH]

Backs up the complete mainline Helium user-data directory, including every
profile and Local State, to a dated folder in Downloads. Waits for all Helium
apps to quit. Does not quit them for you or change the mainline profile.

--migrate-to fork          Also copy into the auto-updating Helium Fork profile.
--migrate-to user-scripts  Also copy into the separate User Scripts test profile.
                          An existing destination is preserved beside it.
--profile-dir PATH        Override the mainline user-data directory.
--output-dir PATH         Use an existing directory instead of Downloads.
--help                    Show this help.

Run as your normal macOS user, without sudo. Keep Helium closed until finished.
The backup contains private browsing data. Nothing is uploaded, and no Keychain
secret is exported. Encrypted data still needs the existing macOS Keychain.
EOF
}

classify_helium_processes() {
  /usr/bin/awk '
    $0 ~ "/Contents/MacOS/Helium( Helper[^/]*)?$" { found=1 }
    END { print found ? 1 : 0 }
  '
}

helium_running() {
  # CFBundleExecutable stays "Helium" in the signed forks. Include helpers so
  # copying starts only after the network/storage processes have also exited.
  local processes found
  processes=$(/bin/ps -U "$(/usr/bin/id -u)" -o comm=) || die 'Cannot inspect running processes.'
  found=$(printf '%s\n' "$processes" | classify_helium_processes) || die 'Cannot identify running Helium apps.'
  [[ "$found" == 0 || "$found" == 1 ]] || die 'Unexpected process inspection result.'
  [[ "$found" == 1 ]]
}

wait_for_helium() {
  if helium_running; then
    printf '\nQuit all Helium apps with Cmd+Q now. This script will wait.\n'
    printf 'Keep them closed until the script prints "Finished". Ctrl+C cancels.\n'
    while helium_running; do /bin/sleep 2; done
    /bin/sleep 2
  fi
  helium_running && die 'Helium restarted. Quit it and run the script again.'
  return 0
}

assert_helium_closed() {
  helium_running && die 'Helium reopened during the backup. Quit it and run again.'
  return 0
}

copy_profile() {
  local source="$1" target="$2"
  /usr/bin/ditto "$source" "$target"
  # Process locks and the remote-debugging port are specific to the old process.
  # Remove only these entries from the COPY, never from the source profile.
  local entry
  for entry in SingletonLock SingletonSocket SingletonCookie DevToolsActivePort; do
    if [[ -d "$target/$entry" && ! -L "$target/$entry" ]]; then
      die "Unexpected directory at $target/$entry; refusing to remove it."
    fi
    /bin/rm -f "$target/$entry"
  done
}

verify_copy() {
  local source="$1" target="$2" differences
  differences=$(/usr/bin/rsync -nrcil --delete \
    --exclude=/SingletonLock --exclude=/SingletonSocket \
    --exclude=/SingletonCookie --exclude=/DevToolsActivePort \
    "$source/" "$target/")
  [[ -z "$differences" ]] || die 'Profile files changed or the copy differs. No migration was performed.'
}

fork_profile_path() {
  case "$1" in
    fork) printf '%s/Library/Application Support/eu.cabraja.helium\n' "$HOME" ;;
    user-scripts) printf '%s/Library/Application Support/eu.cabraja.helium.userscripts\n' "$HOME" ;;
    *) die 'Choose --migrate-to fork or --migrate-to user-scripts.' ;;
  esac
}

install_profile_copy() {
  local source="$1" destination="$2" backup_dir="$3" stamp="$4"
  local parent prepared saved
  parent=$(/usr/bin/dirname "$destination")
  [[ ! -L "$destination" ]] || die 'The destination is a symlink; refusing to replace it.'
  [[ ! -e "$destination" || -d "$destination" ]] || die 'The destination exists but is not a directory.'
  /bin/mkdir -p "$parent"
  prepared=$(/usr/bin/mktemp -d "$parent/.helium-profile-copy.XXXXXX")
  copy_profile "$source" "$prepared/profile"
  verify_copy "$source" "$prepared/profile"
  assert_helium_closed
  saved="${destination}.before-mainline-${stamp}-$$"
  [[ ! -e "$saved" && ! -L "$saved" ]] || die "Recovery path already exists: $saved"
  if [[ -d "$destination" ]]; then
    /bin/mv "$destination" "$saved"
    printf 'Previous fork profile: %s\n' "$saved" | /usr/bin/tee -a "$backup_dir/MIGRATION.txt"
  fi
  if ! /bin/mv "$prepared/profile" "$destination"; then
    # Restore only if the failed move left the destination absent.
    if [[ ! -e "$destination" && ! -L "$destination" && -d "$saved" ]]; then
      /bin/mv "$saved" "$destination"
    fi
    die "Could not install the profile copy. Recovery files remain in $prepared and $saved."
  fi
  /bin/rmdir "$prepared"
  printf 'Installed profile copy: %s\n' "$destination" | /usr/bin/tee -a "$backup_dir/MIGRATION.txt"
}

main() {
  local source="$HOME/Library/Application Support/net.imput.helium"
  local output="$HOME/Downloads" migrate='' destination=''
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --help|-h) usage; return 0 ;;
      --migrate-to|--profile-dir|--output-dir)
        [[ $# -ge 2 && -n "$2" ]] || die "Missing value for $1"
        case "$1" in
          --migrate-to) migrate="$2" ;;
          --profile-dir) source="$2" ;;
          --output-dir) output="$2" ;;
        esac
        shift 2 ;;
      *) die "Unknown option: $1. Use --help." ;;
    esac
  done
  [[ "$(/usr/bin/uname -s)" == Darwin ]] || die 'This script is for macOS.'
  [[ "$(/usr/bin/id -u)" -ne 0 ]] || die 'Run as your normal macOS user, without sudo.'
  [[ "$source" == /* && "$output" == /* ]] || die 'Use absolute paths for --profile-dir and --output-dir.'
  case "$migrate" in ''|fork|user-scripts) ;; *) die 'Choose --migrate-to fork or --migrate-to user-scripts.' ;; esac
  [[ -d "$source" && -f "$source/Local State" ]] || die "No Helium user-data directory at $source"
  source=$(cd "$source" && pwd -P)
  [[ -d "$output" ]] || die "Create the backup output directory first: $output"
  output=$(cd "$output" && pwd -P)
  case "$output/" in "$source/"*) die 'The backup output cannot be inside the source profile.' ;; esac
  if [[ -n "$migrate" ]]; then
    destination=$(fork_profile_path "$migrate")
    # Refuse equal or nested roots, including a symlinked existing destination.
    [[ ! -L "$destination" ]] || die 'The destination profile is a symlink.'
    if [[ -d "$destination" ]]; then destination=$(cd "$destination" && pwd -P); fi
    case "$source/" in "$destination/"*) die 'Source and destination profiles overlap.' ;; esac
    case "$destination/" in "$source/"*) die 'Source and destination profiles overlap.' ;; esac
    case "$output/" in "$destination/"*) die 'The backup output cannot be inside the destination profile.' ;; esac
    case "$destination/" in "$output/"*) die 'The destination profile cannot be inside the backup output.' ;; esac
  fi
  printf 'Mainline profile: %s\nBackup location: %s\n' "$source" "$output"
  [[ -z "$destination" ]] || printf 'Migration destination: %s\n' "$destination"
  wait_for_helium

  local stamp backup_dir work archive_name archive
  stamp=$(/bin/date '+%Y%m%d-%H%M%S')
  backup_dir=$(/usr/bin/mktemp -d "$output/Helium-profile-backup-${stamp}.XXXXXX")
  work="$backup_dir/.work"
  /bin/mkdir "$work"
  printf '\nCopying the complete profile. Large profiles can take several minutes.\n'
  copy_profile "$source" "$work/Profile"
  assert_helium_closed
  verify_copy "$source" "$work/Profile"

  archive_name="Helium-mainline-profile-${stamp}.zip"
  archive="$backup_dir/$archive_name"
  printf 'Creating and checking the archive...\n'
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$work/Profile" "$archive.partial"
  /usr/bin/unzip -tq "$archive.partial" > "$backup_dir/archive-check.txt"
  assert_helium_closed
  verify_copy "$source" "$work/Profile"
  /bin/mv "$archive.partial" "$archive"
  /bin/chmod 600 "$archive"
  (cd "$backup_dir" && /usr/bin/shasum -a 256 "$archive_name" > "$archive_name.sha256")
  cat > "$backup_dir/RESTORE.txt" <<EOF
Helium profile backup created $stamp
Original profile: $source
Archive: $archive_name

This contains every on-disk profile and Local State, including stored sessions,
bookmarks, extensions and site data. Incognito state held in memory is not saved.
Only process-lock files and DevToolsActivePort were omitted.

This is private, unencrypted browser data. Keep this folder private.
No Keychain secret was exported. On this same Mac and macOS account, the fork
uses the existing Helium Storage Key. Approve access for your trusted signed
Helium Fork app when macOS asks. Moving to a different Mac needs that Keychain
as well; the profile ZIP alone is not a complete credential transfer.

To restore: quit every Helium app, extract the ZIP, and use its Profile folder
as the complete user-data directory. Rename an existing destination aside first;
do not merge two profiles. Keep the original and this backup until you have
verified your tabs, bookmarks and logins. The script never changes the original.
If tabs do not reopen, use History > Recently Closed or Cmd+Shift+T.
EOF
  printf 'Verified backup: %s\n' "$archive"
  if [[ -n "$destination" ]]; then
    printf '\nPreparing a separate copy for the fork...\n'
    install_profile_copy "$work/Profile" "$destination" "$backup_dir" "$stamp"
  fi
  /bin/rm -rf "$work"
  printf '\nFinished. Backup folder:\n%s\n' "$backup_dir"
  if [[ -n "$destination" ]]; then
    printf 'You can now open the selected fork. Approve its Helium Storage Key prompt.\n'
  else
    printf 'Backup only: the fork profile has not been changed.\n'
  fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
