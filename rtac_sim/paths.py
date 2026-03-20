from __future__ import annotations

from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
OPENPLC_ROOT = WORKSPACE_ROOT / "openplc-runtime"
INSTALLED_RUNTIME_ROOT = WORKSPACE_ROOT / "OpenPLC Runtime"
MSYS_BASH = INSTALLED_RUNTIME_ROOT / "msys64" / "usr" / "bin" / "bash.exe"
MSYS_RUNTIME_STATE_DIR = INSTALLED_RUNTIME_ROOT / "msys64" / "run" / "runtime"
START_BAT = INSTALLED_RUNTIME_ROOT / "StartOpenPLC.bat"
FIXTURE_ZIP = (
    OPENPLC_ROOT
    / "tests"
    / "pytest"
    / "plugins"
    / "opcua"
    / "test_project"
    / "uploaded_project (2).zip"
)
DEFAULT_RTAC_PROJECT = WORKSPACE_ROOT / "production"
DIST_DIR = WORKSPACE_ROOT / "rtac_sim" / "dist"
DEFAULT_RUNTIME_URL = "https://127.0.0.1:8443/api"
DEFAULT_USERNAME = "codex"
DEFAULT_PASSWORD = "codexpass123"
DEFAULT_ROLE = "admin"
DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 18080
DEFAULT_SCAN_INTERVAL_MS = 100


def to_msys_path(path: Path) -> str:
    normalized = path.resolve().as_posix()
    drive, remainder = normalized.split(":/", 1)
    return f"/{drive.lower()}/{remainder}"
