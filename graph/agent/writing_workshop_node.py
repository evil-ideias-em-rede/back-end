from .base import run_agent
from .prompts.audiencias_sugeridas.writing_workshop_prompt import WRITING_WORKSHOP_PROMPT
from .prompts.editor.writing_workshop_prompt import EDITOR_WRITING_WORKSHOP_PROMPT


async def writing_workshop_node(state, config=None):
    print(f"Writing workshop is executing for {state.get('agent_name')}...")
    prompt = EDITOR_WRITING_WORKSHOP_PROMPT if state.get("editor_mode") else WRITING_WORKSHOP_PROMPT
    return await run_agent(state, prompt, config)
