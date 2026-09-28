import asyncio
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from .workdir import _extrai_sandbox_dir


def _result(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> str:
    return json.dumps(
        {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": returncode,
            "sucesso": returncode == 0,
        },
        ensure_ascii=False,
    )


COMMAND_TIMEOUT_SECONDS = 300


def _command_for_files(comando: str, allowed_files: Sequence[Path]) -> list[str]:
    """Monta um bubblewrap que expõe apenas os arquivos permitidos."""
    command_with_limits = f"ulimit -u 64 -v 2097152 -f 20480; {comando}"
    file_bindings = [
        argument
        for allowed_file in allowed_files
        for argument in ("--bind", str(allowed_file), f"/workspace/{allowed_file.name}")
    ]
    command = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/usr/local", "/usr/local",
        "--dir", "/workspace",
        "--chmod", "0555", "/workspace",
        *file_bindings,
        "--chdir", "/workspace",
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--dev", "/dev",
        "--clearenv",
        "--setenv", "PATH", "/usr/local/bin:/usr/bin:/bin",
        "--setenv", "HOME", "/workspace",
        "--cap-drop", "ALL",
        "--uid", "65534", "--gid", "65534",
        "bash", "-c", command_with_limits,
    ]
    if not Path("/.dockerenv").exists():
        command[command.index("--dev"):command.index("--dev")] = ["--proc", "/proc"]
    return command


def restricted_file_tool(
    filename: str | Sequence[str],
    formatter: Callable[[str | Path], str | None] | None = None,
) -> BaseTool:
    """Cria uma ferramenta com acesso exclusivo a arquivos do sandbox.

    Os arquivos permitidos podem ser lidos e alterados, mas não excluídos. O diretório
    virtual exposto ao processo não permite criar outros arquivos e não contém
    nenhum dos demais arquivos reais do sandbox.
    """
    filenames = [filename] if isinstance(filename, str) else list(filename)
    if not filenames:
        raise ValueError("informe pelo menos um arquivo permitido")
    if len(set(filenames)) != len(filenames):
        raise ValueError("os nomes dos arquivos permitidos não podem se repetir")
    for candidate in filenames:
        safe_candidate = Path(candidate).name
        if safe_candidate != candidate or safe_candidate in {"", ".", ".."}:
            raise ValueError("cada filename deve ser somente o nome de um arquivo")

    primary_filename = filenames[0]
    tool_name = f"execute_{re.sub(r'[^a-zA-Z0-9_]+', '_', primary_filename.removesuffix('.json').removesuffix('.md'))}_restricted"

    async def execute_restricted_file(comando: str, config: RunnableConfig) -> str:
        if not isinstance(comando, str) or not comando.strip():
            return _result(stderr="O comando deve ser uma string não vazia".encode(), returncode=-1)

        try:
            sandbox_dir = Path(await _extrai_sandbox_dir(config))
            allowed_files = [sandbox_dir / allowed_filename for allowed_filename in filenames]
            for allowed_file in allowed_files:
                if allowed_file.is_symlink() or (allowed_file.exists() and not allowed_file.is_file()):
                    return _result(
                        stderr=f"{allowed_file.name} precisa ser um arquivo regular".encode(),
                        returncode=-1,
                    )
                allowed_file.touch(exist_ok=True)
            command = _command_for_files(comando, allowed_files)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=COMMAND_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return _result(
                    stderr=f"Comando excedeu o tempo limite ({COMMAND_TIMEOUT_SECONDS}s)".encode(),
                    returncode=-1,
                )

            if formatter:
                warning = formatter(sandbox_dir)
                if warning:
                    stderr += f"\nNão foi possível formatar {primary_filename}: {warning}".encode()
            return _result(stdout, stderr, process.returncode)
        except (OSError, ValueError, RuntimeError) as exc:
            return _result(stderr=str(exc).encode(), returncode=-1)

    allowed_names = " e ".join(filenames)
    return tool(
        tool_name,
        description=(
            f"Lê e escreve somente {allowed_names}. "
            "Não exclua esses arquivos, não crie outros arquivos e não acesse outros arquivos do sandbox."
        ),
    )(execute_restricted_file)
