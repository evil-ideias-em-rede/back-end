---
id: 12-consulta-ao-rag
system: proprio
inputs: [BRIEFING, DEBATE_METADATA, LEGISLATIVE_GLOSSARY, PREVIOUS_QUERIES]
---

## SYSTEM

Você formula consultas para um índice semântico de transcrições de audiências públicas da Câmara dos Deputados. A busca é por similaridade de sentido, não por casamento de termos. Responda apenas com o objeto JSON especificado, sem comentário, sem markdown, sem cerca de código.

## USER

<debate_metadata>
{{DEBATE_METADATA}}
</debate_metadata>

{{LEGISLATIVE_GLOSSARY}}

<previous_queries>
{{PREVIOUS_QUERIES}}
</previous_queries>

<scope>
O debate já foi escolhido pelo professor. As consultas abaixo recuperam falas **dentro do debate escolhido** e nos documentos associados a ele.

Quando `debate_metadata` vier vazio, a busca opera sobre o corpus inteiro e os filtros passam a ser o único recorte.
</scope>

<instructions>
Escreva de **seis a dez** consultas. O conjunto precisa cobrir quatro frentes; distribua as consultas entre elas.

**Frente 1 — o tema em linguagem comum.** Como o professor e o estudante nomeiam o assunto.

**Frente 2 — o tema em linguagem legislativa.** Como o assunto é nomeado em plenário e em comissão: nome do projeto, termo técnico do setor, nome de política pública ou programa. O índice guarda o vocabulário da transcrição. Um debate sobre lixo aparece como resíduos sólidos; um sobre internet nas escolas, como conectividade ou inclusão digital.

**Frente 3 — as duas posições.** Consultas que alcancem a sustentação favorável **e** consultas que alcancem a contrária, com os termos e o enquadramento que cada lado tipicamente emprega. Esta frente é obrigatória e nunca fica vazia. Se você só consegue imaginar como um lado se expressa, o conjunto está enviesado: pare e formule o oposto.

**Frente 4 — evidência e controvérsia.** Consultas que alcancem dado, estudo citado, prazo, custo e divergência explícita entre participantes.

Regras de escrita:

Cada consulta é uma **frase afirmativa de cinco a quinze palavras**, como alguém enunciaria a ideia. Enunciados, não palavras soltas.

Nenhuma consulta contém adjetivo avaliativo. Busque "argumentos contrários ao prazo de implementação", não "críticas ao projeto ruim".

Nenhuma consulta carrega a resposta. "Por que o projeto prejudica os municípios" recupera apenas o que confirma a premissa.

Se duas frases recuperariam o mesmo trecho, reescreva uma delas para outro ângulo.

Quando `previous_queries` vier preenchido, não repita o que já foi tentado: ataque o que ficou faltando e diga em `rationale` o que mudou.

Preencha os filtros apenas com o que o briefing e os metadados sustentam. Não invente número de projeto, nome de comissão nem recorte de data.
</instructions>

<output_schema>
{
  "queries": [
    {
      "text": "frase de cinco a quinze palavras",
      "frente": 1 | 2 | 3 | 4,
      "lado": "favoravel" | "contrario" | "neutro",
      "intencao": "o que esta consulta procura, em até dez palavras"
    }
  ],
  "filters": {
    "debate_id": "string | null",
    "comissao": "string | null",
    "periodo": "string | null",
    "projeto_de_lei": "string | null",
    "posicionamento": "Favorável | Contrário | Neutro | Ambíguo | null",
    "credibilidade": "Autoridade Própria | Referência Externa | Recursos Retóricos | null",
    "objeto_do_posicionamento": "string | null"
  },
  "rationale": "duas linhas, dizendo como o conjunto cobre as quatro frentes e os dois lados",
  "expansion_note": "string | null, o que tentar se esta rodada devolver pouco"
}
</output_schema>

<output_rules>
Ao menos uma consulta com `lado: "favoravel"` e ao menos uma com `lado: "contrario"`. Um conjunto que não atenda a isso está malformado.
O filtro `posicionamento` só é preenchido quando a consulta se destinar explicitamente a completar um lado ausente do conjunto já recuperado. As quatro dimensões da taxonomia admitem mais de um valor por fala, então um filtro nelas restringe, mas não isola.
</output_rules>

<briefing>{{BRIEFING}}</briefing>
