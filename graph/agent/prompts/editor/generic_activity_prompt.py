from ..loader import render
from .rules import _NEUTRALITY_BLOCK, _SANDBOX_FLOW_EDIT


EDITOR_GENERIC_ACTIVITY_PROMPT = f"""
{render("16-editor-no-documento")}

{_NEUTRALITY_BLOCK}

{_SANDBOX_FLOW_EDIT}
""".strip()
