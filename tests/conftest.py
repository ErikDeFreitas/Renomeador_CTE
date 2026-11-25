import os
import tempfile

# Antes de qualquer import do pacote: nenhum teste pode tocar a pasta real %LOCALAPPDATA%\RenomeadorCTE.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RENOMEADOR_DADOS"] = tempfile.mkdtemp(prefix="renomeador_dados_")

import pytest  # noqa: E402
from pypdf import PdfWriter  # noqa: E402
from PySide6 import QtCore  # noqa: E402


class _QSettingsIni(QtCore.QSettings):
    """QSettings(org, app) em arquivo .ini (pasta temporária), nunca no registro do Windows.

    No Qt 6, QSettings(org, app) ignora setDefaultFormat() e usa sempre o registro; por isso a classe é
    trocada em PySide6.QtCore antes de qualquer `from PySide6.QtCore import QSettings`.
    """

    def __init__(self, *args, **kwargs):
        if 1 <= len(args) <= 2 and not kwargs and all(isinstance(a, str) for a in args):
            super().__init__(QtCore.QSettings.IniFormat, QtCore.QSettings.UserScope, *args)
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = _QSettingsIni
from PySide6.QtCore import QSettings  # noqa: E402

from renomeador_cte import cte_engine as engine  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def _qsettings_fora_do_registro(tmp_path_factory):
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path_factory.mktemp("qsettings")))


def _make_key(number: int, model: str = "57", series: int = 3, branch: str = "0001") -> str:
    base = f"3526111122233300{branch}{model}{series:03d}{number:09d}1{12345678:08d}"[:43]
    return base + str(engine.key_check_digit(base))


def _pdf_em_branco(tmp_path, paginas: int):
    escritor = PdfWriter()
    for _ in range(paginas):
        escritor.add_blank_page(width=200, height=200)
    caminho = tmp_path / "origem.pdf"
    with caminho.open("wb") as fluxo:
        escritor.write(fluxo)
    return caminho


def _resultado_falso(pdf, numeros: list[int]):
    """AnalysisResult fictício: um CteDocument por número, uma página cada, sobre o PDF em branco."""
    documentos = [
        engine.CteDocument(str(n), key=_make_key(n), pages=[i]) for i, n in enumerate(numeros)
    ]
    return engine.AnalysisResult(pdf, len(documentos), documentos, [])


@pytest.fixture
def make_key():
    return _make_key


@pytest.fixture
def pdf_em_branco(tmp_path):
    return lambda paginas: _pdf_em_branco(tmp_path, paginas)


@pytest.fixture
def resultado_falso():
    return _resultado_falso


@pytest.fixture
def janela(qtbot):
    from PySide6.QtWidgets import QWidget

    pai = QWidget()
    qtbot.addWidget(pai)
    return pai


@pytest.fixture
def contexto(janela):
    import logging

    from tcm_ui.modulo import Contexto

    from renomeador_cte import dados

    return Contexto("TCMSP\\teste", dados.PASTA, "avulso", logging.getLogger("teste"), janela)
