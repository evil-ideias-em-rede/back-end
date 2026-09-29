import json
import unittest
from unittest.mock import patch

from graph.tools.retrieval.audiencias import (
    AUDIENCE_PAGE_CHARS,
    consultar_audiencia,
    consultar_audiencia_por_id,
)


class AudiencePaginationTest(unittest.TestCase):
    def query(self, **kwargs):
        return json.loads(consultar_audiencia_por_id.invoke({"audiencia_id": 136, **kwargs}))

    def test_reported_audience_starts_with_bounded_overview(self):
        original = consultar_audiencia(136)
        self.assertGreater(len(json.dumps(original)), AUDIENCE_PAGE_CHARS)
        page = self.query()
        self.assertLessEqual(len(page["conteudo"]), AUDIENCE_PAGE_CHARS)
        parts = [page["conteudo"]]
        while page["proximo_inicio"] is not None:
            page = self.query(inicio=page["proximo_inicio"])
            self.assertLessEqual(len(page["conteudo"]), AUDIENCE_PAGE_CHARS)
            parts.append(page["conteudo"])
        overview = json.loads("".join(parts))
        self.assertEqual(str(overview["id"]), "136")
        self.assertNotIn("transcricao", overview)
        self.assertEqual(len(overview["indice_discursos"]), len(original["discursos"]))

    def test_paginated_speech_preserves_exact_text_and_annotations(self):
        speech = {"id": "fala-1", "texto": "Ação, educação e direitos. " * 2000,
                  "taxonomia": {"Posicionamento": ["Favorável"]},
                  "propostas": ["Proposta original."]}
        audience = {"id": 136, "discursos": [speech, {"id": "outra", "texto": "Outra fala"}]}
        with patch("graph.tools.retrieval.audiencias.consultar_audiencia", return_value=audience):
            parts, offset = [], 0
            while offset is not None:
                page = self.query(secao="discursos", discurso_id="fala-1", inicio=offset)
                self.assertLessEqual(len(page["conteudo"]), AUDIENCE_PAGE_CHARS)
                parts.append(page["conteudo"])
                offset = page["proximo_inicio"]
            self.assertGreater(len(parts), 1)
            self.assertEqual(json.loads("".join(parts)), speech)
            self.assertEqual(audience["discursos"][0], speech)

    def test_transcript_pages_reconstruct_source_without_truncation(self):
        transcript = "Texto literal da audiência. " * 1200
        with patch("graph.tools.retrieval.audiencias.consultar_audiencia", return_value={"transcricao": transcript}):
            parts, offset = [], 0
            while offset is not None:
                page = self.query(secao="transcricao", inicio=offset)
                parts.append(page["conteudo"])
                offset = page["proximo_inicio"]
            self.assertEqual("".join(parts), transcript)
            self.assertIsNone(self.query(secao="transcricao", inicio=len(transcript))["proximo_inicio"])

    def test_invalid_offsets_and_unknown_speeches_are_explicit(self):
        with patch("graph.tools.retrieval.audiencias.consultar_audiencia", return_value={"id": 136}):
            self.assertIn("erro", self.query(inicio=-1))
            self.assertIn("erro", self.query(secao="discursos", discurso_id="missing"))
            self.assertIn("erro", self.query(secao="resumo", discurso_id="missing"))
