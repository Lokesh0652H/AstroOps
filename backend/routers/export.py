"""Export Project ZIP — real, sanitized source-archive download.

GET /api/export/source?scope=astraops|weltrix  → application/zip attachment
GET /api/export/scopes                         → available scopes for the dialog

Security posture (treat this endpoint as a source-disclosure boundary):
  - Scope is a closed allowlist; the export root is fixed per scope (env-overridable) and
    never taken from user input.
  - The archive is built in a pod-level temp dir OUTSIDE the project root, so the export
    can never include its own output; it is deleted after the response completes.
  - os.walk(followlinks=False) with symlinked dirs pruned and symlinked files skipped —
    nothing outside the project root can enter the archive.
  - Every file is re-validated by resolved-path containment before being added; entry
    names are relative posix paths, so no absolute server path ever leaks.
  - Real `.env` files are excluded outright; `.env.example`-style files pass through a
    redaction pass; a synthesized placeholder example is added if the tree has none.
  - Per-file and total size caps; per-file errors (missing/permission) are skipped and
    counted, never fatal.
  - Failures return generic JSON errors — no internal paths in any response body.
"""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

router = APIRouter(prefix="/export", tags=["export"])

logger = logging.getLogger(__name__)

SCOPES: dict[str, dict[str, str]] = {
    "astraops": {
        "root_env": "EXPORT_ROOT_ASTRAOPS",
        "default_root": "/app",
        "folder": "AstraOps-AI",
        "label": "AstraOps AI — running project source",
    },
    "weltrix": {
        "root_env": "EXPORT_ROOT_WELTRIX",
        "default_root": "/app/weltrix-source",
        "folder": "Weltrix-AI",
        "label": "Weltrix AI — reference repository (github.com/Samy-in/Weltrix-AI)",
    },
}

# Directories never exported, wherever they appear under the root.
EXCLUDED_DIRS = {
    "node_modules", ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".emergent", ".next", ".turbo", ".nuxt", "dist",
    "build", "out", "coverage", "htmlcov", ".idea", ".vscode", ".gradle", ".terraform",
    ".screenshots", "test_reports", "artifacts", "recordings", "memory",
    "weltrix-source",  # the nested reference clone must not nest inside the astraops scope
}
EXCLUDED_DIR_SUFFIXES = (".egg-info",)

# Files never exported by exact name.
EXCLUDED_FILE_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development", ".env.test",
    ".DS_Store", ".coverage", "coverage.xml", "design_guidelines.json", ".gitignore.bak",
}

# Files never exported by suffix (secrets, caches, logs, archives, large binaries).
EXCLUDED_SUFFIXES = (
    ".pyc", ".pyo", ".pyd", ".log", ".swp", ".swo", ".sqlite", ".sqlite3", ".db",
    ".pem", ".key", ".p12", ".pfx", ".cer", ".crt", ".jks", ".jar", ".whl",
    ".zip", ".tar", ".tar.gz", ".tgz", ".gz", ".bz2", ".7z", ".rar",
)

# Text-file redaction: any KEY/SECRET/TOKEN/PASSWORD/CREDENTIAL value is replaced.
_SECRET_KEY_RE = re.compile(
    r"(?im)^(\s*(?:export\s+)?[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|PRIVATE)[A-Z0-9_]*\s*[=:]\s*)(.*)$"
)
_REDACTED = r"\1REDACTED-BY-EXPORT-POLICY"

MAX_FILE_BYTES = 4 * 1024 * 1024          # 4 MB per file
MAX_TOTAL_BYTES = 96 * 1024 * 1024        # 96 MB per archive
CHUNK = 256 * 1024

ENV_EXAMPLE_FALLBACK = (
    "# Placeholder environment configuration — copy to .env and fill in real values.\n"
    "# NEVER commit a real .env; the export policy excludes it.\n"
    'MONGO_URL="mongodb://localhost:27017"\n'
    'DB_NAME="app"\n'
    'CORS_ORIGINS="*"\n'
)

EXCLUSION_POLICY_DOC = {
    "excluded_directories": sorted(EXCLUDED_DIRS),
    "excluded_directory_suffixes": list(EXCLUDED_DIR_SUFFIXES),
    "excluded_file_names": sorted(EXCLUDED_FILE_NAMES),
    "excluded_file_suffixes": list(EXCLUDED_SUFFIXES),
    "env_handling": (
        "Real .env files are excluded. Files named *.env.example are included after a "
        "redaction pass that replaces any KEY/SECRET/TOKEN/PASSWORD/CREDENTIAL value with "
        "a placeholder. If the tree contains no .env.example, a placeholder one is synthesized."
    ),
    "symlinks": "Symlinks are never followed; a symlinked file or directory is skipped entirely.",
    "max_file_bytes": MAX_FILE_BYTES,
    "max_total_bytes": MAX_TOTAL_BYTES,
}


class ExportTooLarge(Exception):
    pass


def _resolve_root(scope: str) -> Path:
    spec = SCOPES[scope]
    root = Path(os.environ.get(spec["root_env"], spec["default_root"])).resolve()
    if not root.is_dir():
        # Deliberately generic: never echo the internal path back to the client.
        raise HTTPException(status_code=404, detail=f"export source for scope '{scope}' is not available in this deployment")
    return root


