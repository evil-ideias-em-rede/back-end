"""Orquestração do ETL: percorre os deputados e persiste tudo, com retomada via checkpoint."""

from .banco import abrir_banco
from .carregamento import carregar_audiencias_publicas, carregar_deputados
from .config import SQLITE_PATH
from .organizacao_partidaria import montar_falas_por_partido
from .persistencia import inserir_deputado, inserir_registros


def imprimir_valor(valor, nivel=0, nome=None):
    """Imprime qualquer estrutura, truncando strings em 100 caracteres."""
    indentacao = "  " * nivel
    prefixo = f"{nome}: " if nome is not None else ""

    if isinstance(valor, dict):
        #print(f"{indentacao}{prefixo}{{")
        for chave, item in valor.items():
            imprimir_valor(item, nivel + 1, chave)
        #print(f"{indentacao}}}")
    elif isinstance(valor, (list, tuple)):
        #print(f"{indentacao}{prefixo}[")
        for indice, item in enumerate(valor):
            imprimir_valor(item, nivel + 1, f"[{indice}]")
        #print(f"{indentacao}]")
    elif isinstance(valor, str):
        texto = valor.replace("\n", "\\n")
        if len(texto) > 100:
            texto = texto[:100] + "... [texto truncado]"
        #print(f"{indentacao}{prefixo}{texto!r}")
    else: 
        pass #print(f"{indentacao}{prefixo}{valor!r}")


def imprimir_resultado(deputado, historico, registros):
    """Exibe os resultados sem depender da estrutura do JSON."""
    def limitar_textos(valor):
        if isinstance(valor, dict):
            return {chave: limitar_textos(item) for chave, item in valor.items()}
        if isinstance(valor, list):
            return [limitar_textos(item) for item in valor]
        if isinstance(valor, tuple):
            return [limitar_textos(item) for item in valor]
        if isinstance(valor, str):
            return valor[:100] + ("... [texto truncado]" if len(valor) > 100 else "")
        return valor

    """
    caminho_json = SQLITE_PATH.parent / "resultado_impressao.json"
    dados = {"deputado": deputado, "historico": historico, "registros": registros}
    with open(caminho_json, "w", encoding="utf-8") as arquivo:
        import json
        json.dump(limitar_textos(dados), arquivo, ensure_ascii=False, indent=2)
    """
    """
    
    print("\n" + "=" * 80)
    imprimir_valor(deputado, nome="deputado")
    imprimir_valor(historico, nome="historico")
    imprimir_valor(registros, nome="registros")
    print("=" * 80)
    """


def imprimir_processado(db, deputado):
    """Imprime novamente um deputado já salvo no SQLite."""
    colunas = ["id", "deputado_id", "filiacao_id", "data_hora_inicio",
               "tipo_discurso", "fase", "nu_sessao",
               "tipo_sessao", "url_video", "url_texto_integral", "sumario",
               "transcricao", "fala", "fala_fonte", "keywords_raw"]
    linhas = db.execute(
        "SELECT " + ", ".join(colunas) +
        " FROM discursos WHERE deputado_id=? ORDER BY data_hora_inicio",
        (deputado["id"],),
    ).fetchall()
    registros = [dict(zip(colunas, linha)) for linha in linhas]
    print("\nDeputado já processado — dados recuperados do SQLite:")
    imprimir_resultado(deputado, [], registros)


def main():
    deputados = carregar_deputados()
    audiencias_publicas = carregar_audiencias_publicas()
    db = abrir_banco()
    ids_salvos = {r[0] for r in db.execute("SELECT deputado_id FROM etl_processados")}
    print(f"Retomando: {len(ids_salvos)} deputado(s) já salvo(s).")

    for deputado in deputados:
        if deputado["id"] in ids_salvos:
            imprimir_processado(db, deputado)
            print(f"{deputado['nome']}: já processado, pulando nova busca.")
            continue

        inserir_deputado(db, deputado)
        historico = montar_falas_por_partido(deputado, audiencias_publicas)
        registros = [r for p in historico for r in p["discursos"]]
        imprimir_resultado(deputado, historico, registros)
        inserir_registros(db, deputado, registros)
        db.execute("INSERT INTO etl_processados (deputado_id) VALUES (?)", (deputado["id"],))
        db.commit()

        total_falas = len(registros)
        ids_salvos.add(deputado["id"])
        print(f"{deputado['nome']}: {total_falas} discurso(s). Checkpoint salvo ({len(ids_salvos)}/{len(deputados)}).")
        # break

    db.close()
    print(f"\nBanco SQLite salvo em: {SQLITE_PATH}")


if __name__ == "__main__":
    main()
