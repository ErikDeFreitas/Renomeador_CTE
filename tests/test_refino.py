"""Refino pós-lançamento da 2.0.0: PDF com AES, pasta de destino digitada e espera limitada ao fechar."""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError

from renomeador_cte import cte_engine
from renomeador_cte.tela import TelaRenomear, normalizar_pasta


def test_pdf_com_criptografia_aes_e_lido(tmp_path):
    escritor = PdfWriter()
    escritor.add_blank_page(width=200, height=200)
    escritor.encrypt(user_password="", owner_password="dono", algorithm="AES-256")
    pdf = tmp_path / "aes.pdf"
    with pdf.open("wb") as fluxo:
        escritor.write(fluxo)
    assert PdfReader(str(pdf)).is_encrypted
    resultado = cte_engine.analyze_pdf(pdf)
    assert resultado.total_pages == 1


def test_falta_de_biblioteca_de_criptografia_vira_mensagem_em_portugues(tmp_path, monkeypatch):
    def sem_cryptography(_caminho):
        raise DependencyError("cryptography>=3.1 is required for AES algorithm")

    monkeypatch.setattr(cte_engine, "PdfReader", sem_cryptography)
    with pytest.raises(cte_engine.PdfAnalysisError, match="criptografia que este programa não consegue abrir"):
        cte_engine.analyze_pdf(tmp_path / "x.pdf")


@pytest.mark.parametrize("texto, esperado", [
    ("", ""),
    ('  "C:\\Saida\\CTEs"  ', "C:\\Saida\\CTEs"),
    ("C:\\Saida", "C:\\Saida"),
    ("CTEs", "C:\\Origem\\CTEs"),
    ('"..\\Outra"', "C:\\Origem\\..\\Outra"),
])
def test_normalizar_pasta(texto, esperado):
    assert normalizar_pasta(texto, Path("C:\\Origem\\arquivo.pdf")) == esperado


def test_pasta_relativa_sem_pdf_fica_como_digitada():
    assert normalizar_pasta("CTEs", None) == "CTEs"


class _TarefaPresa:
    def __init__(self):
        self.chamadas = []

    def wait(self, *limite):
        self.chamadas.append(("wait", *limite))
        return bool(not limite)  # com limite: estoura; sem limite (depois do terminate): termina

    def terminate(self):
        self.chamadas.append(("terminate",))


def test_aguardar_derruba_tarefa_presa_depois_do_limite(qtbot, contexto):
    tela = TelaRenomear(contexto)
    qtbot.addWidget(tela)
    presa = _TarefaPresa()
    tela._tarefa = presa
    tela.aguardar(50)
    assert presa.chamadas == [("wait", 50), ("terminate",), ("wait",)]
    tela._tarefa = None
