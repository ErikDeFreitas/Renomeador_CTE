import threading

import pytest
from PySide6.QtWidgets import QApplication
from tcm_ui.components import Modal

from renomeador_cte import cte_engine
from renomeador_cte.instancia import Renomeador
from renomeador_cte.worker import Tarefa


@pytest.fixture
def inst(qtbot, contexto):
    objeto = Renomeador(contexto)
    yield objeto
    if objeto.tela is not None:
        qtbot.addWidget(objeto.tela)


def test_widget_e_criado_uma_vez(inst):
    assert inst.widget("separar") is inst.widget("separar")


def test_pagina_desconhecida(inst):
    with pytest.raises(KeyError):
        inst.widget("outra")


def test_sem_acoes_no_cabecalho(inst):
    assert inst.acoes_cabecalho("separar") == []


def test_pode_fechar_antes_e_depois_de_abrir_a_tela(inst):
    assert inst.pode_fechar()
    inst.widget("separar")
    assert inst.pode_fechar()


def test_fecha_sem_aviso_com_pdf_analisado_e_nao_gerado(inst, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(1)
    monkeypatch.setattr(cte_engine, "analyze_pdf", lambda caminho, progresso=None: resultado_falso(pdf, [774]))
    tela = inst.widget("separar")
    tela.analisar(str(pdf))
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    assert tela.pendente
    assert inst.pode_fechar()


def test_nao_fecha_com_tarefa_presa_e_ao_sair_cancela_sem_modal(inst, qtbot, monkeypatch, tmp_path):
    liberar = threading.Event()

    def analise_presa(caminho, progresso=None):
        liberar.wait(10)  # presa até alguém soltar; o progresso então enxerga o cancelamento
        progresso(1, 1)

    avisos = []
    monkeypatch.setattr(cte_engine, "analyze_pdf", analise_presa)
    monkeypatch.setattr(Modal, "informar", classmethod(lambda cls, *a, **k: avisos.append(a)))
    monkeypatch.setattr(Modal, "escolher", classmethod(lambda cls, *a, **k: avisos.append(a)))
    tela = inst.widget("separar")
    tela.analisar(str(tmp_path / "x.pdf"))
    tarefa = tela._tarefa
    cancelada = []
    tarefa.cancelada.connect(lambda: cancelada.append(True))
    qtbot.waitUntil(tarefa.isRunning, timeout=5000)
    assert tela.rodando
    assert not inst.pode_fechar()

    threading.Timer(0.3, liberar.set).start()
    QApplication.instance().aboutToQuit.emit()  # parar() + aguardar(): só volta com a thread terminada
    assert tarefa.isFinished()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    assert cancelada == [True]
    assert avisos == []


def test_cancelar_de_fora_da_thread_com_funcao_bloqueada(qtbot):
    liberar = threading.Event()
    tarefa = Tarefa(lambda progresso: (liberar.wait(10), progresso(1, 1)))
    with qtbot.waitSignal(tarefa.cancelada, timeout=5000):
        tarefa.start()
        qtbot.waitUntil(tarefa.isRunning, timeout=5000)
        tarefa.cancelar()  # da thread da interface, com a função bloqueada
        liberar.set()
    tarefa.wait()
    assert not tarefa.isRunning()
