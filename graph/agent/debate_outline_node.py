from .base import run_agent
from .prompts.debate_outline_prompt import ROTEIRO_DEBATE_PROMPT
from graph.tools.sandbox.workdir import remover_planning_json


async def debate_outline_node(state, config=None):
    remover_planning_json(state)
    print(f"Debate outline is executing for {state.get('agent_name')}...")
    return await run_agent(state, ROTEIRO_DEBATE_PROMPT, config)
