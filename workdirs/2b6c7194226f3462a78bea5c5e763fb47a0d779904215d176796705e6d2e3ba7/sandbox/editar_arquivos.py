import json
from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from graph.tools.sandbox.workdir import _extrai_sandbox_dir


def _erro(msg: str) -> str:
    return json.dumps({"sucesso": False, "erro": msg}, ensure_ascii=False)


def _resolver_caminho(sandbox_dir: str, caminho: str) -> Path:
    """Resolve `caminho` dentro do sandbox_dir, bloqueando qualquer tentativa de escapar dele."""
    base = Path(sandbox_dir).resolve()
    bruto = Path(caminho)
    alvo = bruto.resolve() if bruto.is_absolute() else (base / bruto).resolve()
    try:
        alvo.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Caminho fora do sandbox permitido: {caminho}") from exc
    return alvo


@tool
async def visualizar_arquivo(caminho: str, config: RunnableConfig, intervalo_linhas: list[int] | None = None) -> str:
    """
    Mostra o conteúdo de um arquivo de texto do sandbox, numerando as linhas, ou lista os
    arquivos de um diretório. Use SEMPRE antes de `editar_arquivo`, para conferir o texto
    exato (espaços, indentação e quebras de linha) que vai em `texto_antigo`.

    Args:
        caminho (str): Caminho relativo ao sandbox (ex: "dados.py", "saida/relatorio.csv").
            Use "." para listar a raiz do sandbox.
        intervalo_linhas (list[int], opcional): [linha_inicio, linha_fim] (1-indexado) para
            ver só um trecho do arquivo. Use linha_fim = -1 para ir até o final.

    Returns:
        str: JSON com:
        {
            "sucesso": bool,
            "erro": str,
            "tipo": "arquivo" | "diretorio",
            "conteudo": str,        # presente quando tipo == "arquivo"
            "entradas": list[str],  # presente quando tipo == "diretorio"
        }
    """
    try:
        sandbox_dir = await _extrai_sandbox_dir(config)
    except (ValueError, RuntimeError) as e:
        return _erro(str(e))

    try:
        alvo = _resolver_caminho(sandbox_dir, caminho)
    except ValueError as e:
        return _erro(str(e))

    if not alvo.exists():
        return _erro(f"Caminho não encontrado: {caminho}")

    if alvo.is_dir():
        try:
            entradas = sorted(
                (f"{p.name}/" if p.is_dir() else p.name)
                for p in alvo.iterdir()
                if not p.name.startswith(".")
            )
        except OSError as e:
            return _erro(str(e))
        return json.dumps(
            {"sucesso": True, "erro": "", "tipo": "diretorio", "entradas": entradas},
            ensure_ascii=False,
        )

    try:
        texto = alvo.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return _erro(str(e))

    linhas = texto.split("\n")
    inicio, fim = 1, len(linhas)
    if intervalo_linhas:
        inicio = max(1, intervalo_linhas[0])
        fim = len(linhas) if intervalo_linhas[1] == -1 else min(len(linhas), intervalo_linhas[1])

    numeradas = "\n".join(f"{i}\t{linhas[i - 1]}" for i in range(inicio, fim + 1))
    return json.dumps(
        {"sucesso": True, "erro": "", "tipo": "arquivo", "conteudo": numeradas},
        ensure_ascii=False,
    )


@tool
async def editar_arquivo(caminho: str, texto_antigo: str, texto_novo: str, config: RunnableConfig) -> str:
    """
    Edita um arquivo já existente no sandbox substituindo UM trecho único por outro — sem
    reescrever o arquivo inteiro. Prefira sempre esta ferramenta a reescrever o arquivo todo
    via bash: você só manda a parte que muda, e o resto do arquivo fica intocado.

    `texto_antigo` precisa casar exatamente (espaços e quebras de linha incluídos) com UMA
    única ocorrência no arquivo. Se casar zero vezes ou mais de uma vez, a edição é recusada
    e nada é alterado — nesse caso, use `visualizar_arquivo` para conferir o texto exato e
    inclua mais contexto ao redor até o trecho ficar único. Para apagar um trecho, passe
    texto_novo="".

    Args:
        caminho (str): Caminho relativo ao sandbox do arquivo a editar.
        texto_antigo (str): Texto exato a localizar (deve ser único no arquivo).
        texto_novo (str): Texto que substitui texto_antigo.

    Returns:
        str: JSON com {"sucesso": bool, "erro": str, "ocorrencias": int}
    """
    try:
        sandbox_dir = await _extrai_sandbox_dir(config)
    except (ValueError, RuntimeError) as e:
        return _erro(str(e))

    try:
        alvo = _resolver_caminho(sandbox_dir, caminho)
    except ValueError as e:
        return _erro(str(e))

    if not alvo.is_file():
        return _erro(f"Arquivo não encontrado: {caminho}")

    try:
        conteudo = alvo.read_text(encoding="utf-8")
    except OSError as e:
        return _erro(str(e))
    except UnicodeDecodeError:
        return _erro("Arquivo não é texto UTF-8 válido; edição de binários não é suportada")

    ocorrencias = conteudo.count(texto_antigo)
    if ocorrencias == 0:
        return json.dumps(
            {"sucesso": False, "erro": "texto_antigo não encontrado no arquivo", "ocorrencias": 0},
            ensure_ascii=False,
        )
    if ocorrencias > 1:
        return json.dumps(
            {
                "sucesso": False,
                "erro": "texto_antigo aparece mais de uma vez; inclua mais contexto para torná-lo único",
                "ocorrencias": ocorrencias,
            },
            ensure_ascii=False,
        )

    novo_conteudo = conteudo.replace(texto_antigo, texto_novo, 1)
    try:
        alvo.write_text(novo_conteudo, encoding="utf-8")
    except OSError as e:
        return _erro(str(e))

    return json.dumps({"sucesso": True, "erro": "", "ocorrencias": 1}, ensure_ascii=False)


@tool
async def criar_arquivo(caminho: str, conteudo: str, config: RunnableConfig) -> str:
    """
    Cria um arquivo novo no sandbox com o conteúdo dado. Falha se o arquivo já existir — use
    `editar_arquivo` para modificar um arquivo existente, ou apague-o antes via `execute_bash`
    se realmente quiser substituí-lo por completo.

    Args:
        caminho (str): Caminho relativo ao sandbox do novo arquivo (pastas intermediárias são
            criadas automaticamente).
        conteudo (str): Conteúdo textual do arquivo.

    Returns:
        str: JSON com {"sucesso": bool, "erro": str}
    """
    try:
        sandbox_dir = await _extrai_sandbox_dir(config)
    except (ValueError, RuntimeError) as e:
        return _erro(str(e))

    try:
        alvo = _resolver_caminho(sandbox_dir, caminho)
    except ValueError as e:
        return _erro(str(e))

    if alvo.exists():
        return _erro(f"Arquivo já existe: {caminho}")

    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(conteudo, encoding="utf-8")
    except OSError as e:
        return _erro(str(e))

    return json.dumps({"sucesso": True, "erro": ""}, ensure_ascii=False)
