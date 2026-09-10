import os
import json
import asyncio
from langchain_core.tools import tool
from .workdir import _extrai_sandbox_dir
from .format_planning import format_planning_file
from .config_sandbox import _montar_comando_sandboxed
from langchain_core.runnables import RunnableConfig


def _format_warning(work_dir: str) -> str:
    error = format_planning_file(work_dir)
    return f"\nNão foi possível formatar planning.json automaticamente: {error}" if error else ""


@tool
async def execute_bash(comando: str, config: RunnableConfig) -> str:
    """
    Executa um comando shell restrito ao diretório de trabalho do projeto
    e retorna o resultado estruturado. Você pode usar para criar codigo python para 
    manipular CSVs através de comando bash ou usar comandos bash em geral.

    Para gerar PDFs, escreva um script Python usando a biblioteca
    reportlab e execute-o com esta mesma ferramenta (não existe uma
    ferramenta separada para PDF). O módulo `pdf_helpers.py` já está
    disponível para import (cuida de tipografia, tabelas, cores e rodapé
    numerado) — consulte a skill "geracao_pdf.md" para o fluxo recomendado
    e exemplos antes de escrever o script do zero. Aém disso, você também pode usar
    a biblioteca matplotlib para gerar gráficos e salvar como imagens, que podem
    ser incluídas no PDF.
    Também é possível gerar slides com a biblioteca "pptxgenjs" como descrito na skill "geracao_slide.md".

    Args:
        comando (str): Comando a ser executado no shell (ex: "ls -la", echo "print('Python rodando!)" > teste.py, python3 teste.py).

    Returns:
        str: JSON com:
        {
            "stdout": str,
            "stderr": str,
            "returncode": int,
            "sucesso": bool
        }
    """

    if not isinstance(comando, str) or not comando.strip():
        return json.dumps(
            {
                "stdout": "",
                "stderr": "O comando deve ser uma string não vazia",
                "returncode": -1,
                "sucesso": False,
            },
            ensure_ascii=False,
        )

    try:
        work_dir = await _extrai_sandbox_dir(config)
    except (ValueError, RuntimeError) as e:
        return json.dumps({"stdout": "", "stderr": str(e), "returncode": -1, "sucesso": False}, ensure_ascii=False,)
    
    try:
        comando_sandbox = _montar_comando_sandboxed(comando, work_dir)
        processo = await asyncio.create_subprocess_exec(*comando_sandbox, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(processo.communicate(), timeout=120)
        except asyncio.TimeoutError:
            processo.kill()
            await processo.communicate()
            warning = _format_warning(work_dir)
            return json.dumps(
                {
                    "stdout": "",
                    "stderr": "Comando excedeu o tempo limite (120s)" + warning,
                    "returncode": -1,
                    "sucesso": False,
                },
                ensure_ascii=False,
            )

        resultado = {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace") + _format_warning(work_dir),
            "returncode": processo.returncode,
            "sucesso": processo.returncode == 0
        }

        return json.dumps(resultado, ensure_ascii=False)

    
    except Exception as e:
        return json.dumps(
            {"stdout": "", "stderr": str(e), "returncode": -1, "sucesso": False},
            ensure_ascii=False,
        )

'''
if __name__ == "__main__":
    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    config_teste: RunnableConfig = {"configurable": { "thread_id": "teste-usuario-123", "callbacks_sio": [] }}

    testes_bloqueio = [
    "cat ../../etc/passwd",
    "cat /etc/passwd",
    "ls /root",
    "ls /home",
    "cat ~/.ssh/id_rsa",
    "cd .. && ls",
    "ls /proc/1/environ",
    ]

    
    for cmd in testes_bloqueio:
        resultado = asyncio.run(execute_bash(config=config_teste, comando=cmd))
        print(resultado)
        status = "BLOQUEADO ✅" if not resultado["sucesso"] else "PASSOU ⚠️ FALHA DE SEGURANÇA"
        print(f"{cmd!r:40} -> {status} | stderr={resultado['stderr'][:60]}")
    

    # Prepara um arquivo que ficará disponível apenas em workdirs/<thread>/sandbox.
    csv_teste = (
        "nome,idade,cidade,curso\n"
        "Ana,21,Campina Grande,Ciência da Computação\n"
        "Bruno,25,João Pessoa,Engenharia\n"
        "Carla,19,Patos,Administração\n"
        "Diego,30,Sousa,Matemática\n"
        "Aninha,22,Campina Grande,Ciência da Computação\n"
        "Bruna,26,João Pessoa,Engenharia\n"
        "Carlos,20,Patos,Administração\n"
        "Daniela,31,Sousa,Matemática\n"
    )
    csv_literal = csv_teste.replace("'", "'\\''").replace("\n", "\\n")
    asyncio.run(execute_bash(config=config_teste, comando=f"printf '{csv_literal}' > dados_teste.csv",))

    @tool
    async def bash(comando: str) -> str:
        """Executa um comando bash no sandbox. O arquivo dados_teste.csv está disponível."""
        resultado = await execute_bash(config=config_teste, comando=comando)
        return json.dumps(resultado, ensure_ascii=False)

    async def conversar_com_llm() -> None:
        if not os.getenv("OPENAI_API_KEY"): return

        llm = ChatOpenAI(model=os.getenv("AGENT_MODEL", "gpt-5.6-luna"), reasoning={"effort": "low"},).bind_tools([bash])
        mensagens = [HumanMessage(content=(
            "Você é um analista de dados. Use a ferramenta bash quando precisar "
            "ler ou transformar dados. O arquivo dados_teste.csv está no diretório "
            "atual. Nunca tente acessar caminhos fora do sandbox."
        ))]

        print("\nAgente bash pronto. Digite uma tarefa sobre dados_teste.csv (ou 'sair').")
        while True:
            pedido = await asyncio.to_thread(input, "\nVocê> ")
            if pedido.strip().lower() in {"sair", "exit", "quit"}: break
            mensagens.append(HumanMessage(content=pedido))

            while True:
                resposta = await llm.ainvoke(mensagens)
                mensagens.append(resposta)
                chamadas = getattr(resposta, "tool_calls", [])
                if not chamadas:
                    print(f"LLM> {resposta.content[0]["text"]}")
                    break
                for chamada in chamadas:
                    argumentos = chamada.get("args", {})
                    resultado = await bash.ainvoke(argumentos)
                    mensagens.append(ToolMessage(content=resultado, tool_call_id=chamada["id"],))

    asyncio.run(conversar_com_llm())
'''
