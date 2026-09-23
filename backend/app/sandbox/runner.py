"""
Runs a PR's code snapshot inside isolated, resource-limited Docker
containers: lints with ruff, tests with pytest, and captures the output.

Network isolation: dependency installation legitimately needs network
access (to reach PyPI), but the actual test/lint execution does not and
is a bigger risk surface (untrusted code running with active network).
So this runs in two stages:
  1. Install stage — network enabled, installs requirements.txt into a
     throwaway Docker volume.
  2. Test stage — network fully disabled, mounts that volume read-only
     and runs ruff + pytest against it.

This module is synchronous (the Docker SDK is blocking) — callers from
async code should wrap calls in `asyncio.to_thread(...)`.
"""
import logging
import os
import time
import uuid
from pathlib import Path

import docker
from docker.errors import DockerException, ImageNotFound

logger = logging.getLogger("devagent.sandbox")

IMAGE_TAG = "devagent-sandbox:latest"
DOCKERFILE_DIR = str(Path(__file__).resolve().parents[2] / "sandbox")

INSTALL_SCRIPT = """
set -o pipefail
echo "## DEPENDENCIES ##"
if [ -f requirements.txt ]; then
    pip install --quiet --no-cache-dir --target=/deps -r requirements.txt \
        || echo "(dependency install failed, continuing without them)"
else
    echo "(no requirements.txt found, skipping)"
fi
"""

TEST_SCRIPT = """
set -o pipefail
export RUFF_CACHE_DIR=/tmp/.ruff_cache
export PYTHONPATH=/deps
mkdir -p /tmp/.pytest_cache

echo "## LINT (ruff) ##"
ruff check . || true

echo "## TESTS (pytest) ##"
pytest -q --maxfail=25 -p no:cacheprovider || true
"""


def get_client() -> docker.DockerClient:
    try:
        return docker.from_env()
    except DockerException as e:
        raise RuntimeError(
            "Could not reach Docker. Is Docker Desktop running?"
        ) from e


def ensure_image_built(force: bool = False) -> None:
    """Build the sandbox image if it doesn't exist yet (or force rebuild)."""
    client = get_client()

    if not force:
        try:
            client.images.get(IMAGE_TAG)
            return  # already built
        except ImageNotFound:
            pass

    logger.info("Building sandbox image %s from %s", IMAGE_TAG, DOCKERFILE_DIR)
    client.images.build(path=DOCKERFILE_DIR, tag=IMAGE_TAG, rm=True)


def _run_container(client, *, command: str, local_dir: str, deps_volume: str,
                    deps_mode: str, network_disabled: bool, run_as_root: bool,
                    timeout: int) -> dict:
    """Run one stage (install or test) and return {exit_code, logs, timed_out}."""
    volumes = {
        os.path.abspath(local_dir): {"bind": "/workspace", "mode": "ro"},
        deps_volume: {"bind": "/deps", "mode": deps_mode},
    }
    kwargs = dict(
        image=IMAGE_TAG,
        command=["sh", "-c", command],
        volumes=volumes,
        working_dir="/workspace",
        mem_limit="512m",
        nano_cpus=1_000_000_000,   # 1 CPU
        pids_limit=256,
        network_disabled=network_disabled,
        detach=True,
    )
    if run_as_root:
        kwargs["user"] = "root"  # needed to write into the fresh /deps volume

    container = client.containers.run(**kwargs)

    timed_out = False
    try:
        result = container.wait(timeout=timeout)
        exit_code = result.get("StatusCode", -1)
    except Exception:
        logger.warning("Sandbox stage exceeded %ss timeout, killing container", timeout)
        timed_out = True
        exit_code = -1
        try:
            container.kill()
        except DockerException:
            pass

    try:
        logs = container.logs().decode(errors="replace")
    except DockerException:
        logs = "(could not retrieve container logs)"

    try:
        container.remove(force=True)
    except DockerException:
        pass

    return {"exit_code": exit_code, "logs": logs, "timed_out": timed_out}


def run_checks(local_dir: str, timeout: int = 90) -> dict:
    """
    Run lint + tests against the code in `local_dir`. Returns:
      {"exit_code", "logs", "timed_out", "duration_seconds"}
    """
    client = get_client()
    ensure_image_built()

    start = time.monotonic()
    volume_name = f"devagent-deps-{uuid.uuid4().hex[:12]}"
    client.volumes.create(name=volume_name)

    try:
        has_requirements = os.path.isfile(os.path.join(local_dir, "requirements.txt"))

        install_logs = ""
        if has_requirements:
            install_result = _run_container(
                client, command=INSTALL_SCRIPT, local_dir=local_dir,
                deps_volume=volume_name, deps_mode="rw",
                network_disabled=False, run_as_root=True, timeout=timeout,
            )
            install_logs = install_result["logs"]

        test_result = _run_container(
            client, command=TEST_SCRIPT, local_dir=local_dir,
            deps_volume=volume_name, deps_mode="ro",
            network_disabled=True, run_as_root=False, timeout=timeout,
        )
    finally:
        try:
            client.volumes.get(volume_name).remove(force=True)
        except DockerException:
            pass

    duration = round(time.monotonic() - start, 2)
    combined_logs = (f"{install_logs}\n" if install_logs else "") + test_result["logs"]

    if test_result["timed_out"]:
        combined_logs += "\n\n[sandbox] Execution timed out and was terminated."

    return {
        "exit_code": test_result["exit_code"],
        "logs": combined_logs,
        "timed_out": test_result["timed_out"],
        "duration_seconds": duration,
    }
