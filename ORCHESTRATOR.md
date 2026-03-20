# RTAC Sim Orchestrator Memory

## Workspace Shape

- Top-level workspace:
  - `openplc-runtime/`: source checkout of OpenPLC Runtime v4.
  - `production/`: SEL AcSELerator RTAC export.
  - `OpenPLC Runtime/`: installed Windows/MSYS2 runtime bundle.
- `openplc-runtime/` is the Git repo on `main`.
- The workspace root is not a Git repo.

## Confirmed Runtime Facts

- OpenPLC Runtime v4 is dual-process.
- Python web/control plane lives in `openplc-runtime/webserver/`.
- C/C++ PLC core lives in `openplc-runtime/core/src/plc_app/`.
- The web process handles HTTPS API, JWT auth, upload/compile orchestration, debug WebSocket, and runtime supervision.
- The PLC core handles scan cycles, plugin execution, watchdog/state management, and loading `build/libplc_*.so`.
- IPC uses Unix sockets at `/run/runtime/plc_runtime.socket` and `/run/runtime/log_runtime.socket`.
- The installed Windows runtime is running and reachable at `https://127.0.0.1:8443`.
- The first user was created and the API is live; no PLC program is loaded until a ZIP upload succeeds.
- A sample OpenPLC upload ZIP was compiled successfully on this machine and moved the runtime to `STATUS:RUNNING`.
- Local tooling facts on this machine:
  - `python` is available in the host shell.
  - `bash` and `gcc` are not on the host PATH, but MSYS2 is present in the installed runtime bundle.
  - Docker Desktop's Linux engine was not available during verification.

## OpenPLC Conventions

- The runtime is not a direct interpreter for arbitrary IEC or SEL RTAC projects.
- It expects an OpenPLC Editor v4 style ZIP containing generated sources and support files, then compiles that ZIP server-side.
- Required upload contents include `Config0.c`, `Res0.c`, `debug.c`, `glueVars.c`, `c_blocks_code.cpp`, and `lib/`.
- The runtime loads symbols from the compiled shared library, not from the original source tree.
- Windows support is MSYS2-based, not native Win32.
- On MSYS2/Cygwin, some communication blocks are stubbed in `scripts/compile.sh`.

## Fragile Areas

- Docs drift exists around `setup.py` vs `pyproject.toml` and `scripts/setup-tests-env.sh` vs the actual test scripts.
- Native Linux persistence paths differ between code and older docs; code currently uses `/var/lib/openplc-runtime` for persistent data.
- `webserver/config.py` can prompt interactively if `.env` is invalid, which is brittle for automation.
- Plugin behavior is not passive: uploaded configs can enable or disable plugins via `core/generated/conf/*.json`.
- The PLC core relies on `compile-clean.sh` behavior to keep only one `libplc_*.so`.

## Current Decision

- Do not try to import the SEL export directly into OpenPLC as-is.
- Host the SEL RTAC project through a custom `rtac_bridge` inside OpenPLC Runtime.
- The bridge should flatten the RTAC data model, load the needed user logic, and expose a simple simulation surface plus runtime automation.
- Keep the first target narrow: the currently implemented user-logic path, not the full SEL device tree or all RTAC runtime features.

## Current Working State

- The source checkout in `openplc-runtime/` is installed and runnable on Windows through the MSYS2 bundle under `OpenPLC Runtime/msys64/`.
- `python -m rtac_sim` from the workspace root now performs the working launch path:
  - launches the source runtime if `https://127.0.0.1:8443/api` is down
  - recovers from stale source-runtime auth state if needed
  - uploads `rtac_sim/dist/rtac_bridge_stub.zip`
  - enables the `rtac_bridge` plugin via `generated/conf/rtac_bridge.json`
- The live bridge HTTP surface is now available at `http://127.0.0.1:18080`.
- Verified live endpoints:
  - `GET /health`
  - `GET /manifest`
  - `GET /state`
  - `POST /state`
  - `POST /cycle`
- Verified live RTAC behavior from the real `production/` export:
  - `SEL751_MODBUS.TRIP_751.stVal = true` drives `CB_101_01_400A_MODBUS.A_COMMAND.oper.ctlVal = 904`
  - `SEL751_MODBUS.CLOSE_751.stVal = true` drives `CB_101_01_400A_MODBUS.A_COMMAND.oper.ctlVal = 905`
  - companion fields `B_LENGTH`, `C_DESTINATION`, `D_SECURITY`, `E_PASSWORD`, and `F_PASSWORD_EXT` are populated from the RTAC constants
