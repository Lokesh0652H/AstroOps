# AstraOps AI — Setup & Operations

## Stack

- **Backend:** FastAPI + motor (async MongoDB) + Pydantic v2, scikit-learn ensemble
- **Frontend:** Vite + React 19 + TypeScript (strict) + Tailwind v4 + shadcn/ui (base-nova) + Recharts
- **Data:** MongoDB (`app` database), engine loop ticks every 5 seconds

## Run

```bash
# 1. Configure (never commit real secrets)
cp backend/.env.example backend/.env

# 2. Backend deps + seed + serve
cd backend && pip install -r requirements.txt
python seed.py                       # fleet registry + 10 min baseline telemetry (idempotent)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 3. Frontend
cd frontend && yarn install && yarn dev    # http://localhost:3000 (/api proxies to :8001)
```

## Tests

```bash
cd backend && pytest                 # includes export archive validation + full AIOps loop
```

The full-loop test drives a real incident end to end (~3-4 min): inject -> detect ->
recommend -> execute -> verify recovery. The export tests download the ZIP and assert
contents, exclusions, and sanitization.

## Export Project ZIP

- Endpoint: `GET /api/export/source?scope=astraops|weltrix`
- Frontend: header button -> scope dialog -> binary download via `apiDownload`
- Filename: `AstraOps-AI-Source.zip` / `Weltrix-AI-Source.zip`
- Every archive carries `EXPORT_MANIFEST.json` documenting stats + the exclusion policy.

### Inclusion

Backend source, frontend source, shared libs, assets, tests, docs, dependency manifests
and lock files, Docker/Prometheus config (reference scope), README, `.env.example` files.

### Exclusion policy (enforced in `backend/routers/export.py`)

- Dirs: `node_modules`, `.git`, `.venv`/`venv`, `__pycache__`, `.pytest_cache`, `dist`,
  `build`, coverage caches, IDE dirs, the nested `weltrix-source` clone, internal agent state
- Files: real `.env*` files, `.pem/.key/.p12/...` secret material, `.pyc/.log/.swp`,
  archives (`.zip/.tar/...`), SQLite/db dumps
- `.env.example`-style files pass a redaction pass (KEY/SECRET/TOKEN/PASSWORD/CREDENTIAL
  values become placeholders); if a scope has none, a placeholder example is synthesized
- Symlinks are never followed; per-file cap 4 MB, total cap 96 MB
- The archive is built in a pod temp dir outside the project root and deleted after the
  response completes — the export can never include its own output

### Limitations

- The export scopes are fixed at deploy time (env: `EXPORT_ROOT_ASTRAOPS`,
  `EXPORT_ROOT_WELTRIX`); the endpoint intentionally accepts no arbitrary paths.
- No authentication is wired in this demo build; if you expose the app beyond localhost,
  front the export endpoint with your own auth layer before sharing it.
- The export reflects the deployment's source tree at request time — generated files
  (build output, downloaded dependencies) are excluded by policy, not backed up.

## Manual export check

```bash
curl -sf "http://localhost:8001/api/export/source?scope=astraops" -o /tmp/export.zip
python - <<'PY'
import zipfile
zf = zipfile.ZipFile("/tmp/export.zip")
print(len(zf.namelist()), "files; corrupt member:", zf.testzip())
print("has manifest:", "AstraOps-AI/EXPORT_MANIFEST.json" in zf.namelist())
PY
```
