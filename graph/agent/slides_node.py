from .base import run_agent
from .prompts.audiencias_sugeridas.slides_prompt import SLIDES_PROMPT
from .prompts.editor.slides_prompt import EDITOR_SLIDES_PROMPT


async def slides_node(state, config=None):
    print(f"Slides is executing for {state.get('agent_name')}...")
    prompt = EDITOR_SLIDES_PROMPT if state.get("editor_mode") else SLIDES_PROMPT
    return await run_agent(state, prompt, config)
