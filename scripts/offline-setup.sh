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
echo "[setup] (1/7) selecting python ..."
# Selection priority:
#   1. $PY env var      — caller already knows the path, skip all UI
#   2. interactive Q&A  — when stdin is a tty, ask user to scan or enter path
#   3. auto-scan        — non-interactive (CI / sub-shell) falls back to first
#                         usable candidate from PATH + common install locations
#
# PY_EXTRA_DIRS=dir1:dir2  prepends extra search dirs (custom-compiled paths).

_check_python() {
  local p="$1"
  [[ -x "$p" ]] || return 1
  local ver
  ver="$("$p" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || return 1
  [[ "$ver" == "3.12" || "$ver" == "3.11" ]] || return 1
  echo "$ver"
}

# Scan PATH + common install locations + PY_EXTRA_DIRS. Prints unique usable
# candidates to stdout, one per line as "<abs-path>\t<version>".
_scan_pythons() {
  local seen_list="" cmd p d v ver real
  # PATH
  for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      while IFS= read -r p; do
        [[ -n "$p" ]] || continue
        real="$(cd "$(dirname "$p")" 2>/dev/null && pwd -P)/$(basename "$p")"
        case "|$seen_list|" in *"|$real|"*) continue;; esac
        seen_list="$seen_list|$real"
        ver="$(_check_python "$real")" && printf '%s\t%s\n' "$real" "$ver"
      done < <(command -v -a "$cmd" 2>/dev/null || true)
    fi
  done
  # Off-PATH
  local EXTRA_DIRS=(
    /usr/bin /usr/local/bin
    /opt/homebrew/bin
    /Library/Frameworks/Python.framework/Versions/3.12/bin
    /Library/Frameworks/Python.framework/Versions/3.11/bin
    "$HOME/.pyenv/versions"
    "$HOME/anaconda3/bin" "$HOME/miniconda3/bin" "$HOME/miniforge3/bin"
    /opt/anaconda3/bin /opt/miniconda3/bin /opt/miniforge3/bin
    "$HOME/.local/share/uv/python"
  )
  if [[ -n "${PY_EXTRA_DIRS:-}" ]]; then
    local _extra
    IFS=':' read -r -a _extra <<< "$PY_EXTRA_DIRS"
    EXTRA_DIRS=("${_extra[@]}" "${EXTRA_DIRS[@]}")
  fi
  for d in "${EXTRA_DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    for v in python3.12 python3.11; do
      p="$d/$v"
      [[ -x "$p" ]] || continue
      real="$(cd "$(dirname "$p")" 2>/dev/null && pwd -P)/$(basename "$p")"
      case "|$seen_list|" in *"|$real|"*) continue;; esac
      seen_list="$seen_list|$real"
      ver="$(_check_python "$real")" && printf '%s\t%s\n' "$real" "$ver"
    done
    while IFS= read -r p; do
      [[ -n "$p" ]] || continue
      real="$(cd "$(dirname "$p")" 2>/dev/null && pwd -P)/$(basename "$p")"
      case "|$seen_list|" in *"|$real|"*) continue;; esac
      seen_list="$seen_list|$real"
      ver="$(_check_python "$real")" && printf '%s\t%s\n' "$real" "$ver"
    done < <(find "$d" -maxdepth 4 \( -name 'python3.12' -o -name 'python3.11' \) -type f 2>/dev/null)
  done
}

# Prompt for a path until a valid 3.11/3.12 binary is given (or user quits).
_prompt_custom_path() {
  local p ver
  while :; do
    printf "  Enter absolute path to python3.11/3.12 binary (or 'q' to quit): " >&2
    IFS= read -r p
    [[ "$p" == "q" || "$p" == "Q" || -z "$p" ]] && return 1
    if ver="$(_check_python "$p")"; then
      printf '%s\t%s\n' "$p" "$ver"
      return 0
    fi
    echo "    ✗ $p is not an executable python 3.11/3.12 — try again." >&2
  done
}

CHOSEN=""
CHOSEN_VER=""

# (1) explicit override — no UI
if [[ -n "${PY:-}" ]]; then
  if ver="$(_check_python "$PY")"; then
    CHOSEN="$PY"; CHOSEN_VER="$ver"
    echo "[setup]   using \$PY override: $PY (python $ver)"
  else
    echo "[setup] ERROR: \$PY=$PY is not python 3.11 / 3.12 or not executable." >&2
    exit 1
  fi
fi

