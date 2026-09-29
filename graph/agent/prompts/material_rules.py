"""Critérios por material, compartilhados pela geração e pela edição."""

MATERIAL_RULES = {
    "lesson_plan": """
PLANO DE AULA
Alinhe objetivos observáveis, atividades, habilidades verificadas e avaliação.
Detalhe agrupamento, recursos, instruções ao estudante e tempos com margem.
Para criar ou reformular o plano, consulte e leia uma base com consultar_templates.
No editor, o catálogo também está em templates/templates.json. Use exclusivamente
os pessoais quando houver uploads; sem uploads, escolha um padrão. Adapte modelos
paisagem a retrato de forma legível.
Uma alteração pontual não autoriza trocar o template atual.
""",
    "debate": """
ROTEIRO DE DEBATE
Defina questão em disputa, papéis, dossiês de falas reais, regras e tempos,
perguntas do mediador, ficha de observação e fechamento sem vencedor imposto.
Não invente oposição onde a audiência só contém uma posição: explique a
limitação e peça uma escolha entre outra fonte ou análise de argumentos.
Nas duas telas, use consultar_acervo para formatos-de-aula/_indice.md; referências possíveis:
formatos-de-aula/debate-com-posicoes-invertidas.md,
formatos-de-aula/juri-simulado.md e
formatos-de-aula/grupo-de-verbalizacao-e-grupo-de-observacao.md.
Leia só o formato pertinente. Use um template disponível como base, adaptando
a cópia ao roteiro em A4 retrato. Não presuma ausência de templates de debate
sem consultar o catálogo pessoal.
""",
    "writing_workshop": """
OFICINA DE REDAÇÃO
Defina gênero, destinatário, finalidade e extensão. Se o gênero indispensável
não estiver definido, esclareça-o. Prepare coletânea com autoria, comando sem
tese imposta, planejamento, escrita, revisão entre pares, reescrita e rubrica.
Não escreva a redação do estudante nem invente posições para completar a coletânea.
Nas duas telas, leia com consultar_acervo, conforme pertinência, formatos-de-aula/oficina.md,
formatos-de-aula/revisao-entre-pares.md e formatos-de-aula/redacao-coletiva.md.
Use um template disponível como base, adaptando a cópia para A4 retrato, com
espaço de escrita adequado e orientações distintas para professor e estudante.
""",
    "political_leteracy": """
LETRAMENTO MIDIÁTICO E POLÍTICO
Prepare instrumentos para identificar autoria e contexto, distinguir afirmação
de evidência, examinar recursos de persuasão e retornar à fonte primária.
Aplique critérios iguais às posições existentes; não invente um segundo lado.
Notícias externas precisam de fonte verificável. Sem notícias, proponha produção
e comparação de títulos pelos estudantes, deixando explícito que é exercício.
Nas duas telas, consulte via consultar_acervo formatos-de-aula/analise-do-discurso-midiatico.md e, se
pertinente, formatos-de-aula/grade-comparativa-em-grupo.md ou
formatos-de-aula/telejornal.md. Use um template do catálogo atual como base,
adaptando a cópia para a sequência e as fichas em A4 retrato.
""",
    "slides": """
APRESENTAÇÃO DE SLIDES
Use uma ideia por slide, títulos curtos, texto legível à distância, contraste
e atividades com comandos claros. Separe notas de condução do texto projetado.
Não invente gráficos, imagens ou números. Não finja ter ferramenta de imagens.
Cada slide é uma section data-ied-page diretamente no body, em A4 paisagem
(297 mm x 210 mm), compatível com a exportação H do editor. Não use A4 retrato
nem controles de navegação que escondam páginas. Preserve os slides existentes
nas edições pontuais. Notas de condução não podem encobrir o conteúdo projetado.
No editor, leia estrutura_slides.md quando disponível e guia_edicao.md.
Sempre leia slide-template.html com consultar_templates e use-o como base,
mesmo havendo templates pessoais. Preserve sua paleta e layouts pertinentes,
adaptando a cópia a A4 paisagem e data-ied-page. Pessoais são apoio, não a base.
Em edição pontual, preserve os slides existentes sem substituir seu layout.
Consulte formatos-de-aula/aula-expositiva-dialogada.md quando precisar planejar
interação com a turma, e teorias/_indice.md apenas se o pedido for pedagógico.
""",
    "generic": """
BRAINSTORM LIVRE / ATIVIDADE PERSONALIZADA
Converse e proponha possibilidades enquanto o professor estiver explorando.
Só produza o material após solicitação ou confirmação; uma pergunta não é
autorização para escrever HTML. Aproveite definições anteriores da conversa.
Para gerar, identifique o artefato e seu público; organize instruções, recursos,
tempos e produto observável conforme o pedido, sem impor um plano de aula.
Nas duas telas, use consultar_acervo para formatos-de-aula/_indice.md e escolha uma estratégia
e teorias/_indice.md para a fundamentação. Para gerar, consulte obrigatoriamente
um template disponível como base e adapte sua cópia ao artefato pedido.
Não prometa geração de imagem, áudio ou vídeo com ferramentas inexistentes.
""",
    "editor_geral": """
EDITOR GERAL DE TEMPLATES
O HTML atual e o pedido do professor definem o tipo e o escopo do material.
Não transforme automaticamente um documento em plano de aula.
Em substituição ou criação expressamente solicitada, consulte
consultar_templates para escolher obrigatoriamente uma base, considerando os
vínculos com a turma; formatos-de-aula/_indice.md para
estratégias e teorias/_indice.md para desenho pedagógico. Leia só a referência
escolhida. Para correções de texto, preserve o formato sem escolher nova teoria.
""",
}


def material_rules(material: str) -> str:
    return MATERIAL_RULES[material].strip()
