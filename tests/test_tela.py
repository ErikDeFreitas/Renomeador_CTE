from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from tcm_ui.components import Etiqueta, Modal

from renomeador_cte import cte_engine
from renomeador_cte.tela import COL_STATUS, COLUNAS, FILTROS, TelaRenomear


@pytest.fixture
def tela(qtbot, contexto):
    pagina = TelaRenomear(contexto)
    qtbot.addWidget(pagina)
    pagina.resize(1100, 900)
    return pagina


def esperar(qtbot, tela):
    qtbot.waitUntil(lambda: not tela.rodando, timeout=10000)


def usar_resultado(monkeypatch, resultado, revisar=()):
    """Troca analyze_pdf por um resultado pronto; `revisar` lista os números que ganham um aviso."""
    for doc in resultado.documents:
        if int(doc.number) in revisar:
            doc.warnings.append("Conferir este CT-e.")
    cte_engine.mark_repeated_numbers(resultado.documents)
    monkeypatch.setattr(cte_engine, "analyze_pdf", lambda caminho, progresso=None: resultado)


def linhas(tela):
    """{texto da coluna Número: índice da linha}"""
    return {tela.tabela.item(i, 0).text(): i for i in range(tela.tabela.rowCount())}


def etiqueta(tela, linha):
    return tela.tabela.cellWidget(linha, COL_STATUS).findChild(Etiqueta)


def valor(indicador):
    return indicador._valor.text()


def avisos_falsos(monkeypatch, escolha=None):
    """Troca os Modal por falsos; devolve a lista (tipo, título, descrição, tom). `escolha(título)` responde."""
    chamadas = []

    def informar(cls, pai, titulo, descricao, tom="info"):
        chamadas.append(("informar", titulo, descricao, tom))

    def escolher(cls, pai, titulo, descricao, opcoes, tom=None):
        chamadas.append(("escolher", titulo, descricao, tom))
        return escolha(titulo) if escolha else None

    monkeypatch.setattr(Modal, "informar", classmethod(informar))
    monkeypatch.setattr(Modal, "escolher", classmethod(escolher))
    return chamadas


def test_constantes():
    assert COLUNAS == ["Número", "Emissão", "Tomador", "Páginas", "Arquivo", "Status"]
    assert COL_STATUS == 5
    assert FILTROS == ["Todos os status", "Prontos", "Para revisar"]


def test_estado_inicial(tela):
    assert not tela.rodando and not tela.pendente and tela.resultado is None
    assert list(tela.indicadores) == ["paginas", "ctes", "prontos", "revisar"]
    assert [valor(i) for i in tela.indicadores.values()] == ["–"] * 4
    assert not tela.botao_gerar.isEnabled()
    assert tela._pilha.currentWidget() is tela.vazio
    assert tela.progresso.isHidden() and tela.rotulo_progresso.isHidden()


