from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field


class GoogleLoginIn(BaseModel):
    id_token: str


class LoginOut(BaseModel):
    access_token: str
    user_id: UUID
    email: str
    name: Optional[str] = None
    picture_url: Optional[str] = None


class ChatTabOut(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ChatTabCreateIn(BaseModel):
    title: str


class ChatMessageOut(BaseModel):
    id: UUID
    role: str
    content: Optional[str] = None
    filename: Optional[str] = None
    created_at: datetime


class SendMessageIn(BaseModel):
    # ``input`` é o nome usado pelo frontend. ``text`` permanece aceito para
    # compatibilidade com clientes antigos; ``inout`` cobre o typo usado na
    # primeira integração do botão.
    text: str = Field(validation_alias=AliasChoices("input", "text", "inout"))
    agent_name: Optional[str] = None


class SendMessageOut(BaseModel):
    reply: str
