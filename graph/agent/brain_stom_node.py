from .base import run_agent
from .prompts.brain_storm_prompt import get_brainstorm
from graph.tools.sandbox.format_planning import format_planning_file
from graph.tools.sandbox.restricted_file import restricted_file_tool
execute_planning_bash = restricted_file_tool("planning.json", formatter=format_planning_file)


async def brain_storm_node(state, config=None):
    agent_name = state.get('agent_name')
    print(f"Brain storm is executing for {agent_name}...")
    restricted_prompt = get_brainstorm(agent_name).replace("execute_bash", execute_planning_bash.name)
    return await run_agent(state, restricted_prompt, config, tools=[execute_planning_bash])
