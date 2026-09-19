import asyncio
import hashlib
import logging
import os
import shutil
from pathlib import Path
from urllib.parse import quote
from langchain_core.runnables import RunnableConfig


BASE_WORKDIRS = (Path(__file__).resolve().parent.parent.parent.parent / "workdirs").resolve()
SHARED_FILES_DIR = (Path(__file__).resolve().parent / "shared").resolve()
logger = logging.getLogger(__name__)


def workspace_id_for_chat(user_id: str, chat_id: str) -> str:
    """Gera um nome opaco e estável para o sandbox de um chat.

    O hash impede colisões entre usuários mesmo que, no futuro, o formato do
    identificador do chat mude. Todos os agentes do mesmo usuário/chat recebem
    exatamente o mesmo resultado.
    """
    identity = f"{user_id}:{chat_id}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def workspace_for_chat(user_id: str, chat_id: str) -> Path:
    return BASE_WORKDIRS / workspace_id_for_chat(user_id, chat_id)


def _agent_key(agent_name: str | None) -> str | None:
    """Normaliza o nome recebido para localizar a pasta do agente."""
    if not agent_name:
        return None
    return str(agent_name).strip().lower().replace("-", "_")


def _agent_dir_candidates(agent_name: str | None) -> list[str]:
    """Retorna nomes de pasta possíveis, priorizando o nome exato do agente."""
    agent_key = _agent_key(agent_name)
    if not agent_key:
        return []

    candidates = [agent_key]
    if agent_key.endswith("_node"):
        candidates.append(agent_key.removesuffix("_node"))
    else:
        candidates.append(f"{agent_key}_node")

    # Nomes curtos enviados pela API para os nodes atuais.
    node_aliases = {
        "debate": "debate_outline_node",
        "generic": "generic_activity_node",
        "political_leteracy": "political_leteracy_node",
    }
    if agent_key in node_aliases:
        candidates.append(node_aliases[agent_key])

    # Compatibilidade com o nome usado anteriormente para o plano de aula.
    if agent_key in {"lesson_plan", "lesson_plan_node"}:
        candidates.append("plano_de_aula")
    return list(dict.fromkeys(candidates))


def _agent_source_dir(agent_name: str | None) -> Path | None:
    """Encontra shared/<agente> sem exigir cadastro prévio do agente."""
    for directory_name in _agent_dir_candidates(agent_name):
        candidate = SHARED_FILES_DIR / directory_name
        if candidate.is_dir():
            return candidate
    return None


def _copy_flat_files(source_dir: Path, target_dir: Path, skip_names: set[str] | None = None) -> None:
    """Copia somente arquivos diretamente no diretório de origem."""
    if not source_dir.is_dir():
        return
    skip_names = skip_names or set()
    for source in source_dir.iterdir():
        if not source.is_file() or source.name in skip_names:
            continue
        target = target_dir / source.name
        if not target.exists():
            shutil.copy2(source, target)


def _copy_shared_files(sandbox_dir: Path, agent_name: str | None = None) -> None:
    """Prepara os arquivos comuns e os arquivos do agente na mesma raiz."""
    # O planejamento é um artefato exclusivo do brainstorm. Os nodes finais
    # removem o arquivo e não devem recriá-lo ao preparar suas ferramentas.
    skip_names = set()
    if _agent_key(agent_name) not in {"brainstorm", "brainstorm_node"}:
        skip_names.add("planning.json")
    _copy_flat_files(SHARED_FILES_DIR, sandbox_dir, skip_names=skip_names)
    agent_source_dir = _agent_source_dir(agent_name)
    if agent_source_dir:
        _copy_flat_files(agent_source_dir, sandbox_dir, skip_names=skip_names)


def remover_planning_json(state: dict) -> None:
    """Remove o planejamento do sandbox associado à sessão do agente."""
    work_dir = workspace_for_chat(str(state["user_id"]), str(state["chat_id"]))
    sandbox_dir = work_dir / "sandbox"
    try:
        sandbox_dir.mkdir(parents=True, exist_ok=True)
        planning_path = sandbox_dir / "planning.json"
        planning_path.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError("Não foi possível remover planning.json do sandbox") from exc


def _validar_work_dir(work_dir: str | os.PathLike[str]) -> Path:
    """Resolves e valida um diretório isolado imediatamente abaixo de workdirs/."""
    work_dir_resolvido = Path(work_dir).resolve()
    try:
        relativo = work_dir_resolvido.relative_to(BASE_WORKDIRS)
    except ValueError as exc:
        raise ValueError(f"work_dir resolvido fora da base permitida: {work_dir_resolvido}") from exc

    if len(relativo.parts) != 1 or relativo.parts[0] in {"", ".", ".."}:
        raise ValueError("work_dir deve identificar uma única conversa diretamente abaixo de workdirs/")
    return work_dir_resolvido


