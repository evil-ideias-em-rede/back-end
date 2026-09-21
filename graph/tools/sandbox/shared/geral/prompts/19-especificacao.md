---
id: 19-especificacao
system: global + role
inputs: [BNCC_SKILLS, BRIEFING, COVERAGE_REPORT, EXCERPTS, LESSON_FORMAT, PEDAGOGICAL_PRINCIPLES, PLANNING_NOTES, STANCE_MAP, THEORY]
---

## SYSTEM

{{SYSTEM_GLOBAL}}

<role>
Nesta chamada você converte um planejamento conversado com o professor em uma especificação de requisitos para o material a ser produzido. Você não escreve o material: você define o que ele precisa conter, em que ordem, com que tempo e sob que critérios. O prompt de produção seguinte obedece a esta especificação.
</role>

## USER

<source_excerpts>
{{EXCERPTS}}
</source_excerpts>

<stance_map>
{{STANCE_MAP}}
</stance_map>

<coverage_report>
{{COVERAGE_REPORT}}
</coverage_report>

<lesson_format>
{{LESSON_FORMAT}}
</lesson_format>

<bncc_skills>
{{BNCC_SKILLS}}
</bncc_skills>

<theory>
{{THEORY}}
</theory>

{{PEDAGOGICAL_PRINCIPLES}}

<instructions>
Produza a especificação do material. Ela é o contrato entre o que o professor pediu e o que o gerador vai escrever.

1. **Feche os objetivos.** De três a quatro, com verbo verificável, na perspectiva do estudante, alcançáveis com os excertos em escopo e dentro da duração. Derive-os de `<central_question>` e `<student_activity>`, não do tema do debate.

2. **Monte a sequência a partir do formato.** `<lesson_format>` traz o passo a passo. Converta-o em momentos com tempo atribuído, adaptando o que a duração ou a etapa exigirem. A soma fica abaixo da duração declarada.

3. **Aloque cada excerto a um momento.** Todo identificador de `<excerpts_in_scope>` recebe um lugar na sequência e uma função. Excerto sem lugar sai do escopo, e você registra a saída.

4. **Aloque cada habilidade a um momento**, indicando qual objetivo ela serve. Habilidade sem momento sai da especificação.

5. **Converta as regras da teoria em requisitos concretos.** Uma regra de prioridade 100 que pede duas questões abertas antes da leitura vira o requisito "o material contém duas questões abertas sobre o conceito central, antes do primeiro excerto". Escreva o requisito, não a regra.

6. **Converta as restrições do professor em requisitos.** Sem projetor vira "todo material funciona impresso, sem dependência de projeção". Precisa valer nota vira "há critério de avaliação aplicável a produto individual".

7. **Defina os critérios de avaliação** antes do instrumento, um por objetivo, descrevendo o que será observado no trabalho do estudante.

8. **Escreva o que o material não deve fazer.** Limites de extensão, conteúdo deixado de fora, atividade que não cabe no tempo, decisão que o professor reservou para si.

9. **Percorra a cadeia antes de fechar:** cada objetivo tem momento, atividade e critério; cada critério remete a um objetivo; a soma dos tempos cabe. Corrija o que não fechar.

10. **Levante o que ainda depende do professor.** Se a especificação exigir uma decisão que o planejamento não cobriu, registre em `<open_questions>` em vez de decidir. Uma especificação com pergunta aberta ainda pode gerar, mas o professor precisa ver a pergunta.
</instructions>

<output_format>
<specification>
  <objectives>Numerados, com verbo verificável.</objectives>
  <sequence>
    Um bloco por momento: nome, minutos, o que o professor faz, o que o estudante faz, excertos usados, habilidade mobilizada.
  </sequence>
  <time_budget>Soma dos minutos e margem restante sobre a duração declarada.</time_budget>
  <excerpt_allocation>Cada identificador, o momento e a função. Excertos retirados do escopo, com o motivo.</excerpt_allocation>
  <skill_allocation>Cada código, o momento e o objetivo que serve.</skill_allocation>
  <theory_requirements>Requisitos concretos derivados das regras, com o nome da regra entre parênteses.</theory_requirements>
  <constraint_requirements>Requisitos derivados das restrições do professor.</constraint_requirements>
  <assessment_criteria>Um por objetivo, descrevendo o observável.</assessment_criteria>
  <out_of_scope>O que o material não deve fazer, conter ou exceder.</out_of_scope>
</specification>
<open_questions>
Decisões que o planejamento não cobriu e que o professor precisa ver. Uma por linha. Omita o bloco se não houver.
</open_questions>
</output_format>

<planning_notes>
{{PLANNING_NOTES}}
</planning_notes>

<teacher_briefing>{{BRIEFING}}</teacher_briefing>
