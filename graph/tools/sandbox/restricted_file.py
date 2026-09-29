"""Ferramenta que expõe somente arquivos explicitamente permitidos."""

import asyncio
import json
import re
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Callable

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from microsandbox import ExecTimeoutError

from .microsandbox_runtime import COMMAND_TIMEOUT_SECONDS, run_in_microsandbox
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


def _prepare_restricted_workspace(
    sandbox_dir: Path,
    filenames: Sequence[str],
    staging_dir: Path,
) -> list[Path]:
    """Copia somente os arquivos permitidos para a área montada na microVM."""
    originals = []
    for filename in filenames:
        original = sandbox_dir / filename
        if original.is_symlink() or (original.exists() and not original.is_file()):
            raise ValueError(f"{filename} precisa ser um arquivo regular")
        original.touch(exist_ok=True)
        shutil.copy2(original, staging_dir / filename)
        originals.append(original)
    return originals


def _sync_restricted_workspace(
    originals: Sequence[Path],
    staging_dir: Path,
) -> str | None:
    """Sincroniza os permitidos e recusa exclusões ou links criados pelo comando."""
    for original in originals:
        staged = staging_dir / original.name
        if staged.is_symlink() or not staged.is_file():
            return f"{original.name} nao pode ser excluido nem substituido por link"
    for original in originals:
        if original.is_symlink() or not original.is_file():
            return f"{original.name} deixou de ser um arquivo regular"
        shutil.copyfile(staging_dir / original.name, original)
    return None


def restricted_file_tool(
    filename: str | Sequence[str],
    formatter: Callable[[str | Path], str | None] | None = None,
) -> BaseTool:
    """Cria uma tool cuja microVM recebe exclusivamente os arquivos indicados."""
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
    tool_name = (
        "execute_"
        f"{re.sub(r'[^a-zA-Z0-9_]+', '_', primary_filename.removesuffix('.json').removesuffix('.md'))}"
        "_restricted"
    )

    async def execute_restricted_file(comando: str, config: RunnableConfig) -> str:
        if not isinstance(comando, str) or not comando.strip():
            return _result(
                stderr=b"O comando deve ser uma string nao vazia",
                returncode=-1,
            )

        try:
            sandbox_dir = Path(await _extrai_sandbox_dir(config))
            with tempfile.TemporaryDirectory(
                prefix=".restricted-",
                dir=sandbox_dir.parent,
            ) as temporary:
                staging_dir = Path(temporary)
                staging_dir.chmod(0o700)
                originals = _prepare_restricted_workspace(
                    sandbox_dir,
                    filenames,
                    staging_dir,
                )

                try:
                    output = await run_in_microsandbox(comando, staging_dir)
                except ExecTimeoutError:
                    sync_error = _sync_restricted_workspace(originals, staging_dir)
                    detail = sync_error or (
                        f"Comando excedeu o tempo limite ({COMMAND_TIMEOUT_SECONDS}s)"
                    )
                    return _result(stderr=detail.encode(), returncode=-1)
                except asyncio.CancelledError:
                    _sync_restricted_workspace(originals, staging_dir)
                    raise
                except Exception as exc:
                    sync_error = _sync_restricted_workspace(originals, staging_dir)
                    detail = sync_error or str(exc)
                    return _result(stderr=detail.encode(), returncode=-1)

                sync_error = _sync_restricted_workspace(originals, staging_dir)
                if sync_error:
                    return _result(stderr=sync_error.encode(), returncode=-1)

                stderr = output.stderr
                if formatter:
                    warning = formatter(sandbox_dir)
                    if warning:
                        stderr += (
                            f"\nNão foi possível formatar {primary_filename}: {warning}"
                        ).encode()
                return _result(output.stdout, stderr, output.returncode)
        except (OSError, ValueError, RuntimeError) as exc:
            return _result(stderr=str(exc).encode(), returncode=-1)

    allowed_names = " e ".join(filenames)
    return tool(
        tool_name,
        description=(
            f"Lê e escreve somente {allowed_names}. "
            "Não exclua esses arquivos, não crie outros arquivos e não acesse "
            "outros arquivos do sandbox."
        ),
    )(execute_restricted_file)
