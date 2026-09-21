"""Conexão e schema do SQLite."""

import sqlite3

from .config import DATASETS_PATH, SQLITE_PATH


def abrir_banco():
    DATASETS_PATH.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(SQLITE_PATH)
    db.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS deputados (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            sigla_uf TEXT,
            url_foto TEXT,
            email TEXT
        );
        CREATE TABLE IF NOT EXISTS filiacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deputado_id INTEGER NOT NULL REFERENCES deputados(id),
            partido TEXT NOT NULL,
            data_inicio TEXT NOT NULL,
            data_fim TEXT,
            UNIQUE(deputado_id, partido, data_inicio, data_fim)
        );
        CREATE TABLE IF NOT EXISTS discursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deputado_id INTEGER NOT NULL REFERENCES deputados(id),
            filiacao_id INTEGER REFERENCES filiacoes(id),
            data_hora_inicio TEXT NOT NULL,
            tipo_discurso TEXT,
            fase TEXT,
            nu_sessao TEXT,
            tipo_sessao TEXT,
            url_video TEXT,
            url_texto_integral TEXT,
            sumario TEXT,
            transcricao TEXT,
            fala TEXT,
            fala_fonte TEXT,
            keywords_raw TEXT
        );
        CREATE TABLE IF NOT EXISTS pautas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discurso_id INTEGER NOT NULL REFERENCES discursos(id),
            topico TEXT,
            regime TEXT,
            situacao_item TEXT,
            relator TEXT,
            proposicao TEXT,
            ementa TEXT,
            proposicao_relacionada TEXT,
            ementa_relacionada TEXT,
            tema TEXT
        );
        CREATE TABLE IF NOT EXISTS etl_processados (
            deputado_id INTEGER PRIMARY KEY REFERENCES deputados(id),
            processado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_discursos_deputado ON discursos(deputado_id);
        CREATE INDEX IF NOT EXISTS idx_discursos_data ON discursos(data_hora_inicio);
    """)
    colunas_pautas = {row[1] for row in db.execute("PRAGMA table_info(pautas)")}
    if "tema" not in colunas_pautas:
        db.execute("ALTER TABLE pautas ADD COLUMN tema TEXT")
        db.commit()
    # Migra bancos criados antes da remoção do término (todos eram NULL).
    colunas = {row[1] for row in db.execute("PRAGMA table_info(discursos)")}
    if "data_hora_fim" in colunas:
        db.execute("ALTER TABLE discursos DROP COLUMN data_hora_fim")
        db.commit()
    return db
