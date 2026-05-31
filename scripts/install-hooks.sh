#!/usr/bin/env bash
# Install the project's git hooks into .git/hooks/.
# Re-run after a fresh clone (git hooks are not tracked by git itself).
set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_SRC="$REPO_ROOT/scripts/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"
for hook in pre-push; do
  cp "$HOOKS_SRC/$hook" "$HOOKS_DST/$hook"
  chmod +x "$HOOKS_DST/$hook"
  echo "installed: $HOOKS_DST/$hook"
done
