from __future__ import annotations

import argparse
import json
from pathlib import Path

from rtac_sim.launch import (
    launch_source_runtime,
    reset_runtime_state,
    source_runtime_is_running,
    stop_source_runtime,
)
from rtac_sim.paths import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    DEFAULT_PASSWORD,
    DEFAULT_ROLE,
    DEFAULT_RTAC_PROJECT,
    DEFAULT_RUNTIME_URL,
    DEFAULT_SCAN_INTERVAL_MS,
    DEFAULT_USERNAME,
)
from rtac_sim.runtime_api import OpenPLCRuntimeClient, RuntimeApiError
from rtac_sim.stub_bundle import build_stub_zip


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch OpenPLC Runtime and upload a stub project that enables rtac_bridge.",
    )
    parser.add_argument("--runtime-url", default=DEFAULT_RUNTIME_URL)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument("--project-path", type=Path, default=DEFAULT_RTAC_PROJECT)
    parser.add_argument("--bind-host", default=DEFAULT_BRIDGE_HOST)
    parser.add_argument("--bind-port", type=int, default=DEFAULT_BRIDGE_PORT)
    parser.add_argument("--scan-interval-ms", type=int, default=DEFAULT_SCAN_INTERVAL_MS)
    parser.add_argument("--output-zip", type=Path)
    parser.add_argument("--skip-launch", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    zip_path = build_stub_zip(
        output_zip=args.output_zip,
        project_path=args.project_path,
        bind_host=args.bind_host,
        bind_port=args.bind_port,
        scan_interval_ms=args.scan_interval_ms,
    )
    print(f"[INFO] Stub ZIP ready: {zip_path}")
    print(
        "[INFO] rtac_bridge endpoint target: "
        f"http://{args.bind_host}:{args.bind_port}"
    )

    client = OpenPLCRuntimeClient(args.runtime_url)
    launched_runtime = False
    if not client.is_reachable():
        if args.skip_launch:
            print("[ERROR] Runtime API is not reachable and launch was skipped.")
            return 1
        print("[INFO] Runtime API not reachable. Launching source checkout via MSYS2...")
        if not launch_source_runtime(client):
            print("[ERROR] Failed to launch the source runtime checkout.")
            return 1
        launched_runtime = True
        print("[INFO] Runtime API is reachable.")

    try:
        client.ensure_user(args.username, args.password, role=args.role)
        client.login(args.username, args.password)
    except RuntimeApiError as exc:
        if not launched_runtime and not source_runtime_is_running():
            print(f"[ERROR] Runtime authentication failed: {exc}")
            return 1

        print(
            "[WARN] Source runtime is reachable with an existing auth store. "
            "Resetting runtime state and retrying..."
        )
        stop_source_runtime(client)
        reset_runtime_state()
        if not launch_source_runtime(client):
            print("[ERROR] Failed to relaunch the source runtime after auth reset.")
            return 1

        try:
            client.ensure_user(args.username, args.password, role=args.role)
            client.login(args.username, args.password)
        except RuntimeApiError as retry_exc:
            print(f"[ERROR] Runtime authentication failed after reset: {retry_exc}")
            return 1

    if args.skip_upload:
        print("[INFO] Upload skipped by request.")
        return 0

    try:
        upload_response = client.upload_zip(zip_path)
        print(f"[INFO] Upload response: {json.dumps(upload_response, sort_keys=True)}")
        compilation = client.wait_for_compilation(timeout_seconds=args.timeout_seconds)
        print(f"[INFO] Compilation status: {json.dumps(compilation, sort_keys=True)}")
        status = client.wait_for_runtime_status(
            "STATUS:RUNNING",
            timeout_seconds=max(30, min(args.timeout_seconds, 60)),
        )
        print(f"[INFO] Runtime status: {json.dumps(status, sort_keys=True)}")
    except RuntimeApiError as exc:
        print(f"[ERROR] Runtime interaction failed: {exc}")
        return 1

    if compilation["status"] != "SUCCESS":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
