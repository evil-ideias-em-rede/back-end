from .base import run_agent
from .prompts.editor.template_editor_prompt import TEMPLATE_EDITOR_PROMPT


async def template_editor_node(state, config=None):
    print(f"Template editor is executing for {state.get('agent_name')}...")
    return await run_agent(state, TEMPLATE_EDITOR_PROMPT, config)
