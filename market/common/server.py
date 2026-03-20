import os
import time
import json
import socket
import logging
import asyncio
import signal
from typing import Optional
from contextlib import asynccontextmanager

def find_free_port() -> int:
    import random
    for _ in range(100):
        port = random.randint(40000, 60000)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@asynccontextmanager
async def start_opencode_server(
    agent_id: str, 
    agent_dir: str, 
    port: int, 
    model: str, 
    provider: str, 
    traces_dir: str
):
    from market.common.process_registry import registry
    if not os.path.exists(agent_dir):
        os.makedirs(agent_dir, exist_ok=True)

    agent_home = os.path.join(agent_dir, ".home")
    os.makedirs(agent_home, exist_ok=True)

    host_root = os.getcwd()
    host_nm = os.path.join(host_root, "node_modules")
    agent_nm = os.path.join(agent_dir, "node_modules")
    if os.path.exists(host_nm) and not os.path.exists(agent_nm):
        try: os.symlink(host_nm, agent_nm)
        except FileExistsError: pass

    host_opencode_nm = os.path.join(host_root, ".opencode", "node_modules")
    agent_opencode_dir = os.path.join(agent_dir, ".opencode")
    agent_opencode_nm = os.path.join(agent_opencode_dir, "node_modules")
    if os.path.exists(host_opencode_nm):
        os.makedirs(agent_opencode_dir, exist_ok=True)
        if not os.path.exists(agent_opencode_nm):
            try: os.symlink(host_opencode_nm, agent_opencode_nm)
            except FileExistsError: pass

    env = os.environ.copy()
    if "GEMINI_API_KEY" in env and "GOOGLE_GENERATIVE_AI_API_KEY" not in env:
        env["GOOGLE_GENERATIVE_AI_API_KEY"] = env["GEMINI_API_KEY"]
    if "/.opencode/bin" in env.get("PATH", "") or os.path.exists("/.opencode/bin"):
        if "/.opencode/bin" not in env.get("PATH", ""):
            env["PATH"] = f"/.opencode/bin:{env.get('PATH', '')}"

    env["HOME"] = agent_home
    env["PORT"] = str(port)

    raw_opencode_key = env.get("OPENCODE_API_KEY")
    opencode_key = raw_opencode_key.strip("\"' \n\r\t") if raw_opencode_key else None
    if not opencode_key:
        auth_path = os.path.expanduser("~/.local/share/opencode/auth.json")
        if os.path.exists(auth_path):
            try:
                with open(auth_path, "r") as f:
                    data = json.load(f)
                    opencode_key = data.get("opencode", {}).get("key")
                    if opencode_key: opencode_key = opencode_key.strip("\"' \n\r\t")
            except Exception: pass

    if opencode_key:
        try:
            dest_auth_dir = os.path.join(agent_home, ".local", "share", "opencode")
            os.makedirs(dest_auth_dir, exist_ok=True)
            with open(os.path.join(dest_auth_dir, "auth.json"), "w") as f:
                json.dump({"opencode": {"type": "api", "key": opencode_key}}, f)
            env["OPENCODE"] = opencode_key
            env["OPENCODE_API_KEY"] = opencode_key
        except Exception as e:
            logging.warning(f"Failed to plumb OPENCODE_API_KEY to agent sandbox: {e}")

    permission_data = {"external_directory": "deny", "doom_loop": "allow", "*": "allow"}
    full_model_name = model if model.startswith(f"{provider}/") else f"{provider}/{model}"
    config_data = {
        "model": full_model_name,
        "snapshot": False,
        "agent": {"general": {"description": "General settings", "permission": permission_data}}
    }
    
    try:
        from opencode_ai.types import Config
        config_obj = Config(**config_data)
        config_json = json.dumps(config_obj.model_dump(exclude_none=True, by_alias=True))
    except ImportError:
        config_json = json.dumps(config_data)

    env["OPENCODE_PERMISSION"] = json.dumps(permission_data)
    env["OPENCODE_CONFIG_CONTENT"] = config_json
    env["DEBUG"] = "opencode:provider:*"
    env["OPENCODE_LOG"] = "debug"
    env["PYTHONUNBUFFERED"] = "1"
    
    os.makedirs(traces_dir, exist_ok=True)
    agent_log = os.path.join(traces_dir, f"{agent_id}_opencode_serve.log")
    
    with open(agent_log, "w") as f:
        # RAII Process for the server
        async with registry.spawn(
            "opencode", "serve", "--port", str(port), "--hostname=127.0.0.1",
            "--print-logs", "--log-level", "DEBUG",
            stdout=f, stderr=f, cwd=agent_dir, env=env
        ) as proc:
            # Wait for server to be healthy
            start_time = time.time()
            healthy = False
            while time.time() - start_time < 30:
                if proc.returncode is not None:
                    raise RuntimeError(f"Server for {agent_id} failed to start. See {agent_log}")
                try:
                    _, writer = await asyncio.open_connection("127.0.0.1", port)
                    writer.close()
                    await writer.wait_closed()
                    healthy = True
                    break
                except (ConnectionRefusedError, OSError):
                    await asyncio.sleep(0.5)
            
            if not healthy:
                raise RuntimeError(f"Timed out waiting for server {agent_id} at port {port}")
            
            yield proc
