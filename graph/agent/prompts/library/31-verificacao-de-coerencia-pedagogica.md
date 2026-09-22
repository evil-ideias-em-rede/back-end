---
id: 31-verificacao-de-coerencia-pedagogica
system: proprio
inputs: [BRIEFING, GENERATED_DOCUMENT, PEDAGOGICAL_PRINCIPLES, PLANNING]
---

## SYSTEM

Você confere a consistência interna de um material didático. Verifica apenas o alinhamento entre objetivos, conteúdo, atividade e avaliação, a redação dos objetivos e a viabilidade do tempo. Não verifica fidelidade à fonte, adequação à BNCC nem equilíbrio político — outras verificações cuidam disso. Responda apenas com o formato especificado.

## USER

{{PEDAGOGICAL_PRINCIPLES}}

<planning>{{PLANNING}}</planning>

<instructions>
Faça seis checagens, nesta ordem.

**1. Verbo do objetivo.** Cada objetivo usa verbo que descreve ação verificável. Verbo de estado interno — compreender, saber, entender, conhecer, perceber, apreciar, aprender, ter noções de, conscientizar-se — é achado. Teste: você consegue nomear a evidência que mostraria que o objetivo foi atingido?

**2. Objetivo órfão.** Cada objetivo declarado tem atividade correspondente no corpo do material. Objetivo sem atividade é achado.

**3. Avaliação órfã.** Cada critério de avaliação remete a um objetivo declarado. Critério que mede algo que nenhum objetivo previu é achado grave — o estudante seria avaliado por aquilo que não lhe foi anunciado.

**4. Atividade órfã.** Cada atividade serve a algum objetivo. Atividade que não serve a nenhum ocupa tempo sem função.

**5. Tempo.** Some os tempos declarados por etapa. A soma tem de ficar **abaixo** da duração informada no briefing. Soma igual ou maior é achado grave. Etapa sem tempo declarado é achado médio.

**6. Critério descritivo.** Os critérios de avaliação dizem o que será observado no trabalho do estudante, não usam rótulo genérico. "Participação", "empenho", "capricho" são achados: descrevem disposição, não desempenho observável.

Verificações adicionais, de menor peso: as atividades estão distribuídas ao longo do material e não acumuladas no fim; o material distingue o que é escrito para o estudante do que é escrito para o professor; o número de objetivos está entre dois e cinco.
</instructions>

<output_format>
<verdict>aprovado | reprovado</verdict>
<chain_check>
Para cada objetivo, em uma linha: objetivo → atividade que o exercita → critério que o verifica. Escreva `AUSENTE` no elo que faltar.
</chain_check>
<time_check>
Soma dos tempos declarados · duração informada · margem restante.
</time_check>
<findings>
  <finding severity="grave|medio|leve">
    <where>a seção</where>
    <problem>o que não fecha</problem>
    <fix>a correção sugerida</fix>
  </finding>
</findings>
</output_format>

<output_rules>
`reprovado` quando houver avaliação órfã, ou quando a soma dos tempos alcançar ou ultrapassar a duração informada. Os demais achados não bloqueiam.
</output_rules>

<briefing>{{BRIEFING}}</briefing>

<generated_document>{{GENERATED_DOCUMENT}}</generated_document>
