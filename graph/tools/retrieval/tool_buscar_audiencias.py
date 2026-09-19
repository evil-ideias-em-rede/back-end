"""Tool de LangChain para buscar conteúdo nas audiências públicas."""

import json

from langchain_core.tools import tool

from .embeddings_index import buscar_vetorial, conectar


@tool("buscar_audiencias")
def buscar_audiencias(pergunta: str, k: int = 5) -> str:
    """Busca trechos relevantes das transcrições de audiências públicas.

    Use esta ferramenta sempre que precisar de informação factual sobre o
    que foi discutido, dito ou defendido em uma audiência. Não invente o
    conteúdo da audiência quando a busca não trouxer evidência suficiente.

    Args:
        pergunta: Pergunta ou tema em linguagem natural.
        k: Quantidade máxima de trechos retornados; padrão 5.

    Returns:
        JSON serializado com ``doc_id``, ``source``, ``ref_id``, ``distance``
        e ``trecho`` para cada resultado.

        Se precisar ler a audiência completa, os metadados ou mais texto de
        uma fala, use a tool ``consultar_audiencias_sql`` com o ``ref_id``
        retornado nesta busca.
    """
    pergunta = pergunta.strip()
    if not pergunta:
        return json.dumps({"erro": "A pergunta não pode ser vazia."}, ensure_ascii=False)

    k = max(1, min(int(k), 20))
    # LangGraph executa tools síncronas em threads do executor. Abrir a
    # conexão nesta chamada evita reutilizar uma conexão SQLite criada em
    # outra thread e também isola chamadas concorrentes do agente.
    conexao = conectar()
    try:
        resultados = buscar_vetorial(conexao, pergunta, k=k, source="audiencia")
        return json.dumps(resultados, ensure_ascii=False)
    finally:
        conexao.close()
