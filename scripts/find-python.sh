#!/usr/bin/env bash
# Diagnostic: list every Python 3.x interpreter we can find on this machine,
# with version + path. Use this when offline-setup.sh can't find one and you
# don't know where Python lives on the offline box.
#
# Run:   ./scripts/find-python.sh
#
# Then either:
#   - Add the right one to PATH:  export PATH="<dir>:$PATH"
#   - Or point the wizard at it:  PY=<full path> ./scripts/offline-setup.sh

set -uo pipefail

echo "== Python interpreters discovered =="
echo ""

# Build a candidate list from PATH + common off-PATH locations.
EXTRA_DIRS=(
  /usr/bin /usr/local/bin
  /opt/homebrew/bin
  /Library/Frameworks/Python.framework/Versions/3.12/bin
  /Library/Frameworks/Python.framework/Versions/3.11/bin
  "$HOME/.pyenv/versions"
  "$HOME/anaconda3/bin" "$HOME/miniconda3/bin" "$HOME/miniforge3/bin"
  /opt/anaconda3/bin /opt/miniconda3/bin /opt/miniforge3/bin
  "$HOME/.local/share/uv/python"
)

# macOS ships bash 3.2 — no associative arrays. Track seen paths via a delimited
# string, and remember resolved paths for the final recommendation pass.
SEEN_LIST=""
USABLE_LIST=""   # newline-separated "<ver>\t<real-path>" entries

_report() {
  local p="$1"
  [[ -x "$p" ]] || return
  local real
  real="$(readlink -f "$p" 2>/dev/null || python -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$p" 2>/dev/null || echo "$p")"
  case "|$SEEN_LIST|" in *"|$real|"*) return;; esac
  SEEN_LIST="$SEEN_LIST|$real"
  local ver
  ver="$("$p" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)" || return
  local flag=""
  case "$ver" in
    3.11.*|3.12.*) flag=" ✅ usable"; USABLE_LIST="$USABLE_LIST
$ver	$real" ;;
    3.*)           flag=" (need 3.11 or 3.12)" ;;
  esac
  printf "  %-60s  python %s%s\n" "$p" "$ver" "$flag"
}

# 1. PATH
echo "-- from PATH --"
for cmd in python python3 python3.10 python3.11 python3.12 python3.13; do
  while IFS= read -r p; do
    [[ -n "$p" ]] && _report "$p"
  done < <(command -v -a "$cmd" 2>/dev/null || true)
done

# 2. Off-PATH common locations
echo ""
echo "-- from common install locations --"
for d in "${EXTRA_DIRS[@]}"; do
  [[ -d "$d" ]] || continue
  for v in python python3 python3.10 python3.11 python3.12 python3.13; do
    [[ -x "$d/$v" ]] && _report "$d/$v"
  done
  while IFS= read -r p; do
    _report "$p"
  done < <(
    find "$d" -maxdepth 4 \
      \( -name 'python3.11' -o -name 'python3.12' -o -name 'python3' \) \
      -type f 2>/dev/null
  )
done

# 3. Pick the best one and print the exact invocation.
echo ""
echo "== Recommendation =="
BEST=""
# Prefer 3.12 over 3.11.
BEST="$(printf '%s\n' "$USABLE_LIST" | awk -F'\t' '$1 ~ /^3\.12\./ {print $2; exit}')"
if [[ -z "$BEST" ]]; then
  BEST="$(printf '%s\n' "$USABLE_LIST" | awk -F'\t' '$1 ~ /^3\.11\./ {print $2; exit}')"
fi

if [[ -n "$BEST" ]]; then
  echo "  Use this one:  $BEST"
  echo ""
  echo "  PY=$BEST ./scripts/offline-setup.sh"
else
  echo "  No 3.11 / 3.12 found. Install one of:"
  echo "    macOS:  brew install python@3.12   (or download from python.org)"
  echo "    Linux:  apt install python3.12     (Debian/Ubuntu)"
  echo "            dnf install python3.12     (Fedora/RHEL)"
  echo "    Cross:  pyenv install 3.12"
  echo ""
  echo "  Then re-run this script."
fi
