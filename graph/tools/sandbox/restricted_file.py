import asyncio
import json
import re
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


def _command_for_file(comando: str, allowed_file: Path) -> list[str]:
    """Monta um bubblewrap que expõe apenas o arquivo permitido."""
    command_with_limits = f"ulimit -u 64 -v 2097152 -f 20480; {comando}"
    command = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/usr/local", "/usr/local",
        "--dir", "/workspace",
        "--chmod", "0555", "/workspace",
        "--bind", str(allowed_file), f"/workspace/{allowed_file.name}",
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


def restricted_file_tool(filename: str, formatter: Callable[[str | Path], str | None] | None = None,) -> BaseTool:
    """Cria uma ferramenta com acesso exclusivo a um arquivo do sandbox.

    O arquivo permitido pode ser lido e alterado, mas não excluído. O diretório
    virtual exposto ao processo não permite criar outros arquivos e não contém
    nenhum dos demais arquivos reais do sandbox.
    """
    safe_filename = Path(filename).name
    if safe_filename != filename or safe_filename in {"", ".", ".."}:
        raise ValueError("filename deve ser somente o nome de um arquivo")
    tool_name = f"execute_{re.sub(r'[^a-zA-Z0-9_]+', '_', safe_filename.removesuffix('.json').removesuffix('.md'))}_restricted"

    async def execute_restricted_file(comando: str, config: RunnableConfig) -> str:
        if not isinstance(comando, str) or not comando.strip():
            return _result(stderr="O comando deve ser uma string não vazia".encode(), returncode=-1)

        try:
            sandbox_dir = Path(await _extrai_sandbox_dir(config))
            allowed_file = sandbox_dir / safe_filename
            if allowed_file.is_symlink() or (allowed_file.exists() and not allowed_file.is_file()):
                return _result(
                    stderr=f"{safe_filename} precisa ser um arquivo regular".encode(),
                    returncode=-1,
                )
            allowed_file.touch(exist_ok=True)
            command = _command_for_file(comando, allowed_file)
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return _result(stderr=b"Comando excedeu o tempo limite (120s)", returncode=-1)

            if formatter:
                warning = formatter(sandbox_dir)
                if warning:
                    stderr += f"\nNão foi possível formatar {safe_filename}: {warning}".encode()
            return _result(stdout, stderr, process.returncode)
        except (OSError, ValueError, RuntimeError) as exc:
            return _result(stderr=str(exc).encode(), returncode=-1)

    return tool(
        tool_name,
        description=(
            f"Lê e escreve somente {safe_filename}. "
            f"Não exclua {safe_filename}, não crie outros arquivos e não acesse outros arquivos do sandbox."
        ),
    )(execute_restricted_file)
