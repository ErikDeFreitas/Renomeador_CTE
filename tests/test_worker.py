import importlib
import sys

from PySide6.QtCore import Qt

from renomeador_cte import cte_engine as engine
from renomeador_cte.worker import Tarefa


def test_tarefa_emite_progresso_e_concluida(qtbot):
    def funcao(progresso):
        progresso(1, 2)
        progresso(2, 2)
        return "ok"

    tarefa = Tarefa(funcao)
    vistos = []
    tarefa.progresso.connect(lambda a, b: vistos.append((a, b)))
    with qtbot.waitSignal(tarefa.concluida, timeout=5000) as sinal:
        tarefa.start()
    tarefa.wait()
    assert sinal.args == ["ok"]
    assert vistos == [(1, 2), (2, 2)]


def test_cancelar_para_exportacao_depois_do_arquivo_atual(qtbot, tmp_path, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(3)
    resultado = resultado_falso(pdf, [1, 2, 3])
    saida = tmp_path / "saida"
    tarefa = Tarefa(lambda progresso: engine.export_documents(resultado, saida, progress=progresso))
    tarefa.progresso.connect(lambda *_: tarefa.cancelar(), Qt.DirectConnection)  # corre na thread da tarefa
    with qtbot.waitSignal(tarefa.cancelada, timeout=5000):
        tarefa.start()
    tarefa.wait()
    assert len(list(saida.glob("*.pdf"))) == 1
    assert list(saida.glob("*.part")) == []


def test_cancelar_analise(qtbot, pdf_em_branco):
    pdf = pdf_em_branco(5)
    vistos = []
    tarefa = Tarefa(lambda progresso: engine.analyze_pdf(pdf, progresso))
    tarefa.progresso.connect(lambda a, b: vistos.append(a))
    tarefa.progresso.connect(lambda *_: tarefa.cancelar(), Qt.DirectConnection)  # corre na thread da tarefa
    with qtbot.waitSignal(tarefa.cancelada, timeout=5000):
        tarefa.start()
    tarefa.wait()
    assert vistos == [1]


def test_erro_de_pdf_vira_falhou(qtbot, tmp_path):
    ruim = tmp_path / "ruim.pdf"
    ruim.write_bytes(b"isto nao e um pdf")
    tarefa = Tarefa(lambda progresso: engine.analyze_pdf(ruim, progresso))
    with qtbot.waitSignal(tarefa.falhou, timeout=5000) as sinal:
        tarefa.start()
    tarefa.wait()
    assert sinal.args[0].startswith("Não foi possível ler o PDF")


def test_erro_inesperado_vira_falhou(qtbot):
    def funcao(progresso):
        raise RuntimeError("boom")

    tarefa = Tarefa(funcao)
    with qtbot.waitSignal(tarefa.falhou, timeout=5000) as sinal:
        tarefa.start()
    tarefa.wait()
    assert sinal.args == ["Erro inesperado: boom"]


def test_dados_variavel_e_padrao(monkeypatch, tmp_path):
    from renomeador_cte import dados

    monkeypatch.setenv("RENOMEADOR_DADOS", str(tmp_path / "x"))
    assert dados.pasta_dados() == tmp_path / "x"
    monkeypatch.delenv("RENOMEADOR_DADOS")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert dados.pasta_dados() == tmp_path / "RenomeadorCTE"
    assert dados.NOME_PASTA == "RenomeadorCTE"


def test_importar_nao_cria_pasta(monkeypatch, tmp_path):
    alvo = tmp_path / "nao_criar"
    monkeypatch.setenv("RENOMEADOR_DADOS", str(alvo))
    original = sys.modules.pop("renomeador_cte.dados", None)
    try:
        importlib.import_module("renomeador_cte.dados")
        assert not alvo.exists()
    finally:
        if original is not None:
            sys.modules["renomeador_cte.dados"] = original
