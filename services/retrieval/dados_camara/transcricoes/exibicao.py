"""
Exibição formatada (via rich) dos discursos encontrados, incluindo os
itens de pauta que mais se relacionam com as keywords de cada discurso.
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from .montagem import pontuar_item_pauta


console = Console()
def exibir_registros(registros, nome_deputado, sigla_partido, uf, email, url_foto, id_deputado):
    if not registros:
        console.print(Panel(
            "Nenhum discurso encontrado nesse intervalo de datas.",
            title="Resultado",
            border_style="yellow",
        ))
        return

    for numero, r in enumerate(registros, start=1):
        s = r["sessao"]
        titulo = (
            f"[bold cyan]{nome_deputado}[/bold cyan] "
            f"[magenta]• {sigla_partido}[/magenta] "
            f"[green]• {uf}[/green]"
        )

        deputado_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        deputado_table.add_column("Campo", style="bold cyan", width=18)
        deputado_table.add_column("Valor")
        deputado_table.add_row("ID", str(id_deputado))
        deputado_table.add_row("Parlamentar", nome_deputado)
        deputado_table.add_row("Partido", sigla_partido or "(não informado)")
        deputado_table.add_row("UF", uf or "(não informada)")
        deputado_table.add_row("Email", email or "(não informado)")
        deputado_table.add_row("Foto", url_foto or "(não informada)")
        console.print()
        console.print(Panel(
            deputado_table,
            title=titulo,
            subtitle=f"Discurso #{numero}",
            border_style="magenta",
            padding=(1, 2),
        ))

        data_inicio = r["dataHoraInicio"]
        data_fim = r["dataHoraFim"] if r["dataHoraFim"] else "[yellow]indeterminado[/yellow]"

        discurso_table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        discurso_table.add_column("Campo", style="bold cyan", width=18)
        discurso_table.add_column("Valor")
        discurso_table.add_row("Data/Hora", f"{data_inicio} → {data_fim}")
        discurso_table.add_row("Fase", str(s["fase"] or "(não informada)"))
        discurso_table.add_row("Tipo", str(r["tipoDiscurso"] or "(não informado)"))

        if s["nuSessao"]:
            tipo_sessao = (s["tipoSessao"] or "").replace("OrdinÃ¡ria", "Ordinaria")
            sessao_txt = f"{s['nuSessao']} ({tipo_sessao})"
        else:
            sessao_txt = "[yellow]não encontrada no SITAQWeb para esse horário[/yellow]"

        discurso_table.add_row("Sessão", sessao_txt)
        if s["url_video"]:
            discurso_table.add_row(
                "Vídeo",
                f"[link={s['url_video']}]{s['url_video']}[/link]",
            )

        if r["keywords"]:
            discurso_table.add_row("Keywords", r["keywords"])
        console.print(Panel(discurso_table, title="Informações do discurso", border_style="cyan", padding=(1, 2)))

        if s["pauta"]:
            pontuados = [
                (item, pontuar_item_pauta(item["ementaRelacionada"] or item["ementa"] or "", r["keywords"] or ""))
                for item in s["pauta"]
            ]
            destaques = sorted((p for p in pontuados if p[1] > 0), key=lambda p: p[1], reverse=True)

            if destaques:
                pauta_table = Table(title="Pauta da sessão — itens relacionados", expand=True, show_lines=False)
                pauta_table.add_column("#", justify="right", width=4)
                pauta_table.add_column("Proposição", style="bold cyan", width=25)
                pauta_table.add_column("Match", justify="center", width=12)
                pauta_table.add_column("Ementa / Tema")

                for pos, (item, pontos) in enumerate(destaques[:5], start=1):
                    alvo = item["proposicaoRelacionada"] or item["proposicao"] or "(sem proposição vinculada)"
                    tema = item["ementaRelacionada"] or item["ementa"] or "(sem ementa)"
                    pauta_table.add_row(str(pos), alvo, f"[green]{pontos} termo(s)[/green]", tema)

                console.print(Panel(pauta_table, border_style="blue", padding=(1, 1)))

                if len(destaques) > 5:
                    console.print(
                        f"[dim]... e mais {len(destaques) - 5} item(ns) "
                        f"com alguma palavra-chave em comum.[/dim]"
                    )
            else:
                console.print(Panel(
                    f"[yellow]{len(pontuados)} item(ns) previstos, "
                    f"nenhum bateu com as keywords do discurso.[/yellow]",
                    title="Pauta da sessão",
                    border_style="yellow",
                ))
        else:
            console.print(Panel(
                "[yellow]Nenhum item encontrado / evento não localizado.[/yellow]",
                title="Pauta da sessão",
                border_style="yellow",
            ))

        if r["sumario"]:
            console.print(Panel(r["sumario"], title="Sumário", border_style="blue", padding=(1, 2)))

        fala = r["fala"] or ""
        fala_exibida = fala + "..." if len(fala) > 1000 else fala
        console.print(Panel(fala_exibida, title=f"Fala • fonte: {r['fala_fonte']}", border_style="green", padding=(1, 2)))
        console.rule(f"[bold]Discurso #{numero}[/bold]", style="dim")
