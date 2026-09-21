# Gabarito de avaliação do recuperador

## Decisão final de estratégia (2026-09-17)

`buscar_vetorial()` (`../embeddings_index.py`) é a busca padrão do
recuperador — venceu o BM25 puro (`../fts_index.py buscar`) por larga
margem no gabarito `manual`, que imita pergunta de usuário real sobre o
tema de uma audiência (hit@10 0.955 vs 0.727, MRR 0.727 vs 0.481, n=22).
O BM25 só vence no gabarito `gold`, cujas perguntas são paráfrase de UMA
fala específica com vocabulário quase literal do texto original — cenário
que não representa como um usuário de verdade pergunta. `buscar_hibrido`
(BM25 + vetorial via RRF) e o rerank em `../reranker.py` (LLM ou
embeddings sobre candidatos do BM25) foram testados como alternativas mas
nenhum bateu o vetorial puro no gabarito `manual`; ficam no código como
comparação, não como caminho padrão.

Rodar `python eval_fts.py manual --k 10 --estrategia <bm25|vetorial|hibrido|rerank-llm|rerank-embeddings>`
reproduz a comparação (ver `logs/` pros resultados já gravados).

## Gabaritos

Gabarito gold, pra alimentar o `eval_fts.py` (hit@k / coverage@k / MRR):

```json
{
  "id": "string única",
  "pergunta": "string",
  "doc_ids_esperados": ["audiencia:123:chunk:4"],
  "source_esperada": "audiencia",
  "origem_gabarito": "gold_nli",
  "metadata": {"...": "contexto pra auditoria manual"}
}
```

## Gerar

```
python montar_gabarito.py gold-audiencias     # gabaritos/gabarito_audiencias_gold.jsonl
python montar_gabarito.py manual-audiencias   # gabaritos/gabarito_audiencias_manual.jsonl
```

Requer o índice já populado (`../fts_index.py popular-public-hearing`) — o
gold usa os intervalos de parágrafo gravados na tabela `documentos` pra
descobrir quais chunks cobrem o trecho de cada opinião.

**gold_nli**: pergunta = `opiniao` extraída de `PublicHearingBR_NLI.jsonl`;
resposta = chunks cujo intervalo de parágrafo cobre o(s) `chunks_proximos`
daquela opinião. Descarta automaticamente: opiniões com
`verificacao_manual: true` (sinalizadas como alucinação na checagem manual
do dataset) e opiniões cujos `chunks_proximos` não foram localizáveis por
substring na transcrição — acontece quando o LLM que gerou o dataset
resumiu falas intercaladas de mais de um orador (ex.: uma interrupção no
meio da fala), caso em que o trecho "quase-verdade" não corresponde a
nenhum intervalo contíguo de parágrafos.

**manual**: pergunta escrita à mão em
`gabaritos/perguntas_audiencias_manual.jsonl` (`{"audiencia_id", "pergunta"}`),
a partir das candidatas em `gabaritos/candidatos_audiencias_manual.txt`
(gerado por `gerar_candidatos_audiencias.py`). Diferente do gold, a
pergunta é uma paráfrase realista do tema geral da audiência — não deriva
de um trecho literal da transcrição — então a resposta esperada é todo
chunk indexado daquela audiência. Mede se o FTS acha a audiência certa a
partir de uma pergunta de usuário real, não de keywords que já estão no
texto.
