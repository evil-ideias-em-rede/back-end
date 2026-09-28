from .format_planning import format_planning_file
from .restricted_file import restricted_file_tool


# Na tela de Audiências sugeridas, o agente só enxerga estes dois artefatos.
# O nome da ferramenta continua sendo execute_planning_restricted para manter
# compatibilidade com os prompts e sessões existentes.
execute_suggested_files = restricted_file_tool(
    ("planning.json", "HTML.html"),
    formatter=format_planning_file,
)
