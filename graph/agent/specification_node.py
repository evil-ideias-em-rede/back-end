import json
from .base import run_agent
from .prompts.specification_prompt import SPECIFICATION_PROMPT
from graph.tools.sandbox.workdir import workspace_for_chat


def clear_unaccepted_plan(state) -> None:
    """Lê o planning.json privado do par usuário/chat atual."""
    work_dir = workspace_for_chat(str(state["user_id"]), str(state["chat_id"]))
    planning_file = work_dir / "sandbox" / "planning.json"

    if not planning_file.is_file(): return
    if planning_file.is_symlink(): return

    try:
        data = json.loads(planning_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return

    if isinstance(data, list):
        data = [item for item in data if not isinstance(item, dict) or item.get("user_has_accepted") is not False]
        try:
            planning_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",)
        except OSError as exc:
            return


async def specification_node(state, config=None):
    print("Specification is executing...")
    clear_unaccepted_plan(state)
    return await run_agent(state, SPECIFICATION_PROMPT, config)
