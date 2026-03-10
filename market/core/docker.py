import asyncio
import logging

def get_image_name(instance_id: str) -> str:
    """
    Resolves the official Epoch AI GHCR image name for a given SWE-bench instance ID.
    Strictly uses x86_64 architecture for now to ensure compatibility with standard runs.
    """
    return f"ghcr.io/epoch-research/swe-bench.eval.x86_64.{instance_id}:latest"

async def pull_image(image_name: str) -> None:
    """
    Pulls a Docker image if it's not already present locally.
    """
    logging.info(f"Pulling Docker image {image_name}...")
    proc = await asyncio.create_subprocess_exec(
        "docker", "pull", image_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to pull image {image_name}:\n{stderr.decode()}")
    logging.info(f"Successfully pulled {image_name}")

async def start_container(image_name: str, workspace_host_path: str, licode_host_path: str = None) -> str:
    """
    Starts a background Docker container tailored for SWE-bench execution.
    Returns the running container ID.
    """
    args = [
        "docker", "run", "-d",
        "--init",
        "--name", f"licode-eval-{image_name.split('.')[-1].replace(':', '-')}",
        "-v", f"{workspace_host_path}:/testbed"
    ]

    if licode_host_path:
        args.extend(["-v", f"{licode_host_path}:/licode"])
        
    # We want a sleep command to keep it alive indefinitely until we kill it
    args.extend([image_name, "tail", "-f", "/dev/null"])
    
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to start container:\n{stderr.decode()}")
        
    return stdout.decode().strip()

async def stop_container(container_id: str) -> None:
    """
    Stops and removes a running Docker container forcefully.
    """
    proc = await asyncio.create_subprocess_exec(
        "docker", "rm", "-f", container_id,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        logging.warning(f"Failed to cleanly stop container {container_id}: {stderr.decode()}")
