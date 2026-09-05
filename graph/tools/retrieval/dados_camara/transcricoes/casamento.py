"""
Lógica de casamento entre um discurso e o evento de Plenário (sessão) em
que ele realmente aconteceu.
"""

from .datas import para_datetime


def evento_cobre_horario(evento, momento):
    """
    True se 'momento' (datetime do discurso) cai dentro da janela do
    evento. Isso é mais preciso que casar só por DATA: no mesmo dia pode
    haver mais de um evento de Plenário (ex.: uma Sessão Solene de
    homenagem de manhã e a Sessão Deliberativa à tarde) -- casar pelo
    horário garante que a pauta buscada é da sessão em que o discurso
    realmente aconteceu, e não de uma solenidade sem relação com a fala.

    Como tratamos os campos que a Câmara às vezes deixa vazios:
      - Falta dataHoraInicio -> não dá pra saber quando o evento
        começou, então ele é excluído (não casa com nada). Na prática
        isso nem chega a acontecer aqui: eventos sem dataHoraInicio já
        ficam fora do agrupamento por data lá em montar_registros, então
        nunca entram como candidato.
      - Tem dataHoraInicio mas falta dataHoraFim (sessão ainda em
        andamento, ou a Câmara não fechou o registro) -> a janela fica
        ABERTA a partir do início (momento >= inicio). NÃO colapsa pra
        um instante só -- se colapsasse, qualquer discurso feito minutos
        depois do início do evento (o caso comum) erraria o casamento.
      - Falta 'momento' (o discurso não tem dataHoraInicio) -> não dá
        pra comparar nada, não casa.
    """
    inicio = para_datetime(evento.get("dataHoraInicio"))
    if not inicio or not momento:
        return False

    fim = para_datetime(evento.get("dataHoraFim"))
    if fim is None:
        return momento >= inicio

    return inicio <= momento <= fim


def _e_sessao_solene(evento):
    """
    True se o evento for uma sessão NÃO deliberativa (solene, homenagem,
    etc.). Esse tipo de sessão não tem Ordem do Dia com pauta de mérito --
    incluí-la no cruzamento só polui o registro com itens sem relação
    nenhuma com o discurso (ex.: "Homenagem aos 20 anos da Lei Maria da
    Penha" aparecendo na pauta de um discurso sobre criação de
    universidade federal).
    """
    tipo = (evento.get("descricaoTipo") or "").lower()
    return "solene" in tipo or "não deliberativa" in tipo


def escolher_eventos_do_discurso(candidatos, momento_discurso):
    """
    Escolhe, dentre os eventos de Plenário do MESMO DIA do discurso, qual(is)
    evento(s) correspondem à sessão em que ele realmente aconteceu. Ordem de
    preferência:

      1) Evento(s) cuja janela dataHoraInicio-dataHoraFim cobre o horário
         exato do discurso (evento_cobre_horario) -- caso ideal.
      2) Se nenhum cobrir exatamente (comum quando a Câmara fecha o
         dataHoraFim de uma sessão de Ordem do Dia antes do horário real em
         que ela terminou), descarta sessões solenes dos candidatos --
         elas nunca são a sessão de um discurso de mérito/votação -- e usa
         o(s) evento(s) deliberativo(s) que sobrarem.
      3) Se ainda sobrar mais de um candidato deliberativo no dia, fica só
         com o mais próximo do horário do discurso, em vez de misturar a
         pauta de todos -- isso é o que antes fazia registros como o das
         12:48 virem com "várias pautas, de outros temas, nada a ver": ao
         cair no fallback, TODOS os eventos do dia entravam, solenes
         inclusive.

    Se não houver nenhum candidato no dia, devolve lista vazia (sem pauta).
    """
    if not candidatos:
        return []

    match_exato = [ev for ev in candidatos if evento_cobre_horario(ev, momento_discurso)]
    if match_exato:
        return match_exato

    deliberativos = [ev for ev in candidatos if not _e_sessao_solene(ev)]
    restantes = deliberativos or candidatos

    if len(restantes) <= 1 or not momento_discurso:
        return restantes

    def distancia(ev):
        inicio = para_datetime(ev.get("dataHoraInicio"))
        return abs((inicio - momento_discurso).total_seconds()) if inicio else float("inf")

    return [min(restantes, key=distancia)]
