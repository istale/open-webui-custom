# Running this repo on the offline machine

> **Goal**: get `replay_cli` (and its 9 subcommands) running on a machine that
> has the real ledger data but limited / no internet, then fill in
> `docs/offline-verification-checklist.md`.

There are **two paths**. Pick based on what the offline machine has:

| Path | Use when | What you do |
|---|---|---|
| **A. Updating an existing install** | Repo already cloned + venv already set up on the offline machine (Open WebUI has been running there) | `git pull` (or transfer a fresh bundle), then `scripts/offline-setup.sh` |
| **B. Fresh install** | Nothing on the offline machine yet | Run `scripts/offline-prep.sh` on an **online** machine, transfer one tarball, run `scripts/offline-setup.sh` on the offline machine |

Both end with the same verification step.

---

## Path A — updating an existing install

If the offline machine already has the repo and a working venv (which is the
case if Open WebUI is generating data there), this is the cheap path:

```bash
# On your laptop (online):
cd /Users/istale/Documents/open-webui-based-project
./scripts/offline-prep.sh
#   -> writes  dist/offline-bundle-YYYYMMDD-vertical-data-analysis.tar.gz

# Transfer that single .tar.gz to the offline machine (USB / scp / whatever)

# On the offline machine:
tar -xzf offline-bundle-*.tar.gz -C /tmp/owui-update
cd /path/to/existing/open-webui-based-project
git fetch /tmp/owui-update/repo.bundle vertical/data-analysis
git checkout vertical/data-analysis     # <-- the corrected command you asked about
git merge FETCH_HEAD                    # (or `git reset --hard FETCH_HEAD` if you don't care about offline-side changes)

./scripts/offline-setup.sh              # idempotent — just verifies and runs smoke tests
```

`offline-setup.sh` is **idempotent**: re-run it any time to update deps or
verify. It will skip steps that are already done.

---

## Path B — fresh install (truly air-gapped)

### Step 1 — on the ONLINE machine, build a transferable bundle

```bash
cd /Users/istale/Documents/open-webui-based-project
./scripts/offline-prep.sh
```

This produces `dist/offline-bundle-YYYYMMDD-vertical-data-analysis.tar.gz`,
which contains:

- `repo.bundle` — the entire git repo with history (smaller than zipping `.git/`)
- `vendor/` — every pip wheel `backend/requirements.txt` needs
- `scripts/offline-setup.sh` + the docs
- `PYTHON_VERSION` — the Python version used to download wheels (match this on the offline side)

> **Match Python version**: if `PYTHON_VERSION` says `3.12`, the offline
> machine needs Python 3.12. If it has 3.11, re-run `offline-prep.sh` with
> `PY=python3.11 ./scripts/offline-prep.sh`.

### Step 2 — transfer the tarball

Use whatever you can: USB stick, internal share, `scp` to a jump host, etc.
Just one file moves. Nothing else needed.

### Step 3 — on the OFFLINE machine, extract + run the wizard

```bash
mkdir owui-offline && cd owui-offline
tar -xzf /path/to/offline-bundle-*.tar.gz

# Clone from the bundle (creates a real working tree):
git clone repo.bundle repo
cd repo
git checkout vertical/data-analysis        # branch from the bundle

# Run the wizard — it auto-finds the vendor/ dir one level up:
./scripts/offline-setup.sh
```

The wizard does:

1. Picks Python 3.12 (or 3.11 fallback)
2. Creates `.venv/` in the repo
3. Installs deps from `../vendor/` (no internet)
4. Installs the project editable
5. Seeds `.env` if missing
6. Runs `pytest tests/data_analysis/` as smoke test
7. Prints the next commands

When it ends with `✅ ready` and the test summary shows `XX passed`, you're set.

---

## After setup — run the verification checklist

```bash
source .venv/bin/activate
cd backend && set -a && . ../.env && set +a && export PYTHONPATH=.
CLI="python -m open_webui.utils.data_analysis.replay_cli"

# Stage 1 — system health
$CLI --since-days 30 report
$CLI --since-days 30 regression

# Stage 2 — user signals (the new layer)
$CLI --since-days 30 intents --top 20
$CLI --since-days 30 satisfaction
$CLI --since-days 30 fit

# Optional — needs MINIMAX_* in .env + network to the LLM endpoint
$CLI --since-days 30 eval
```

Then open `docs/offline-verification-checklist.md` and fill in the right-hand
column. Bring that filled file back; that's all the info needed to plan Stage
3 prompt changes — no raw data has to leave the offline machine.

---

## Troubleshooting

**"need python 3.11 or 3.12 — none found"** — Install via `pyenv`, `conda`,
your package manager, or a system installer; rerun the wizard.

**"Could not find a version that satisfies the requirement"** during pip
install — means the wheel for your Python version isn't in `vendor/`.
Re-prep with matching Python: `PY=python3.11 ./scripts/offline-prep.sh`.

**Smoke test fails on `ModuleNotFoundError: aiocache`** — you're using a
different venv than the one the wizard created. Run:
`source .venv/bin/activate` then re-run the test.

**`replay_cli` outputs `cases: 0` for eval** — known: needs both
`prompt.submitted` (frontend) and `model.request_prepared` (backend) on the
same chat. See `implementation-notes.md` D17 + the orphan-pair fix in commit
`3053f071a` — pulling the latest already includes it.
