from typing import Optional
from langgraph.graph import MessagesState


class ChatGraphState(MessagesState):
    chat_id: str
    user_id: str
    context: Optional[str]
    agent_name: Optional[str]
    selected_agent: Optional[str]
    next_node: Optional[str]