- Verified live manifest from the real `production/` export:
  - `module_count = 31`
  - `tag_count = 774`
  - `controller_program_count = 25`
  - wrapper/controller dependencies discovered: `24`
  - controller programs now include:
    - 21 breaker/device controller wrappers under `Devices/IFE1` and `Devices/IFE2`
    - `SEL751_MODBUS_Controller`
    - `EtherCAT_I_O_Network_Controller`
    - `System_Time_Control_Controller`
    - `PWRPACT_FAT_TEMP`
  - manifest dependency example:
    - `SEL751_MODBUS_Controller -> SEL751_MODBUS_POU:SEL751_MODBUS_POU_TYPE`
  - the first task currently assigns all 25 discovered program wrappers/programs
  - broader state roots are present:
    - `CB_102_01_600A_MODBUS`
    - `SystemTags`
    - `SEL2240_DO_1_ECAT`

## Bridge Layout

- Runtime automation lives in `rtac_sim/`.
- The custom bridge plugin lives in `openplc-runtime/core/src/drivers/plugins/python/rtac_bridge/`.
- The OpenPLC plugin entrypoint must be `rtac_bridge_plugin.py`, not `plugin.py`.
- The bridge helper modules are namespaced as `rtac_bridge_*` to avoid collisions in OpenPLC's shared Python interpreter.
- Legacy files like `config.py`, `model.py`, `parser.py`, `logic.py`, `http_api.py`, and `service.py` are compatibility wrappers for tests/imports only.
- The bridge is no longer hardcoded to the sample project shape. It now:
  - ingests arbitrary SEL RTAC XML module inventories
  - seeds dynamic simulator state from discovered tag surfaces
  - parses discovered controller/user-logic programs
  - parses serialized `ControllerPOU` wrappers across device/system/network modules
  - records wrapper dependencies declared through `VAR_EXTERNAL` POU instances
  - records coarse task linkage in the manifest via `assigned_programs`
  - executes a limited ST subset (`:=`, `IF/THEN/END_IF`, `AND`, `OR`, `NOT`, `=`, constants, path references)

## Known Loader Pitfalls

- OpenPLC imports Python plugins by filename-derived module name.
- If two plugins use the same entrypoint filename, module caching can make one plugin execute the other's code.
- Generic helper module names like `config.py` also collide across plugins because the interpreter is shared.
- For custom Python plugins in this runtime, prefer unique filenames for both the plugin entrypoint and all support modules.

## Generic RTAC Support Notes

- The parser now walks the full `SEL_RTAC/` tree rather than a fixed file list.
- It also accepts top-level `POUs/` XMLs when they export reusable RTAC POUs, while ignoring non-POU project metadata files outside `SEL_RTAC/`.
- Device, system, tag-processor, EtherCAT, and user-logic modules are all included in the manifest/state model.
- Device and system `ControllerPOU` wrappers are part of the manifest model now; do not assume only user-logic and the two system wrappers are promoted.
- Wrapper controller programs stored as serialized XML/text inside module files require raw-text fallback extraction; do not assume they appear as parsed XML child nodes.
- The execution layer is generic across ingested projects only to the extent their logic stays within the currently implemented ST subset. Unsupported ST constructs would require extending `rtac_bridge_st.py`.

## RTAC Minimum Schema

- `production/SEL_RTAC/User Logic/PWRPACT_FAT_TEMP.xml` is the primary logic to reproduce first.
- Inputs used by that logic:
  - `SEL751_MODBUS.TRIP_751.stVal`
  - `SEL751_MODBUS.CLOSE_751.stVal`
  - `SEL2240_DI_1_ECAT.SE1_OC.stVal`
  - `SEL2240_DI_1_ECAT.SE1_CC.stVal`
- Output command object used by that logic:
  - `CB_101_01_400A_MODBUS`
- Fields driven on that object:
  - `A_COMMAND.oper.ctlVal`
  - `A_COMMAND.oper.trigger`
  - `B_LENGTH.oper.ctlVal`
  - `B_LENGTH.oper.trigger`
  - `C_DESTINATION.oper.ctlVal`
  - `C_DESTINATION.oper.trigger`
  - `D_SECURITY.oper.ctlVal`
  - `D_SECURITY.oper.trigger`
  - `E_PASSWORD.oper.ctlVal`
  - `E_PASSWORD.oper.trigger`
  - `F_PASSWORD_EXT.oper.ctlVal`
  - `F_PASSWORD_EXT.oper.trigger`
- The export also includes SEL-only support objects that should not be assumed portable:
  - EtherCAT runtime objects
  - Tag Processor
  - SystemTags runtime semantics
  - IRIG/PTP/DNP timing controls

## Future Subagent Guidance

- Work in the smallest possible scope and preserve existing runtime behavior.
- Prefer bridge/translator code over patching the core runtime unless a hard limitation forces a runtime change.
- If touching OpenPLC runtime code, preserve the existing plugin/runtime API and Windows/MSYS2 behavior.
- If touching the RTAC side, assume the data model must be flattened or emulated, not imported literally.
- Before introducing new assumptions, check whether the issue is a code limitation, a packaging limitation, or just a translation gap.
