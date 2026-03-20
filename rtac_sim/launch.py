from __future__ import annotations

import subprocess
import time
from pathlib import Path

from rtac_sim.paths import (
    DIST_DIR,
    MSYS_BASH,
    MSYS_RUNTIME_STATE_DIR,
    OPENPLC_ROOT,
    to_msys_path,
)
from rtac_sim.runtime_api import OpenPLCRuntimeClient


def source_runtime_is_running(
    *,
    openplc_root: Path = OPENPLC_ROOT,
) -> bool:
    """Return True when the source checkout owns a live runtime process."""

    command = f"""
$root = '{openplc_root.resolve()}'
$procs = Get-CimInstance Win32_Process | Where-Object {{
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.Name -eq 'bash.exe' -and $_.CommandLine -like '*openplc-runtime*' -and $_.CommandLine -like '*start_openplc.sh*')
}}
if ($procs) {{ 'true' }} else {{ 'false' }}
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().lower() == "true"


def launch_source_runtime(
    client: OpenPLCRuntimeClient,
    *,
    openplc_root: Path = OPENPLC_ROOT,
    bash_path: Path = MSYS_BASH,
    timeout_seconds: int = 45,
) -> bool:
    """Launch the source checkout via the installed MSYS2 bundle if needed."""

    if client.is_reachable():
        return True

    if not bash_path.exists():
        raise FileNotFoundError(f"MSYS2 bash.exe not found: {bash_path}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    log_path = DIST_DIR / "runtime-launch.log"
    openplc_msys = to_msys_path(openplc_root)
    launch_command = (
        f"cd '{openplc_msys}' && "
        "if [ ! -f .installed ]; then ./install.sh; fi && "
        "./start_openplc.sh"
    )

    with log_path.open("ab") as log_file:
        subprocess.Popen(  # noqa: S603
            [str(bash_path), "-lc", launch_command],
            cwd=str(openplc_root.parent),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        )

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if client.is_reachable():
            return True
        time.sleep(1)
    return False


def stop_source_runtime(
    client: OpenPLCRuntimeClient,
    *,
    openplc_root: Path = OPENPLC_ROOT,
    timeout_seconds: int = 20,
) -> bool:
    """Stop runtime processes that belong to the source checkout."""

    command = f"""
$ErrorActionPreference = 'SilentlyContinue'
$root = '{openplc_root.resolve()}'
$procs = Get-CimInstance Win32_Process | Where-Object {{
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) -or
    ($_.Name -eq 'bash.exe' -and $_.CommandLine -like '*openplc-runtime*' -and $_.CommandLine -like '*start_openplc.sh*')
}}
foreach ($proc in $procs) {{
    cmd /c "taskkill /PID $($proc.ProcessId) /T /F" | Out-Null
}}
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
    )

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not client.is_reachable():
            return True
        time.sleep(1)
    return not client.is_reachable()


def reset_runtime_state(
    *,
    runtime_state_dir: Path = MSYS_RUNTIME_STATE_DIR,
) -> None:
    """Remove persisted runtime auth and stale sockets for a clean source launch."""

    for name in (".env", "restapi.db", "log_runtime.socket", "plc_runtime.socket"):
        (runtime_state_dir / name).unlink(missing_ok=True)
