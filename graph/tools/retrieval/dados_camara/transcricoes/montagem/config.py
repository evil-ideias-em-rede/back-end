"""Constantes de caminhos e do período de busca da API."""

from datetime import date
from pathlib import Path

LOCAL_PATH = Path(__file__).resolve().parents[1]
DATASETS_PATH = (LOCAL_PATH / ".." / "datasets")
PUBLIC_HEARING_PATH = (LOCAL_PATH / ".." / ".." / "public_hearing")
SQLITE_PATH = DATASETS_PATH / "deputados.sqlite"

# A API retorna status 400 pra intervalos muito grandes (ex: 2000 a 2026),
# então a busca é feita em janelas menores e os resultados são concatenados
DATA_INICIO_GERAL = "2000-01-01"
DATA_FIM_GERAL = date.today().isoformat()
ANOS_POR_JANELA = 4
