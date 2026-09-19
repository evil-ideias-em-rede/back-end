from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field


class GoogleLoginIn(BaseModel):
    id_token: str


class PasswordRegisterIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = Field(default=None, max_length=160)


class PasswordLoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class LoginOut(BaseModel):
    access_token: str
    user_id: UUID
    email: str
    name: Optional[str] = None
    picture_url: Optional[str] = None


class UserOut(BaseModel):
    id: UUID
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
    agent_name: str


class SendMessageOut(BaseModel):
    reply: str


class TurmaCreateIn(BaseModel):
    school: str = Field(min_length=1, max_length=200)
    series: str = Field(min_length=1, max_length=80)
    id_series: str = Field(default="A", min_length=1, max_length=20, validation_alias=AliasChoices("idSeries", "id_series"))
    qtd: int = Field(default=0, ge=0, validation_alias=AliasChoices("qtd", "student_count"))
    disciplina: str = Field(min_length=1, max_length=120)
    color: Optional[str] = Field(default=None, max_length=30)
    image: Optional[str] = Field(default=None, max_length=1000)


class TurmaOut(BaseModel):
    id: str
    school: str
    series: str
    idSeries: str
    qtd: int
    disciplina: str
    color: Optional[str] = None
    image: Optional[str] = None
    lastModifiedAt: int


class TurmaUpdateIn(TurmaCreateIn):
    pass


class TemplateCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = Field(default=None, max_length=5000)
    html_content: str = Field(default="", max_length=2_000_000, validation_alias=AliasChoices("htmlContent", "html_content"))
    turma_ids: list[UUID] = Field(default_factory=list, validation_alias=AliasChoices("turmaIds", "turma_ids"))


class TemplateOut(BaseModel):
    id: str
    title: str
    qtd: int
    description: Optional[str] = None
    htmlContent: str
    turmaIds: list[str]
    lastModifiedAt: int


class TemplateUpdateIn(TemplateCreateIn):
    pass


class MaterialCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    autoral: bool = False
    orientation: Literal["V", "H"] = "V"
    type: Literal["source", "slide", "atv"] = "source"
    category: Literal["plano", "material", "atividade"] = "material"
    file_type: Literal["pdf", "html"] = Field(default="html", validation_alias=AliasChoices("fileType", "file_type"))
    html_content: str = Field(default="", max_length=2_000_000, validation_alias=AliasChoices("htmlContent", "html_content"))
    file_url: Optional[str] = Field(default=None, max_length=2000, validation_alias=AliasChoices("fileUrl", "file_url"))
    turma_ids: list[UUID] = Field(default_factory=list, validation_alias=AliasChoices("turmaIds", "turma_ids"))


class MaterialOut(BaseModel):
    id: str
    title: str
    autoral: bool
    orientation: Literal["V", "H"]
    type: Literal["source", "slide", "atv"]
    category: Literal["plano", "material", "atividade"]
    fileType: Literal["pdf", "html"]
    qtd: int
    htmlContent: str
    fileUrl: Optional[str] = None
    turmaIds: list[str]
    lastModified: str
    lastModifiedAt: int


class MaterialUpdateIn(MaterialCreateIn):
    pass
