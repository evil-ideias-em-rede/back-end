from .base import run_agent
from .prompts.audiencias_sugeridas.debate_outline_prompt import ROTEIRO_DEBATE_PROMPT
from .prompts.editor.debate_outline_prompt import EDITOR_DEBATE_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def debate_outline_node(state, config=None):
    #remover_planning_json(state)
    print(f"Debate outline is executing for {state.get('agent_name')}...")
    prompt = EDITOR_DEBATE_PROMPT if state.get("editor_mode") else ROTEIRO_DEBATE_PROMPT
    return await run_agent(state, prompt, config)