def _is_env_example(name: str) -> bool:
    # .env.example-style files are included, but pass through the redaction pass.
    return name.endswith(".env.example")


def _redact_env_text(text: str) -> str:
    return _SECRET_KEY_RE.sub(_REDACTED, text)


def _build_zip(root: Path, dest: Path, spec: dict[str, str]) -> dict[str, Any]:
    """Walk the tree and write the archive. Returns stats for the manifest."""
    root_real = str(root)
    now = datetime.now(timezone.utc)
    stats: dict[str, Any] = {
        "file_count": 0,
        "total_bytes": 0,
        "skipped_sensitive": 0,
        "skipped_size": 0,
        "skipped_errors": 0,
        "skipped_symlink": 0,
        "env_examples_redacted": 0,
        "synthesized_env_example": False,
    }
    included: list[str] = []

    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # Prune excluded + symlinked directories before descending (top-down walk).
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in EXCLUDED_DIRS
                and not d.endswith(EXCLUDED_DIR_SUFFIXES)
                and not os.path.islink(os.path.join(dirpath, d))
            )
            for name in sorted(filenames):
                full = Path(dirpath) / name
                try:
                    if name in EXCLUDED_FILE_NAMES:
                        stats["skipped_sensitive"] += 1
                        continue
                    if name.endswith(EXCLUDED_SUFFIXES):
                        stats["skipped_sensitive"] += 1
                        continue
                    if full.is_symlink():
                        stats["skipped_symlink"] += 1
                        continue
                    # Containment re-check on the resolved path — belt and braces.
                    resolved = str(full.resolve())
                    if not resolved.startswith(root_real + os.sep):
                        stats["skipped_symlink"] += 1
                        continue
                    size = full.stat().st_size
                    if size > MAX_FILE_BYTES:
                        stats["skipped_size"] += 1
                        continue
                    if stats["total_bytes"] + size > MAX_TOTAL_BYTES:
                        raise ExportTooLarge()

                    rel = full.relative_to(root).as_posix()
                    arcname = f"{spec['folder']}/{rel}"

                    if _is_env_example(name):
                        text = full.read_text(encoding="utf-8", errors="replace")
                        zf.writestr(arcname, _redact_env_text(text))
                        stats["env_examples_redacted"] += 1
                    else:
                        zf.write(full, arcname)

                    stats["file_count"] += 1
                    stats["total_bytes"] += size
                    included.append(rel)
                except ExportTooLarge:
                    raise
                except (OSError, ValueError):
                    stats["skipped_errors"] += 1

        if not any(rel.endswith(".env.example") for rel in included):
            zf.writestr(f"{spec['folder']}/.env.example", ENV_EXAMPLE_FALLBACK)
            stats["synthesized_env_example"] = True

        manifest = {
            "product": "AstraOps AI — Export Project ZIP",
            "scope": spec["label"],
            "generated_at": now.isoformat(),
            "root_name": root.name,
            "stats": stats,
            "exclusion_policy": EXCLUSION_POLICY_DOC,
            "notes": (
                "This archive was generated by the running AstraOps AI export endpoint. "
                "Paths are relative to the project root; no absolute server paths are included."
            ),
        }
        zf.writestr(f"{spec['folder']}/EXPORT_MANIFEST.json", json.dumps(manifest, indent=2))
    return stats


def _iter_file(path: Path, chunk_size: int = CHUNK):
    with path.open("rb") as fh:
        while chunk := fh.read(chunk_size):
            yield chunk


@router.get("/scopes")
async def list_scopes() -> dict[str, Any]:
    scopes = []
    for key, spec in SCOPES.items():
        available = Path(os.environ.get(spec["root_env"], spec["default_root"])).is_dir()
        scopes.append({"scope": key, "label": spec["label"], "available": available,
                       "filename": f"{spec['folder']}-Source.zip"})
    return {"scopes": scopes, "policy": EXCLUSION_POLICY_DOC}


@router.get("/source")
async def export_source(scope: Literal["astraops", "weltrix"] = "astraops") -> StreamingResponse:
    spec = SCOPES[scope]
    root = _resolve_root(scope)

    tmpdir = tempfile.mkdtemp(prefix="astraops-export-")  # pod-level temp, OUTSIDE the project root
    dest = Path(tmpdir) / f"{spec['folder']}-Source.zip"
    try:
        try:
            await asyncio.to_thread(_build_zip, root, dest, spec)
        except ExportTooLarge:
            raise HTTPException(status_code=413, detail="source tree exceeds the maximum archive size for export")
        except Exception:
            logger.exception("export failed for scope %s", scope)
            raise HTTPException(status_code=500, detail="export failed while generating the archive")
    except HTTPException:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise

    filename = f"{spec['folder']}-Source.zip"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }
    # Cleanup runs after the response body is fully sent — the temp dir always goes away.
    return StreamingResponse(
        _iter_file(dest),
        media_type="application/zip",
        headers=headers,
        background=BackgroundTask(shutil.rmtree, tmpdir, True),
    )
