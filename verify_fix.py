import sys
import os
import json
import subprocess
import time
import signal

def run_verification():
    workspace_root = os.getcwd()
    opencode_dir = os.path.join(workspace_root, ".opencode")
    
    # Use the same prompt as requested
    prompt = "run a tournament with 3 agents for 5 rounds to implement a function that returns the nth fibonacci number. Set log level to INFO."
    
    cmd = [
        "python3", "-m", "market.cli", 
        "run", 
        "--prompt", "implement nth fibonacci", # Simplified internal prompt
        "--agents", "3", 
        "--rounds", "5", 
        "--json-logs"
    ]
    
    print(f"Starting tournament...")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env={**os.environ, "PYTHONPATH": workspace_root}
    )

    agent_info = None
    start_time = time.time()
    
    try:
        while time.time() - start_time < 120:
            line = process.stdout.readline()
            if not line:
                break
            
            try:
                event = json.loads(line)
                if event.get("type") == "agent_init" and event.get("agent_id") == "agent_0":
                    agent_info = event
                    print(f"Found Agent 0: {agent_info['api_url']} (Session: {agent_info['session_id']})")
                    break
            except json.JSONDecodeError:
                pass
        
        if not agent_info:
            print("Failed to find Agent 0 info in time.")
            return

        # Now try to ATTACH using the binary directly as TerminalManager does
        # We'll run it for 10 seconds and check if we get TUI data
        attach_cmd = [
            "/home/codespace/.opencode/bin/opencode", 
            "attach", agent_info["api_url"], 
            "-s", agent_info["session_id"],
            "--print-logs"
        ]
        
        print(f"Attempting to attach to agent_0...")
        # We use a PTY-like environment for the check
        attach_proc = subprocess.Popen(
            attach_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        output = ""
        attach_start = time.time()
        while time.time() - attach_start < 20:
            # Check if process is still alive
            if attach_proc.poll() is not None:
                print(f"Attach process exited early with code {attach_proc.returncode}")
                break
                
            line = attach_proc.stdout.readline()
            if line:
                output += line
                if "Fibonacci" in line or "fibonacci" in line:
                    print("SUCCESS: Received TUI data from agent session!")
                    print(f"TUI Sample: {line.strip()[:100]}")
                    attach_proc.terminate()
                    return True
            time.sleep(0.1)
            
        print("Failed to verify TUI data within timeout.")
        print(f"Final output sample: {output[-500:]}")
        
    finally:
        process.terminate()
        try: attach_proc.terminate()
        except: pass

if __name__ == "__main__":
    if run_verification():
        sys.exit(0)
    else:
        sys.exit(1)
