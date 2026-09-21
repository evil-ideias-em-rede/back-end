from .base import run_agent
from .prompts.audiencias_sugeridas.brain_storm_prompt import BRAINSTORM_PROMPT
from graph.tools.sandbox.format_planning import format_planning_file
from graph.tools.sandbox.restricted_file import restricted_file_tool
from graph.tools.retrieval.audiencias import consultar_audiencia_por_id
from graph.tools.retrieval.tool_buscar_audiencias import buscar_audiencias
from graph.tools.retrieval.tool_consultar_audiencias_sql import consultar_audiencias_sql
execute_planning_bash = restricted_file_tool("planning.json", formatter=format_planning_file)


async def brainstorm_node(state, config=None):
    agent_name = state.get('agent_name')
    print(f"Brain storm is executing for {agent_name}...")
    restricted_prompt = BRAINSTORM_PROMPT.replace("execute_bash", execute_planning_bash.name)
    return await run_agent(
        state,
        restricted_prompt,
        config,
        tools=[
            execute_planning_bash,
            consultar_audiencia_por_id,
            buscar_audiencias,
            consultar_audiencias_sql,
        ],
    )
