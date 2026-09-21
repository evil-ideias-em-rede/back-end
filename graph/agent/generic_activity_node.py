from .base import run_agent
from .prompts.audiencias_sugeridas.generic_activity_prompt import ATIVIDADE_GENERICA_PROMPT
from .prompts.editor.generic_activity_prompt import EDITOR_GENERIC_ACTIVITY_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def generic_activity_node(state, config=None):
    #remover_planning_json(state)
    print(f"Generic activity is executing for {state.get('agent_name')}...")
    prompt = EDITOR_GENERIC_ACTIVITY_PROMPT if state.get("editor_mode") else ATIVIDADE_GENERICA_PROMPT
    return await run_agent(state, prompt, config)
