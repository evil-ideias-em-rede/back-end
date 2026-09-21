"""
Ponto de entrada: busca os discursos de um deputado num intervalo de datas
e exibe tudo formatado no terminal.

Rode com: python3 -m deputados.discursos_cli
"""

from .api_camara import get_deputado_por_nome
from ..montagem import montar_registros
from .exibicao import exibir_registros


def main():
    nome_deputado = "Airton Faleiro"
    data_inicio = "2000-08-01"
    data_fim = "2026-08-25"

    resultado = get_deputado_por_nome(nome_do_deputado=nome_deputado)
    dados = resultado.get("dados") or []
    if not dados:
        print(f"Nenhum deputado encontrado com o nome '{nome_deputado}'.")
        return

    dep = dados[0]
    id_deputado = dep["id"]
    nome_deputado = dep["nome"]
    uf = dep.get("siglaUf")
    sigla_partido = dep.get("siglaPartido")
    url_foto = dep.get("urlFoto")
    email = dep.get("email")

    registros = montar_registros(id_deputado, nome_deputado, data_inicio, data_fim)
    exibir_registros(registros, nome_deputado, sigla_partido, uf, email, url_foto, id_deputado)


if __name__ == "__main__":
    main()
