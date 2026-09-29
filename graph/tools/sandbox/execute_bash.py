"""Tool de shell executada em uma microVM descartável."""

import asyncio
import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from microsandbox import ExecTimeoutError

from .format_planning import format_planning_file
from .microsandbox_runtime import COMMAND_TIMEOUT_SECONDS, run_in_microsandbox
from .workdir import _extrai_sandbox_dir


def _format_warning(work_dir: str) -> str:
    error = format_planning_file(work_dir)
    return (
        f"\nNão foi possível formatar planning.json automaticamente: {error}"
        if error
        else ""
    )


def _result(
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
) -> str:
    return json.dumps(
        {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": returncode,
            "sucesso": returncode == 0,
        },
        ensure_ascii=False,
    )


@tool
async def execute_bash(comando: str, config: RunnableConfig) -> str:
    """Executa um comando sem rede no sandbox privado desta conversa.

    O diretório `/workspace` persiste entre chamadas e contém o acervo
    pedagógico do sistema. A microVM usada em cada chamada é descartada ao
    término da execução.

    Args:
        comando: comando Bash a executar em `/workspace`.

    Returns:
        JSON com ``stdout``, ``stderr``, ``returncode`` e ``sucesso``.
    """
    if not isinstance(comando, str) or not comando.strip():
        return _result(stderr=b"O comando deve ser uma string nao vazia", returncode=-1)

    try:
        work_dir = await _extrai_sandbox_dir(config)
    except (OSError, RuntimeError, ValueError) as exc:
        return _result(stderr=str(exc).encode(), returncode=-1)

    try:
        output = await run_in_microsandbox(comando, work_dir)
        warning = _format_warning(work_dir)
        stderr = output.stderr + warning.encode()
        return _result(output.stdout, stderr, output.returncode)
    except ExecTimeoutError:
        warning = _format_warning(work_dir)
        message = (
            f"Comando excedeu o tempo limite ({COMMAND_TIMEOUT_SECONDS}s){warning}"
        )
        return _result(stderr=message.encode(), returncode=-1)
    except TimeoutError:
        warning = _format_warning(work_dir)
        return _result(
            stderr=(
                "A inicializacao ou execucao do sandbox excedeu o tempo limite"
                f"{warning}"
            ).encode(),
            returncode=-1,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        warning = _format_warning(work_dir)
        return _result(stderr=f"{exc}{warning}".encode(), returncode=-1)
