from .base import run_agent
from .prompts.editor.general_editor_prompt import EDITOR_GENERAL_PROMPT


async def general_editor_node(state, config=None):
    """Edita templates existentes sem participar da geração por audiência."""
    if not state.get("editor_mode"):
        raise ValueError("general_editor_node só pode ser usado no modo de edição")
    print(f"General editor is executing for {state.get('agent_name')}...")
    return await run_agent(state, EDITOR_GENERAL_PROMPT, config)
