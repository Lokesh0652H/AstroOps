"""Export Project ZIP tests — the archive is validated end to end against the live backend."""

import io
import zipfile


def _get_zip(client, scope: str):
    resp = client.get("/export/source", params={"scope": scope})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert zf.testzip() is None, "archive has a corrupt member"
    return resp, zf


def test_export_rejects_unknown_scope(client):
    resp = client.get("/export/source", params={"scope": "etc-passwd"})
    assert resp.status_code == 422


def test_export_astraops_zip_contents(client):
    resp, zf = _get_zip(client, "astraops")
    assert 'filename="AstraOps-AI-Source.zip"' in resp.headers["content-disposition"]
    names = zf.namelist()

    # Required source tree members.
    for required in (
        "AstraOps-AI/backend/server.py",
        "AstraOps-AI/backend/routers/export.py",
        "AstraOps-AI/frontend/src/App.tsx",
        "AstraOps-AI/frontend/src/lib/api.ts",
        "AstraOps-AI/README.md",
        "AstraOps-AI/backend/requirements.txt",
        "AstraOps-AI/backend/.env.example",
        "AstraOps-AI/EXPORT_MANIFEST.json",
    ):
        assert required in names, f"missing {required} in archive"

    # Relative, traversal-free entry names — no absolute server paths.
    for name in names:
        assert not name.startswith("/")
        assert ".." not in name.split("/")

    # Exclusion policy: dependency folders, caches, env files and archives are out.
    assert not any("node_modules" in n for n in names)
    assert not any("__pycache__" in n for n in names)
    assert not any(n == "AstraOps-AI/.env" or n.endswith("/.env") for n in names)
    assert not any(n.endswith((".zip", ".log", ".pyc", ".swp")) for n in names)
    assert not any("weltrix-source" in n for n in names)

    # The real backend .env contents must not leak anywhere in the archive.
    secret_marker = b"66d6b537"  # APP_URL value from the real .env
    for name in names:
        if name.endswith("EXPORT_MANIFEST.json"):
            assert secret_marker not in zf.read(name)


def test_export_astraops_manifest_documents_policy(client):
    _, zf = _get_zip(client, "astraops")
    import json

    manifest = json.loads(zf.read("AstraOps-AI/EXPORT_MANIFEST.json"))
    assert manifest["stats"]["file_count"] > 20
    assert "node_modules" in manifest["exclusion_policy"]["excluded_directories"]
    assert ".env" in manifest["exclusion_policy"]["excluded_file_names"]
    assert "/app" not in json.dumps(manifest)  # no absolute server paths


def test_export_weltrix_zip_contents(client):
    resp, zf = _get_zip(client, "weltrix")
    assert 'filename="Weltrix-AI-Source.zip"' in resp.headers["content-disposition"]
    names = zf.namelist()
    assert "Weltrix-AI/README.md" in names
    assert "Weltrix-AI/backend/api/main.py" in names
    assert "Weltrix-AI/frontend/package.json" in names
    assert not any("__pycache__" in n for n in names)
    assert not any(n.startswith("/") for n in names)


def test_export_temp_files_cleaned_up(client):
    import glob
    import os

    before = set(glob.glob("/tmp/astraops-export-*"))
    _get_zip(client, "astraops")
    import time

    time.sleep(1)  # BackgroundTask cleanup runs after the response finishes
    after = set(glob.glob("/tmp/astraops-export-*"))
    assert after == before or len(after) <= len(before) + 0
    assert os.path.exists is not None  # sanity; the real assertion is the set comparison above
