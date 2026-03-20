from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from rtac_sim.paths import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    DEFAULT_RTAC_PROJECT,
    DEFAULT_SCAN_INTERVAL_MS,
    DIST_DIR,
    FIXTURE_ZIP,
    to_msys_path,
)


def default_bridge_config(
    project_path: Path = DEFAULT_RTAC_PROJECT,
    bind_host: str = DEFAULT_BRIDGE_HOST,
    bind_port: int = DEFAULT_BRIDGE_PORT,
    scan_interval_ms: int = DEFAULT_SCAN_INTERVAL_MS,
) -> dict[str, object]:
    resolved_project_path = project_path.resolve()
    return {
        "project_path": str(resolved_project_path),
        "project_path_windows": str(resolved_project_path),
        "project_path_msys": to_msys_path(resolved_project_path),
        "bind_host": bind_host,
        "bind_port": bind_port,
        "scan_interval_ms": scan_interval_ms,
    }


def build_stub_zip(
    *,
    output_zip: Path | None = None,
    project_path: Path = DEFAULT_RTAC_PROJECT,
    bind_host: str = DEFAULT_BRIDGE_HOST,
    bind_port: int = DEFAULT_BRIDGE_PORT,
    scan_interval_ms: int = DEFAULT_SCAN_INTERVAL_MS,
) -> Path:
    """Reuse the known-good fixture and inject rtac_bridge plugin config."""

    if not FIXTURE_ZIP.exists():
        raise FileNotFoundError(f"Fixture ZIP not found: {FIXTURE_ZIP}")

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    target = output_zip or DIST_DIR / "rtac_bridge_stub.zip"
    config_bytes = json.dumps(
        default_bridge_config(
            project_path=project_path,
            bind_host=bind_host,
            bind_port=bind_port,
            scan_interval_ms=scan_interval_ms,
        ),
        indent=2,
    ).encode("utf-8")

    with ZipFile(FIXTURE_ZIP, "r") as source_zip, ZipFile(target, "w", compression=ZIP_DEFLATED) as target_zip:
        names = source_zip.namelist()
        root_prefix = ""
        if names:
            first_name = names[0]
            if "/" in first_name:
                root_prefix = first_name.split("/", 1)[0] + "/"

        for info in source_zip.infolist():
            if info.is_dir():
                continue
            normalized_name = info.filename.replace("\\", "/")
            if normalized_name.startswith(f"{root_prefix}conf/") and normalized_name.endswith(".json"):
                continue
            target_zip.writestr(info, source_zip.read(info.filename))

        target_zip.writestr(f"{root_prefix}conf/rtac_bridge.json", config_bytes)

    return target
