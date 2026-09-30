#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
platform_tree="${HELIUM_PLATFORM_TREE:-$(cd -- "$script_dir/../../.." && pwd)}"
build_environment="$platform_tree/../build-env.sh"
if [ -f "$build_environment" ]; then
  source "$build_environment"
fi
exec python3 "$script_dir/release.py" --platform-tree "$platform_tree" "$@"
