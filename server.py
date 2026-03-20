import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from rtac_sim.launch import stop_source_runtime, source_runtime_is_running
from rtac_sim.runtime_api import OpenPLCRuntimeClient
from rtac_sim.paths import DEFAULT_RUNTIME_URL

app = FastAPI(title="RTAC Sim Frontend API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BRIDGE_URL = "http://127.0.0.1:18080"
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

@app.get("/api/status")
def get_status():
    """Get the overall status of the simulator and bridge."""
    is_running = source_runtime_is_running()
    bridge_ok = False
    cycle_count = 0
    
    if is_running:
        try:
            resp = requests.get(f"{BRIDGE_URL}/health", timeout=1.0)
            if resp.status_code == 200:
                bridge_ok = True
                cycle_count = resp.json().get("cycle_count", 0)
        except requests.RequestException:
            pass
            
    return {
        "runtime_running": is_running,
        "bridge_ok": bridge_ok,
        "cycle_count": cycle_count
    }

@app.post("/api/start")
async def start_simulation(file: UploadFile = File(None)):
    """Start the simulation, optionally uploading a new RTAC project."""
    project_path = None
    if file:
        project_path = UPLOADS_DIR / file.filename
        with open(project_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    cmd = ["python", "-m", "rtac_sim"]
    if project_path:
        cmd.extend(["--project-path", str(project_path)])
        
    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
        return {"message": "Simulation starting", "project": file.filename if file else "default"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stop")
def stop_simulation():
    """Stop the OpenPLC runtime."""
    client = OpenPLCRuntimeClient(DEFAULT_RUNTIME_URL)
    stop_source_runtime(client)
    return {"message": "Simulation stopped"}

@app.get("/api/bridge/state")
def get_bridge_state():
    try:
        resp = requests.get(f"{BRIDGE_URL}/state", timeout=2.0)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Bridge not reachable: {e}")

@app.post("/api/bridge/state")
def update_bridge_state(payload: Dict[str, Any]):
    try:
        resp = requests.post(f"{BRIDGE_URL}/state", json=payload, timeout=2.0)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Bridge not reachable: {e}")

@app.post("/api/bridge/cycle")
def trigger_bridge_cycle():
    try:
        resp = requests.post(f"{BRIDGE_URL}/cycle", timeout=2.0)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except requests.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Bridge not reachable: {e}")

FRONTEND_DIST = Path("frontend/dist")
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