def test_analisar_mostra_linhas_sufixo_e_indicadores(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(3)
    usar_resultado(monkeypatch, resultado_falso(pdf, [774, 775, 775]))
    tela.analisar(str(pdf))
    assert tela.rodando
    esperar(qtbot, tela)
    assert tela.tabela.rowCount() == 3
    assert sorted(tela.tabela.item(i, 4).text() for i in range(3)) == ["774.pdf", "775.pdf", "775_2.pdf"]
    assert [valor(i) for i in tela.indicadores.values()] == ["3", "3", "1", "2"]
    assert tela._pilha.currentWidget() is tela.tabela
    assert tela.pendente and tela.botao_gerar.isEnabled()
    assert tela.campo_pasta.text() == str(pdf.parent / f"CTEs_{pdf.stem}")
    assert tela.progresso.isHidden()


def test_ordenar_por_numero_move_etiquetas(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(3)
    resultado = resultado_falso(pdf, [10, 9])
    resultado.unidentified_pages = [2]
    usar_resultado(monkeypatch, resultado, revisar={9})
    tela.analisar(str(pdf))
    esperar(qtbot, tela)

    def ordem():
        return [(tela.tabela.item(i, 0).text(), tela.tabela.item(i, 4).text(), etiqueta(tela, i).text())
                for i in range(3)]

    tela.tabela.sortItems(0, Qt.AscendingOrder)  # pela chave numérica: "9" antes de "10"
    assert ordem() == [("–", "_paginas_nao_identificadas.pdf", "Revisar"), ("9", "9.pdf", "Revisar"),
                       ("10", "10.pdf", "Pronto")]
    tela.tabela.sortItems(0, Qt.DescendingOrder)
    assert [linha[0] for linha in ordem()] == ["10", "9", "–"]
    assert etiqueta(tela, 0).text() == "Pronto"  # a etiqueta anda junto com a linha


def test_filtro_para_revisar_e_pesquisa(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(3)
    usar_resultado(monkeypatch, resultado_falso(pdf, [1, 2, 3]), revisar={2})
    tela.analisar(str(pdf))
    esperar(qtbot, tela)
    por_numero = linhas(tela)

    def ocultas():
        return {n for n, i in por_numero.items() if tela.tabela.isRowHidden(i)}

    assert ocultas() == set()
    tela.filtro_status.setCurrentIndex(2)  # Para revisar
    assert ocultas() == {"1", "3"}
    tela.filtro_status.setCurrentIndex(1)  # Prontos
    assert ocultas() == {"2"}
    tela.filtro_status.setCurrentIndex(0)
    tela.pesquisa.setText("3.pdf")
    assert ocultas() == {"1", "2"}
    tela.pesquisa.setText("")
    assert ocultas() == set()


def test_prefixo_renomeia_coluna_e_dica(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(1)
    assert tela.campo_prefixo_field._rodape.text() == "Exemplo de nome: 774.pdf"
    usar_resultado(monkeypatch, resultado_falso(pdf, [321]))
    tela.analisar(str(pdf))
    esperar(qtbot, tela)
    assert tela.campo_prefixo_field._rodape.text() == "Exemplo de nome: 321.pdf"
    tela.campo_prefixo.setText("CT/E-")  # a barra não vale em nome de arquivo
    assert tela.tabela.item(0, 4).text() == "CTE-321.pdf"
    assert tela.campo_prefixo_field._rodape.text() == "Exemplo de nome: CTE-321.pdf"


def test_pdf_sem_texto_mostra_nenhum_cte(tela, qtbot, monkeypatch, pdf_em_branco):
    chamadas = avisos_falsos(monkeypatch)
    tela.analisar(str(pdf_em_branco(2)))
    esperar(qtbot, tela)
    assert [(c[0], c[1], c[3]) for c in chamadas] == [("informar", "Nenhum CT-e encontrado", "perigo")]
    assert tela.resultado is not None and tela.resultado.documents == [] and not tela.pendente
    assert [tela.tabela.item(0, c).text() for c in (0, 2)] == ["–", "Páginas não identificadas"]
    assert not tela.botao_gerar.isEnabled()
    assert tela.zona.isEnabled() and tela.campo_pasta.isEnabled()  # livre para outro PDF


def test_pdf_invalido_mostra_falha(tela, qtbot, monkeypatch, tmp_path):
    ruim = tmp_path / "ruim.pdf"
    ruim.write_bytes(b"isto nao e um pdf")
    chamadas = avisos_falsos(monkeypatch)
    tela.analisar(str(ruim))
    esperar(qtbot, tela)
    assert len(chamadas) == 1
    assert (chamadas[0][0], chamadas[0][1], chamadas[0][3]) == ("informar", "Falha ao ler o PDF", "perigo")
    assert chamadas[0][2].startswith("Não foi possível ler o PDF")
    assert tela.resultado is None
    assert tela.zona._titulo.text() == "Não foi possível ler o arquivo"
    assert tela.zona.isEnabled() and tela.progresso.isHidden()


def preparar_geracao(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso, saida):
    pdf = pdf_em_branco(2)
    usar_resultado(monkeypatch, resultado_falso(pdf, [1, 2]))
    tela.analisar(str(pdf))
    esperar(qtbot, tela)
    tela.campo_pasta.setText(str(saida))
    return pdf


@pytest.mark.parametrize("escolha, esperado", [
    (None, {"1.pdf": b"antigo"}),
    ("substituir", {"1.pdf": None, "2.pdf": None}),
    ("manter", {"1.pdf": b"antigo", "1_2.pdf": None, "2.pdf": None}),
])
def test_conflito_cancelar_substituir_manter(tela, qtbot, monkeypatch, tmp_path, pdf_em_branco, resultado_falso,
                                             escolha, esperado):
    saida = tmp_path / "saida"
    saida.mkdir()
    (saida / "1.pdf").write_bytes(b"antigo")
    pdf = preparar_geracao(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso, saida)
    original = pdf.read_bytes()
    chamadas = avisos_falsos(monkeypatch, lambda titulo: escolha if titulo == "Arquivos já existem" else False)
    tela.gerar()
    esperar(qtbot, tela)
    atual = {p.name: p.read_bytes() for p in saida.glob("*.pdf")}
    assert set(atual) == set(esperado)
    for nome, conteudo in esperado.items():
        if conteudo is None:
            assert atual[nome].startswith(b"%PDF")
        else:
            assert atual[nome] == conteudo
    assert pdf.read_bytes() == original  # a origem nunca é alterada
    assert chamadas[0][1] == "Arquivos já existem"
    if escolha is None:
        assert len(chamadas) == 1 and tela.pendente  # cancelou: nada foi gerado
    else:
        assert [(c[1], c[3]) for c in chamadas[1:]] == [("Arquivos gerados", "sucesso")]
        assert not tela.pendente


def test_gerar_sem_conflito_abre_pasta_quando_pedido(tela, qtbot, monkeypatch, tmp_path, pdf_em_branco,
                                                      resultado_falso):
    saida = tmp_path / "novos"
    preparar_geracao(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso, saida)
    abertos = []
    monkeypatch.setattr("renomeador_cte.tela.QDesktopServices.openUrl", lambda url: abertos.append(url.toLocalFile()))
    chamadas = avisos_falsos(monkeypatch, lambda titulo: True)
    tela.gerar()
    esperar(qtbot, tela)
    assert sorted(p.name for p in saida.glob("*.pdf")) == ["1.pdf", "2.pdf"]
    assert [c[1] for c in chamadas] == ["Arquivos gerados"]
    assert [Path(a) for a in abertos] == [saida]
    assert {etiqueta(tela, i).text() for i in range(2)} == {"Salvo"}


def test_etiqueta_revisar_abre_detalhe(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(2)
    usar_resultado(monkeypatch, resultado_falso(pdf, [1, 2]), revisar={2})
    tela.analisar(str(pdf))
    esperar(qtbot, tela)
    chamadas = avisos_falsos(monkeypatch)
    por_numero = linhas(tela)
    pronto = etiqueta(tela, por_numero["1"])
    revisar = etiqueta(tela, por_numero["2"])
    assert pronto.cursor().shape() != Qt.PointingHandCursor  # "Pronto" não é clicável
    assert revisar.text() == "Revisar" and revisar.cursor().shape() == Qt.PointingHandCursor
    revisar.clicada.emit()
    assert chamadas == [("informar", "Revisar", "Conferir este CT-e.", "aviso")]


def test_soltar_pdf_na_zona_analisa(tela, qtbot, monkeypatch, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(1)
    usar_resultado(monkeypatch, resultado_falso(pdf, [774]))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(pdf))])
    tela.zona.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
    assert tela.rodando
    esperar(qtbot, tela)
    assert tela.tabela.rowCount() == 1
    assert tela.zona._titulo.text() == pdf.name


def test_procurar_pdf_usa_a_janela_como_pai(tela, qtbot, monkeypatch, contexto, pdf_em_branco, resultado_falso):
    pdf = pdf_em_branco(1)
    usar_resultado(monkeypatch, resultado_falso(pdf, [774]))
    pais = []

    def escolher(pai, *a, **k):
        pais.append(pai)
        return str(pdf), ""

    monkeypatch.setattr("renomeador_cte.tela.QFileDialog.getOpenFileName", escolher)
    tela.zona.procurar.emit()
    esperar(qtbot, tela)
    assert pais == [contexto.janela]
    assert tela.tabela.rowCount() == 1


def test_pasta_escolhida_pelo_usuario_nao_e_trocada(tela, qtbot, monkeypatch, tmp_path, pdf_em_branco,
                                                     resultado_falso):
    pdf = pdf_em_branco(1)
    usar_resultado(monkeypatch, resultado_falso(pdf, [774]))
    tela.campo_pasta.setText(str(tmp_path / "minha"))
    tela.campo_pasta.textEdited.emit("x")  # como se o usuário tivesse digitado
    tela.analisar(str(pdf))
    esperar(qtbot, tela)
    assert tela.campo_pasta.text() == str(tmp_path / "minha")
