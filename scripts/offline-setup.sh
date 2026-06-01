#!/usr/bin/env bash
# Offline setup wizard — run inside the repo on the OFFLINE machine.
#
# Idempotent: re-run any time to update / verify.
#
# What it does, in order:
#   1. checks python (3.11 or 3.12)
#   2. creates .venv if missing
#   3. installs backend deps — prefers ../vendor/ (from offline-prep) if present,
#      otherwise tries pip (will fail cleanly on truly air-gapped machines)
#   4. installs the project editable (pip install -e backend --no-deps)
#   5. seeds .env from .env.example if .env doesn't exist
#   6. runs the data_analysis test suite as a smoke test
#   7. prints the next-step commands

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
VENV="$REPO_ROOT/.venv"
VENDOR="$(cd "$REPO_ROOT/.." && pwd)/vendor"  # offline-prep places it one level up
PIP_OPTS=()

echo "[setup] repo: $REPO_ROOT"
echo "[setup] (1/7) checking python ..."
# Priority:
#   1. $PY env var (caller knows best)
#   2. python3.12 / python3.11 / python3 on PATH
#   3. common install locations that may NOT be on PATH (Homebrew, conda envs,
#      pyenv shims, uv-managed pythons, official mac installer, opt/, /usr/local)
#
# If your python is somewhere else: run `./scripts/find-python.sh` to discover
# candidates, then `PY=/abs/path/to/python ./scripts/offline-setup.sh`.

_check_python() {
  local p="$1"
  [[ -x "$p" ]] || return 1
  local ver
  ver="$("$p" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || return 1
  [[ "$ver" == "3.12" || "$ver" == "3.11" ]] || return 1
  echo "$ver"
}

CHOSEN=""
CHOSEN_VER=""

# (1) explicit override
if [[ -n "${PY:-}" ]]; then
  if ver="$(_check_python "$PY")"; then
    CHOSEN="$PY"; CHOSEN_VER="$ver"
    echo "[setup]   using \$PY override: $PY (python $ver)"
  else
    echo "[setup] ERROR: \$PY=$PY is not python 3.11 / 3.12 or not executable." >&2
    exit 1
  fi
fi

# (2) PATH
if [[ -z "$CHOSEN" ]]; then
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      p="$(command -v "$candidate")"
      if ver="$(_check_python "$p")"; then
        CHOSEN="$p"; CHOSEN_VER="$ver"
        echo "[setup]   found on PATH: $p (python $ver)"
        break
      fi
    fi
  done
fi

# (3) common install locations that aren't necessarily on PATH
if [[ -z "$CHOSEN" ]]; then
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
  # Allow caller to add custom-compiled python locations (colon-separated).
  if [[ -n "${PY_EXTRA_DIRS:-}" ]]; then
    IFS=':' read -r -a _PY_EXTRA <<< "$PY_EXTRA_DIRS"
    EXTRA_DIRS=("${_PY_EXTRA[@]}" "${EXTRA_DIRS[@]}")
  fi
  # globs for pyenv / uv style nested layouts
  CANDIDATES=()
  for d in "${EXTRA_DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    # direct python3.x in the dir
    for v in python3.12 python3.11; do
      [[ -x "$d/$v" ]] && CANDIDATES+=("$d/$v")
    done
    # nested (pyenv/uv): <d>/<version>/bin/python3.x
    while IFS= read -r p; do CANDIDATES+=("$p"); done < <(
      find "$d" -maxdepth 4 \( -name 'python3.12' -o -name 'python3.11' \) -type f 2>/dev/null
    )
  done
  for p in "${CANDIDATES[@]}"; do
    if ver="$(_check_python "$p")"; then
      CHOSEN="$p"; CHOSEN_VER="$ver"
      echo "[setup]   found off-PATH: $p (python $ver)"
      break
    fi
  done
fi

if [[ -z "$CHOSEN" ]]; then
  echo "" >&2
  echo "[setup] ERROR: no python 3.11 / 3.12 found on PATH or in common locations." >&2
  echo "[setup] Try one of:" >&2
  echo "  1. Run ./scripts/find-python.sh to see what's available" >&2
  echo "  2. Re-run with PY pointing at the binary: " >&2
  echo "       PY=/abs/path/to/python3.12 ./scripts/offline-setup.sh" >&2
  echo "  3. Install Python 3.12 (or 3.11) via your package manager / pyenv / conda" >&2
  echo "       then re-run this script — it'll discover it." >&2
  exit 1
fi
PY="$CHOSEN"
echo "[setup]   using $PY (python $CHOSEN_VER)"

echo "[setup] (2/7) ensuring venv at $VENV ..."
if [[ ! -d "$VENV" ]]; then
  "$PY" -m venv "$VENV"
  echo "[setup]   venv created"
else
  echo "[setup]   venv exists, reusing"
fi
VPY="$VENV/bin/python"

if [[ -d "$VENDOR" ]]; then
  echo "[setup] (3/7) installing deps from $VENDOR (air-gapped mode) ..."
  PIP_OPTS=(--no-index --find-links "$VENDOR")
else
  echo "[setup] (3/7) no vendor/ dir found — falling back to PyPI"
  echo "[setup]   (if this machine has no internet, run offline-prep.sh on an online machine first)"
fi
"$VPY" -m pip install --quiet --upgrade pip "${PIP_OPTS[@]}" 2>/dev/null || \
  "$VPY" -m pip install --upgrade pip "${PIP_OPTS[@]}"
"$VPY" -m pip install --quiet -r backend/requirements.txt "${PIP_OPTS[@]}"
"$VPY" -m pip install --quiet pytest "${PIP_OPTS[@]}" || true  # pytest needed for smoke test

echo "[setup] (4/7) installing project editable ..."
"$VPY" -m pip install --quiet -e backend --no-deps

echo "[setup] (5/7) checking .env ..."
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "[setup]   seeded .env from .env.example — edit it before running eval"
  else
    cat > .env <<'EOF'
# Required for `replay_cli eval` (live LLM). Other commands work without these.
MINIMAX_BASE_URL=
MINIMAX_API_KEY=
MINIMAX_MODEL=
EOF
    echo "[setup]   created skeleton .env — fill in MINIMAX_* if you want to run eval"
  fi
else
  echo "[setup]   .env already present"
fi

echo "[setup] (6/7) smoke test — pytest tests/data_analysis/ ..."
"$VPY" -m pytest tests/data_analysis/ -q 2>&1 | tail -3

echo ""
echo "[setup] (7/7) ✅ ready. Next steps:"
cat <<EOF

  # Activate the venv for this shell:
  source "$VENV/bin/activate"

  # Run the offline-verification checklist:
  cd "$REPO_ROOT/backend"
  set -a && . ../.env && set +a && export PYTHONPATH=.
  CLI="python -m open_webui.utils.data_analysis.replay_cli"

  \$CLI --since-days 30 report
  \$CLI --since-days 30 intents --top 20
  \$CLI --since-days 30 satisfaction
  \$CLI --since-days 30 fit
  \$CLI --since-days 30 regression
  # \$CLI --since-days 30 eval    # needs MINIMAX_* in .env + network to the LLM

  # Full checklist with fill-in fields:
  open "$REPO_ROOT/docs/offline-verification-checklist.md"
EOF
