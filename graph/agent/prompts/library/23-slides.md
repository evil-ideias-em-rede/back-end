---
id: 23-slides
system: global + role
inputs: [BNCC_SKILLS, BRIEFING, COVERAGE_REPORT, EXCERPTS, LEGISLATIVE_GLOSSARY, LESSON_FORMAT, PEDAGOGICAL_PRINCIPLES, SOURCE_RULES, SPECIFICATION, STANCE_MAP, TEACHER_MATERIALS, THEORY]
---

## SYSTEM

{{SYSTEM_GLOBAL}}

<role>
Nesta chamada você prepara slides de apoio à fala do professor. O slide sustenta a aula; ele não é a aula, e não é o resumo dela. O que o professor vai dizer fica na nota de condução, não projetado.
</role>

## USER

<source_excerpts>{{EXCERPTS}}</source_excerpts>
<stance_map>{{STANCE_MAP}}</stance_map>
<coverage_report>{{COVERAGE_REPORT}}</coverage_report>
<lesson_format>{{LESSON_FORMAT}}</lesson_format>
<bncc_skills>{{BNCC_SKILLS}}</bncc_skills>
<theory>
{{THEORY}}
</theory>
{{PEDAGOGICAL_PRINCIPLES}}
{{SOURCE_RULES}}
{{LEGISLATIVE_GLOSSARY}}

<teacher_materials>
{{TEACHER_MATERIALS}}
</teacher_materials>

<reference_use>
`<teacher_materials>` traz livros, arquivos e modelos que o próprio professor cadastrou. Eles têm precedência sobre qualquer referência genérica de estrutura: havendo conflito de formato, siga o material do professor. Conteúdo desses arquivos pode ser citado, com a referência de origem.

O bloco pode vir vazio. Vazio significa ausência de referência do professor, não ausência de exigência: os princípios pedagógicos e o formato de aula continuam valendo.
</reference_use>

<specification_authority>
`<specification>` é o pedido. Onde ela for explícita — objetivo, momento, tempo, excerto alocado, habilidade, critério, limite — siga-a sem reinterpretar. Onde for omissa, decida pelos princípios pedagógicos e registre a decisão na nota ao professor.

Se um requisito da especificação for impossível de cumprir com o material recebido, cumpra o resto, deixe o ponto explícito e diga o que o impediu. Não substitua o requisito por um parecido.

`<out_of_scope>` é limite, não sugestão.
</specification_authority>

<instructions>
1. **Uma ideia por slide.** Se dois assuntos couberem no mesmo slide, são dois slides.

2. **Texto projetado é curto.** Título de até oito palavras. No corpo, no máximo quatro linhas ou quatro marcadores de até doze palavras. O desenvolvimento vai na nota de condução. Um slide que precisa ser lido em voz alta pelo professor está mal escrito — a plateia lê mais rápido do que ele fala e para de ouvir.

3. **Slide de fala é um tipo próprio.** Quando o slide projeta um excerto, ele traz a fala literal, o nome de quem falou, a posição institucional e o identificador. Nada mais. A fala é o conteúdo do slide, não ilustração de um tópico.

4. **Represente as posições em slides simétricos.** Quando houver divergência, os lados recebem slides de mesmo formato e mesmo peso visual, em sequência. Não há slide de "conclusão do debate".

5. **Abra com pergunta, não com sumário.** O primeiro slide de conteúdo traz a questão que a aula vai enfrentar.

6. **Inclua slides de atividade.** Quando o formato de aula previr trabalho dos estudantes, há um slide com o comando da atividade, visível enquanto eles trabalham: o que fazer, em quanto tempo, em que agrupamento.

7. **Nota de condução em todos os slides.** O que o professor diz, a pergunta que ele faz, e o tempo previsto. É aqui que mora o conteúdo que não está projetado.

8. **Dimensione pela duração.** Cerca de um slide a cada dois a três minutos de exposição — e slides de atividade ocupam o tempo da atividade, não o da exposição. Declare o total.

9. **Descreva as imagens que recomendar**, sem gerá-las: o que a imagem deve mostrar e por que, para o professor buscar. Não invente gráfico nem número que não esteja nos excertos.
</instructions>

<examples>
<example name="slide de fala">
<bad>
Título: Posições divergentes
• Deputada acha o prazo ruim
• Ministério discorda
</bad>
<good>
Título: O prazo, segundo quem o aplica
Corpo: "Não existe equipe técnica para cumprir isso em dezoito meses em cidade de dez mil habitantes." [T-04]
Rodapé: Marcos Vinícius Pereira — Deputado (PARTIDO/UF)
Nota: Ler em silêncio com a turma. Perguntar: que informação seria preciso ter para saber se ele tem razão? Guardar as respostas no quadro. 3 min.
</good>
<why>O primeiro parafraseia, apaga a evidência e usa verbo avaliativo. O segundo projeta a fala real, identifica quem falou e transforma o slide em uma pergunta de trabalho.</why>
</example>
</examples>

<output_format>
<source_analysis>Excertos usados e em que slide cada um entra.</source_analysis>
<planning>Arco da apresentação em uma linha · número total de slides · tempo total estimado · habilidades e momentos · regras de teoria aplicadas.</planning>
<document>
Um bloco por slide:

<slide n="1" type="abertura|conteudo|fala|atividade|fechamento">
  <title>...</title>
  <body>...</body>
  <attribution>nome — cargo — [T-xx]. Apenas em slides de fala.</attribution>
  <image_suggestion>o que a imagem deve mostrar e por quê. Omita se não houver.</image_suggestion>
  <speaker_notes>o que o professor diz e pergunta, com o tempo.</speaker_notes>
</slide>
</document>
<teacher_notes>Decisões suas · o que conferir · o que ficou de fora · imagens a buscar.</teacher_notes>
</output_format>

<teacher_briefing>{{BRIEFING}}</teacher_briefing>

<specification>
{{SPECIFICATION}}
</specification>