# (2)/(3) scan then either prompt or auto-pick
if [[ -z "$CHOSEN" ]]; then
  # Decide if we'll be interactive.
  INTERACTIVE=0
  if [[ -t 0 && -t 1 && "${NON_INTERACTIVE:-0}" != "1" ]]; then
    INTERACTIVE=1
  fi

  if [[ "$INTERACTIVE" == "1" ]]; then
    echo ""
    echo "  How do you want to point at python 3.11 / 3.12?"
    echo "    [1] auto-scan PATH + common install locations  (default)"
    echo "    [2] enter the path manually"
    printf "  choice [1/2]: "
    IFS= read -r choice
    choice="${choice:-1}"
  else
    choice=1
  fi

  if [[ "$choice" == "2" ]]; then
    line="$(_prompt_custom_path)" || { echo "[setup] cancelled." >&2; exit 1; }
    CHOSEN="${line%	*}"; CHOSEN_VER="${line#*	}"
    echo "[setup]   using $CHOSEN (python $CHOSEN_VER)"
  else
    # auto-scan
    SCAN_RESULTS="$(_scan_pythons)"
    if [[ -z "$SCAN_RESULTS" ]]; then
      echo "[setup]   scan found 0 usable python 3.11/3.12 candidates." >&2
      if [[ "$INTERACTIVE" == "1" ]]; then
        echo "[setup]   falling back to manual path entry." >&2
        line="$(_prompt_custom_path)" || { echo "[setup] cancelled." >&2; exit 1; }
        CHOSEN="${line%	*}"; CHOSEN_VER="${line#*	}"
        echo "[setup]   using $CHOSEN (python $CHOSEN_VER)"
      else
        echo "[setup] ERROR: no usable python found and not running interactively." >&2
        echo "  Re-run with PY=/abs/path/to/python3.12 or in an interactive shell." >&2
        exit 1
      fi
    else
      # Build numbered list
      mapfile -t SCAN_LINES <<< "$SCAN_RESULTS" 2>/dev/null || {
        # bash 3.2 fallback (no mapfile)
        SCAN_LINES=()
        while IFS= read -r line; do SCAN_LINES+=("$line"); done <<< "$SCAN_RESULTS"
      }

      if [[ "${#SCAN_LINES[@]}" == "1" || "$INTERACTIVE" != "1" ]]; then
        # Single candidate, or non-interactive: take the first.
        CHOSEN="${SCAN_LINES[0]%	*}"; CHOSEN_VER="${SCAN_LINES[0]#*	}"
        echo "[setup]   using $CHOSEN (python $CHOSEN_VER)"
      else
        # Multiple candidates and interactive: ask user to pick.
        echo ""
        echo "  Found ${#SCAN_LINES[@]} usable python(s):"
        i=1
        for line in "${SCAN_LINES[@]}"; do
          printf "    [%d] %s   (python %s)\n" "$i" "${line%	*}" "${line#*	}"
          i=$((i + 1))
        done
        echo "    [C] enter a custom path instead"
        printf "  choice [1]: "
        IFS= read -r pick
        pick="${pick:-1}"
        if [[ "$pick" == "C" || "$pick" == "c" ]]; then
          line="$(_prompt_custom_path)" || { echo "[setup] cancelled." >&2; exit 1; }
          CHOSEN="${line%	*}"; CHOSEN_VER="${line#*	}"
        elif [[ "$pick" =~ ^[0-9]+$ && "$pick" -ge 1 && "$pick" -le "${#SCAN_LINES[@]}" ]]; then
          line="${SCAN_LINES[$((pick - 1))]}"
          CHOSEN="${line%	*}"; CHOSEN_VER="${line#*	}"
        else
          echo "[setup] invalid choice: $pick" >&2
          exit 1
        fi
        echo "[setup]   using $CHOSEN (python $CHOSEN_VER)"
      fi
    fi
  fi
fi

PY="$CHOSEN"

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
  PIP_OPTS=()
fi
# Expand PIP_OPTS safely under `set -u`: ${arr[@]+"${arr[@]}"} is the bash 3.2
# idiom for "expand if non-empty, else nothing" — a bare ${arr[@]} trips set -u
# when the array has zero elements.
"$VPY" -m pip install --quiet --upgrade pip ${PIP_OPTS[@]+"${PIP_OPTS[@]}"} 2>/dev/null || \
  "$VPY" -m pip install --upgrade pip ${PIP_OPTS[@]+"${PIP_OPTS[@]}"}
"$VPY" -m pip install --quiet -r backend/requirements.txt ${PIP_OPTS[@]+"${PIP_OPTS[@]}"}
"$VPY" -m pip install --quiet pytest ${PIP_OPTS[@]+"${PIP_OPTS[@]}"} || true

echo "[setup] (4/7) installing project editable ..."
# pyproject.toml lives at the repo root, not under backend/.
"$VPY" -m pip install --quiet -e . --no-deps

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
