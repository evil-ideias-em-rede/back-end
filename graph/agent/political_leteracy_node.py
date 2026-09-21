from .base import run_agent
from .prompts.audiencias_sugeridas.political_leteracy_prompt import LETRAMENTO_POLITICO_PROMPT
from .prompts.editor.political_leteracy_prompt import EDITOR_POLITICAL_LETERACY_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def political_leteracy_node(state, config=None):
    #remover_planning_json(state)
    print(f"Political leteracy is executing for {state.get('agent_name')}...")
    prompt = EDITOR_POLITICAL_LETERACY_PROMPT if state.get("editor_mode") else LETRAMENTO_POLITICO_PROMPT
    return await run_agent(state, prompt, config)