def criar_url_download(work_dir: str | os.PathLike[str], filename: str) -> str:
    """Cria a URL pública sem expor um caminho absoluto do servidor."""
    if Path(filename).name != filename:
        raise ValueError("filename deve conter apenas o nome do arquivo")

    work_dir_resolvido = _validar_work_dir(work_dir)
    identificador = work_dir_resolvido.relative_to(BASE_WORKDIRS).name
    return f"/downloads/{quote(identificador, safe='')}/{quote(filename, safe='')}"


async def _extrai_work_dir(config: RunnableConfig) -> str:
    configurable = config.get("configurable", {})
    user_id = configurable.get("user_id")
    chat_id = configurable.get("thread_id")
    if user_id and chat_id:
        # Mesmo que algum chamador forneça work_dir, a identidade do chat tem
        # precedência. Isso impede que um agente aponte para outro workspace.
        work_dir = workspace_for_chat(str(user_id), str(chat_id))
    else:
        # Mantém compatibilidade com chamadas locais/testes sem identidade de
        # usuário, sempre validando o identificador abaixo de workdirs/.
        explicit_work_dir = configurable.get("work_dir")
        thread_id = chat_id or user_id
        if explicit_work_dir:
            work_dir = explicit_work_dir
        elif thread_id:
            work_dir = BASE_WORKDIRS / str(thread_id)
        else:
            raise ValueError("Forneça user_id e thread_id em config['configurable']")

    work_dir_resolvido = _validar_work_dir(work_dir)
    work_dir_resolvido.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        # A raiz da conversa pertence à aplicação. Apenas sandbox/ será entregue ao processo não confiável executado como nobody.
        work_dir_resolvido.chmod(0o700)
    return str(work_dir_resolvido)


async def _extrai_sandbox_dir(config: RunnableConfig) -> str:
    """Retorna a área gravável pelo processo isolado da conversa."""
    work_dir = Path(await _extrai_work_dir(config))
    sandbox_dir = work_dir / "sandbox"
    sandbox_dir.mkdir(exist_ok=True)

    # Os arquivos comuns e os específicos do agente ficam diretamente na raiz
    # do sandbox do chat. O processo isolado continua vendo somente esse
    # diretório, sem conhecer a estrutura interna do projeto.
    configurable = config.get("configurable", {})
    agent_name = configurable.get("agent_name") or configurable.get("selected_agent")
    _copy_shared_files(sandbox_dir, agent_name)

    if os.name == "posix":
        app_uid, app_gid = os.geteuid(), os.getegid()
        stat = sandbox_dir.stat()
        if stat.st_uid != app_uid or stat.st_gid != app_gid:
            try:
                os.chown(sandbox_dir, app_uid, app_gid)
            except PermissionError as exc:
                raise RuntimeError("A aplicação não possui permissão para preparar o diretório do sandbox") from exc

        # O user namespace mapeia o UID 65534 visto dentro do sandbox para o UID da aplicação fora dele. Assim, 0700 continua gravável no bwrap
        # sem liberar acesso para outros usuários do container.
        sandbox_dir.chmod(0o700)

    return str(sandbox_dir.resolve())


async def _extrai_exports_dir(config: RunnableConfig) -> str:
    """Retorna a área privada onde somente a aplicação grava exportações."""
    work_dir = Path(await _extrai_work_dir(config))
    exports_dir = work_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    if os.name == "posix":
        exports_dir.chmod(0o700)
    return str(exports_dir.resolve())


async def remover_work_dir(thread_id: str | None) -> bool:
    """Remove os arquivos associados à conversa."""
    if not thread_id:
        return False
    try:
        work_dir = _validar_work_dir(BASE_WORKDIRS / str(thread_id))
        if not work_dir.exists():
            return False
        await asyncio.to_thread(shutil.rmtree, work_dir)
        return True
    except (OSError, ValueError):
        logger.exception("Não foi possível remover o workdir da conversa %s", thread_id)
        return False


async def remover_workspace_do_chat(user_id: str | None, chat_id: str | None) -> bool:
    """Remove o sandbox pertencente ao par usuário/chat."""
    if not user_id or not chat_id:
        return False
    return await remover_work_dir(workspace_id_for_chat(str(user_id), str(chat_id)))
