"""Execução comum das ferramentas em uma microVM descartável."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from microsandbox import (
    Network,
    PullPolicy,
    Sandbox,
    SecurityProfile,
    Volume,
)


SANDBOX_IMAGE = "contraponto-sandbox:0.1.0"
COMMAND_TIMEOUT_SECONDS = 300
SANDBOX_MAX_DURATION_SECONDS = 330
_LIMITS = "ulimit -u 64 -v 2097152 -f 20480"


@dataclass(frozen=True)
class CommandResult:
    stdout: bytes
    stderr: bytes
    returncode: int


async def run_in_microsandbox(command: str, workspace: str | Path) -> CommandResult:
    """Executa ``command`` sem rede, montando somente ``workspace``."""
    workspace_path = Path(workspace).resolve()
    if not workspace_path.is_dir():
        raise ValueError(f"Workspace do sandbox não existe: {workspace_path}")

    sandbox_name = f"contraponto-{uuid4().hex}"
    limited_command = f"{_LIMITS}; {command}"
    async with asyncio.timeout(SANDBOX_MAX_DURATION_SECONDS + 30):
        async with await Sandbox.create(
            sandbox_name,
            image=SANDBOX_IMAGE,
            pull_policy=PullPolicy.NEVER,
            cpus=1,
            memory=1024,
            workdir="/workspace",
            security=SecurityProfile.RESTRICTED,
            network=Network.none(),
            max_duration=SANDBOX_MAX_DURATION_SECONDS,
            ephemeral=True,
            env={
                "HOME": "/workspace",
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "PYTHONPATH": "/workspace",
                "MPLBACKEND": "Agg",
                "MPLCONFIGDIR": "/tmp/matplotlib",
            },
            volumes={
                "/workspace": Volume.bind(
                    str(workspace_path),
                    nosuid=True,
                    nodev=True,
                )
            },
        ) as sandbox:
            output = await sandbox.exec(
                "bash",
                ["-c", limited_command],
                cwd="/workspace",
                timeout=COMMAND_TIMEOUT_SECONDS,
            )

    return CommandResult(
        stdout=output.stdout_bytes,
        stderr=output.stderr_bytes,
        returncode=output.exit_code,
    )
