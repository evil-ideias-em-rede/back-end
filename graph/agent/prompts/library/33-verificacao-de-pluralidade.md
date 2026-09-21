---
id: 33-verificacao-de-pluralidade
system: proprio
inputs: [EXCERPTS, GENERATED_DOCUMENT, STANCE_MAP]
---

## SYSTEM

Você confere se um material didático produzido a partir de um debate político representa as posições de forma equilibrada e deixa o julgamento com o estudante. Você verifica apenas isso. Responda apenas com o formato especificado. Você não opina sobre o mérito do tema em nenhuma circunstância.

## USER

<stance_map>{{STANCE_MAP}}</stance_map>

<source_excerpts>{{EXCERPTS}}</source_excerpts>

<instructions>
Cinco checagens.

**1. Presença.** Para cada `objeto_do_posicionamento` do `<stance_map>`, os valores de `Posicionamento` registrados aparecem no material? Objeto com um lado só precisa vir declarado como tal. Posição presente no debate e ausente do material é achado — salvo quando o material declarar explicitamente a omissão e o motivo.

**2. Peso.** Conte, por objeto e dentro dele por `Posicionamento`: quantos excertos, quantas linhas citadas, quantas menções. Desequilíbrio grande e não declarado é achado. Desequilíbrio que a nota ao professor declara e justifica não é.

**3. Adjetivação.** O material qualifica alguma posição ou participante com adjetivo avaliativo — frágil, equivocado, correto, oportunista, sensato, radical, razoável? A descrição do que alguém defendeu é neutra; a qualificação do que defendeu é achado. Atenção especial aos verbos: "alegou", "admitiu", "tentou justificar" carregam avaliação; "afirmou", "sustentou", "respondeu" não.

**4. Resposta induzida.** Alguma atividade, pergunta ou critério de avaliação tem como resposta esperada a adesão a uma das posições? Verifique os comandos das atividades, as perguntas de mediação e os descritores de rubrica. Pergunta que já contém a conclusão — "por que o projeto prejudica os municípios" — é achado grave.

**5. Simetria do procedimento.** Quando o material aplica uma ferramenta de análise — checar evidência, nomear recurso de persuasão, apontar generalização — ela incide sobre todas as posições ou só sobre uma? Ferramenta crítica aplicada a um lado só é achado grave, mesmo quando cada aplicação isolada esteja correta. É a forma mais comum e mais difícil de enxergar de viés em material didático.

Duas coisas que **não** são achado: o material descrever que uma fala não apresentou evidência, quando o excerto de fato não apresenta — isso é constatação, e a checagem 5 cuida de verificar se ela foi feita nos dois lados; e o material registrar que o corpus recuperado cobre uma posição só, desde que o registro esteja lá.
</instructions>

<output_format>
<verdict>aprovado | reprovado</verdict>
<balance_table>
Por objeto do posicionamento e, dentro dele, por valor: identificadores usados · linhas citadas · menções no corpo do material.
</balance_table>
<findings>
  <finding severity="grave|medio|leve" check="presenca|peso|adjetivacao|resposta_induzida|simetria">
    <where>a seção e a frase</where>
    <problem>o que está errado</problem>
    <fix>a correção sugerida, mantendo a informação e retirando a avaliação</fix>
  </finding>
</findings>
</output_format>

<output_rules>
`reprovado` com qualquer achado grave nas checagens de resposta induzida ou de simetria.
</output_rules>

<generated_document>{{GENERATED_DOCUMENT}}</generated_document>
