"""Endpoints de mensagens do fluxo de trabalho.

Este é o ponto de entrada para o texto enviado pelo frontend:

* ``POST /api/workflow/sessions/{session_id}/messages``: brainstorm/audiências.
* ``POST /api/workflow/sessions/{session_id}/editor/messages``: edição do material.

O texto recebido está em ``body.text``. O processamento compartilhado continua
em ``workflow_router._process_workflow_message`` para não duplicar a lógica.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from auth.dependencies import CurrentUser, get_optional_current_user
from routers.workflow_router import (
    WorkflowMessageIn,
    WorkflowReplyOut,
    _process_workflow_message,
)
from pydantic import Field


class EditorWorkflowMessageIn(WorkflowMessageIn):
    """Corpo exclusivo das mensagens enviadas pela tela de edição."""

    user_edited: bool = Field(
        default=False,
        description="Indica se o usuário alterou manualmente o material no editor.",
    )


router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# POST /api/workflow/sessions/{session_id}/messages
#
# Parâmetros:
# - session_id: str — UUID da sessão criada anteriormente.
# - body: WorkflowMessageIn — JSON recebido no corpo:
#     {
#       "text": "mensagem escrita pelo professor",
#       "agent_name": "brainstorm",
#       "hidden": false
#     }
#   - text: str — mensagem enviada pelo usuário.
#   - agent_name: str — neste endpoint, normalmente "brainstorm".
#   - hidden: bool — marca a mensagem como interna quando true.
# - user: CurrentUser | None — usuário autenticado obtido pelo token; pode ser
#   None quando a aplicação está usando o modo público/mock.
#
# Retorno: WorkflowReplyOut com session_id, message e html_url quando houver.
@router.post("/sessions/{session_id}/messages", response_model=WorkflowReplyOut)
async def send_workflow_message(
    session_id: str,
    body: WorkflowMessageIn,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    """Recebe mensagens do brainstorm e do fluxo de audiências sugeridas."""
    # PONTO DE ENTRADA DO TEXTO DO BRAINSTORM: body.text
    return await _process_workflow_message(session_id, body, user, editor_mode=False)


# POST /api/workflow/sessions/{session_id}/editor/messages
#
# Parâmetros:
# - session_id: str — UUID da sessão do material que será editado.
# - body: EditorWorkflowMessageIn — JSON recebido no corpo:
#     {
#       "text": "Altere o título da primeira página",
#       "agent_name": "lesson_plan",
#       "hidden": false,
#       "user_edited": true
#     }
#   - text: str — pedido de alteração ou orientação do usuário.
#   - agent_name: str — agente final responsável pelo material, como
#     "lesson_plan", "debate", "generic", "writing_workshop" ou "slides".
#   - hidden: bool — marca a mensagem como interna quando true.
#   - user_edited: bool — true se o usuário escreveu, apagou ou formatou algo
#     manualmente no editor; false caso contrário.
# - user: CurrentUser | None — usuário autenticado obtido pelo token; pode ser
#   None quando a aplicação está usando o modo público/mock.
#
# Retorno: WorkflowReplyOut com a resposta do agente e html_url do HTML
# atualizado, quando o agente produzir HTML.html.
@router.post("/sessions/{session_id}/editor/messages", response_model=WorkflowReplyOut)
async def send_editor_workflow_message(
    session_id: str,
    body: EditorWorkflowMessageIn,
    user: CurrentUser | None = Depends(get_optional_current_user),
):
    """Recebe pedidos pontuais para editar o material do usuário."""
    # PONTO DE ENTRADA DO TEXTO DO EDITOR: body.text
    if body.agent_name == "brainstorm":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="O endpoint de edição exige um agente final, não o brainstorm.",
        )
    
    if body.user_edited:
        body.text = f"""
        O arquivo HTML.html foi editado no frontend do usuário, portanto só responda ou faça
        o que o usuaŕio gostaria sem alterar como já está, pois o usuário consegue edita-lo também.
        Sendo assim, o prompt do usuário foi: 
        
        Prompt do usuário: {body.text}
        """
        
    return await _process_workflow_message(session_id, body, user, editor_mode=True)
