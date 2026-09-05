"""Funções de escrita no banco: deputados, filiações, discursos e pautas."""


def inserir_deputado(db, deputado):
    db.execute("""INSERT OR REPLACE INTO deputados
        (id, nome, sigla_uf, url_foto, email) VALUES (?, ?, ?, ?, ?)""",
        (deputado["id"], deputado["nome"], deputado.get("siglaUf"),
         deputado.get("urlFoto"), deputado.get("email")))
    for p in deputado.get("historicoPartidos", []):
        # O schema exige partido; períodos sem partido ficam identificados.
        partido = p.get("partido") or "S.PART."
        db.execute("""INSERT OR IGNORE INTO filiacoes
            (deputado_id, partido, data_inicio, data_fim) VALUES (?, ?, ?, ?)""",
            (deputado["id"], partido, p["dataInicio"], p.get("dataFim")))


def filiacao_do_registro(db, deputado_id, registro):
    data = registro.get("dataHoraInicio")
    if not data:
        return None
    row = db.execute("""SELECT id FROM filiacoes
        WHERE deputado_id=? AND data_inicio <= ?
        AND (data_fim IS NULL OR data_fim > ?)
        ORDER BY data_inicio DESC LIMIT 1""", (deputado_id, data, data)).fetchone()
    return row[0] if row else None


def inserir_registros(db, deputado, registros):
    for r in registros:
        sessao = r.get("sessao") or {}
        cur = db.execute("""INSERT INTO discursos
            (deputado_id, filiacao_id, data_hora_inicio,
             tipo_discurso, fase, nu_sessao, tipo_sessao, url_video,
             url_texto_integral, sumario, transcricao, fala, fala_fonte, keywords_raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (deputado["id"], filiacao_do_registro(db, deputado["id"], r),
             r.get("dataHoraInicio") or "0000-01-01T00:00",
             r.get("tipoDiscurso"), sessao.get("fase"), sessao.get("nuSessao"),
             sessao.get("tipoSessao"), sessao.get("url_video"),
             sessao.get("url_texto_integral"), r.get("sumario"), r.get("transcricao"),
             r.get("fala"), r.get("fala_fonte"), r.get("keywords")))
        discurso_id = cur.lastrowid
        for p in sessao.get("pauta", []):
            db.execute("""INSERT INTO pautas
                (discurso_id, topico, regime, situacao_item, relator,
                 proposicao, ementa, proposicao_relacionada, ementa_relacionada, tema)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (discurso_id, p.get("topico"), p.get("regime"), p.get("situacaoItem"),
                 p.get("relator"), p.get("proposicao"), p.get("ementa"),
                 p.get("proposicaoRelacionada"), p.get("ementaRelacionada"),
                 p.get("tema")))
