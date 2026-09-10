from .base import run_agent
from .prompts.specification_prompt import get_specification
from graph.tools.sandbox.restricted_file import restricted_file_tool
execute_specification_bash = restricted_file_tool("specification.json")


async def specification_node(state, config=None):
    agent_name = state.get('agent_name')
    print(f"Specification is executing for {agent_name}...")
    restricted_prompt = get_specification(agent_name).replace("execute_bash", execute_specification_bash.name)
    return await run_agent(state, restricted_prompt, config, tools=[execute_specification_bash])
