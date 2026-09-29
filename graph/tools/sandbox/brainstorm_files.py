"""O brainstorm nunca recebe HTML.html no volume montado para seu shell."""

from .format_planning import format_planning_file
from .restricted_file import restricted_file_tool

execute_brainstorm_planning = restricted_file_tool("planning.json", formatter=format_planning_file)
execute_brainstorm_planning.name = "execute_brainstorm_planning"
