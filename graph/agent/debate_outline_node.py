from .base import run_agent
from .prompts.debate_outline_prompt import ROTEIRO_DEBATE_PROMPT


async def debate_outline_node(state, config=None):
    print(f"Debate outline is executing for {state.get('agent_name')}...")
    return await run_agent(state, ROTEIRO_DEBATE_PROMPT, config)
