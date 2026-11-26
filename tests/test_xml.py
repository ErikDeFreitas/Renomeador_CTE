"""Renomeador de XML: motor, módulo, instância e tela (XMLs fictícios)."""

import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import pytest
from tcm_ui.components import Modal

import renomeador_cte
from renomeador_cte import dados, xml_engine
from renomeador_cte.instancia_xml import RenomeadorXml
from renomeador_cte.modulo_xml import MODULO
from renomeador_cte.tela_xml import COL_ARQUIVO, COL_NOVO, TelaRenomearXml


def cte(numero: str, namespace: bool = True) -> str:
    ns = ' xmlns="http://www.portalfiscal.inf.br/cte"' if namespace else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?><cteProc{ns} versao="4.00"><CTe><infCte>'
            f"<ide><cUF>35</cUF><nCT>{numero}</nCT></ide></infCte></CTe></cteProc>")


def criar(pasta: Path, **arquivos: str) -> None:
    for nome, conteudo in arquivos.items():
        (pasta / nome.replace("__", ".")).write_text(conteudo, encoding="utf-8")


def nomes(pasta: Path) -> list[str]:
    return sorted(p.name for p in pasta.iterdir())


# --- Motor -------------------------------------------------------------------
def test_le_numero_com_e_sem_namespace(tmp_path):
    criar(tmp_path, a__xml=cte("774"), b__xml=cte("42", namespace=False))
    assert xml_engine.ler_numero(tmp_path / "a.xml") == "774"
    assert xml_engine.ler_numero(tmp_path / "b.xml") == "42"


def test_planeja_e_renomeia(tmp_path):
    criar(tmp_path, chave1__xml=cte("774"), chave2__xml=cte("775"), outro__txt="x")
    analise = xml_engine.analisar_pasta(tmp_path)
    assert [(i.origem.name, i.estado, i.novo_nome) for i in analise.itens] == [
        ("chave1.xml", xml_engine.PRONTO, "774.xml"), ("chave2.xml", xml_engine.PRONTO, "775.xml")]
    assert nomes(tmp_path) == ["chave1.xml", "chave2.xml", "outro.txt"]  # ler não altera nada
    xml_engine.renomear(analise)
    assert nomes(tmp_path) == ["774.xml", "775.xml", "outro.txt"]
    assert all(i.renomeado and not i.erro for i in analise.itens)


def test_arquivo_ja_com_o_nome_nao_vira_sufixo(tmp_path):
    """No script antigo, 774.xml virava 774_1.xml ao rodar de novo."""
    criar(tmp_path, **{"774__xml": cte("774")})
    analise = xml_engine.analisar_pasta(tmp_path)
    assert analise.itens[0].estado == xml_engine.JA_NOMEADO
    xml_engine.renomear(analise)
    assert nomes(tmp_path) == ["774.xml"]


def test_nome_em_uso_nao_renomeia_nem_cria_sufixo(tmp_path):
    criar(tmp_path, **{"774__xml": "não é o CT-e 774", "a__xml": cte("774"), "b__xml": cte("774")})
    analise = xml_engine.analisar_pasta(tmp_path)
    por_nome = {i.origem.name: i for i in analise.itens}
    assert por_nome["774.xml"].estado == xml_engine.ERRO  # XML quebrado
    assert por_nome["a.xml"].estado == por_nome["b.xml"].estado == xml_engine.NOME_EM_USO
    assert por_nome["a.xml"].novo_nome == "" and por_nome["a.xml"].revisar
    xml_engine.renomear(analise)
    assert nomes(tmp_path) == ["774.xml", "a.xml", "b.xml"]
    assert (tmp_path / "774.xml").read_text(encoding="utf-8") == "não é o CT-e 774"


def test_numero_repetido_renomeia_so_o_primeiro(tmp_path):
    criar(tmp_path, a__xml=cte("774"), b__xml=cte("774"))
    analise = xml_engine.analisar_pasta(tmp_path)
    a, b = analise.itens
    assert (a.estado, a.novo_nome, b.estado) == (xml_engine.PRONTO, "774.xml", xml_engine.NOME_EM_USO)
    assert "aparece em 2 XMLs" in a.aviso
    xml_engine.renomear(analise)
    assert nomes(tmp_path) == ["774.xml", "b.xml"]


def test_sem_numero_e_numero_invalido(tmp_path):
    criar(tmp_path, evento__xml="<procEventoCTe><x>1</x></procEventoCTe>", ruim__xml=cte("../../x"))
    analise = xml_engine.analisar_pasta(tmp_path)
    por_nome = {i.origem.name: i for i in analise.itens}
    assert por_nome["evento.xml"].estado == xml_engine.SEM_NUMERO
    assert por_nome["ruim.xml"].estado == xml_engine.ERRO and "inválido" in por_nome["ruim.xml"].erro
    xml_engine.renomear(analise)
    assert nomes(tmp_path) == ["evento.xml", "ruim.xml"]


def test_destino_criado_depois_da_leitura_fica_como_esta(tmp_path):
    criar(tmp_path, a__xml=cte("10"))
    analise = xml_engine.analisar_pasta(tmp_path)
    criar(tmp_path, **{"10__xml": "outro"})
    xml_engine.renomear(analise)
    assert analise.itens[0].estado == xml_engine.NOME_EM_USO and analise.itens[0].renomeado is None
    assert nomes(tmp_path) == ["10.xml", "a.xml"]
    assert (tmp_path / "10.xml").read_text(encoding="utf-8") == "outro"


def test_extensao_maiuscula_e_progresso(tmp_path):
    criar(tmp_path, A__XML=cte("5"))
    chamadas = []
    analise = xml_engine.analisar_pasta(tmp_path, lambda feito, total: chamadas.append((feito, total)))
    assert chamadas == [(0, 1), (1, 1)]
    assert analise.itens[0].novo_nome == "5.xml"


def test_pasta_inexistente(tmp_path):
    with pytest.raises(xml_engine.ErroPasta):
        xml_engine.analisar_pasta(tmp_path / "nao_existe")


# --- Módulo e instância ------------------------------------------------------
def test_valores_do_modulo():
    assert (MODULO.id, MODULO.nome, MODULO.icone) == ("renomeador_xml", "Renomeador de XML", "arquivo")
    assert (MODULO.grupo_ad, MODULO.repositorio, MODULO.nome_exe) == (
        "SF-RenomeadorCTE", "ErikDeFreitas/Renomeador_CTE", "RenomeadorXML.exe")
    assert MODULO.versao == renomeador_cte.__version__
    assert MODULO.pasta_dados == dados.PASTA
    assert [p.chave for p in MODULO.paginas] == ["renomear"]


def test_entry_point_carrega_o_modulo():
    eps = {ep.name: ep for ep in entry_points(group="sistema_financeiro.modulos")}
    assert eps["renomeador_xml"].load() is MODULO


def test_modulo_e_leve(tmp_path):
    codigo = "import sys, renomeador_cte.modulo_xml; print('renomeador_cte.tela_xml' in sys.modules)"
    env = {**os.environ, "RENOMEADOR_DADOS": str(tmp_path / "nao_criar")}
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, check=True)
    assert saida.stdout.split() == ["False"]


def test_instancia(qtbot, contexto):
    inst = RenomeadorXml(contexto)
    assert inst.pode_fechar()
    tela = inst.widget("renomear")
    qtbot.addWidget(tela)
    assert inst.widget("renomear") is tela
    assert inst.acoes_cabecalho("renomear") == []
    with pytest.raises(KeyError):
        inst.widget("outra")


# --- Tela --------------------------------------------------------------------
@pytest.fixture
def tela(qtbot, contexto):
    pagina = TelaRenomearXml(contexto)
    qtbot.addWidget(pagina)
    pagina.resize(1100, 900)
    return pagina


def avisos_falsos(monkeypatch, resposta=False):
    chamadas = []
    monkeypatch.setattr(Modal, "informar", classmethod(lambda cls, pai, titulo, *a, **k: chamadas.append(titulo)))
    monkeypatch.setattr(Modal, "escolher",
                        classmethod(lambda cls, pai, titulo, *a, **k: chamadas.append(titulo) or resposta))
    return chamadas


def test_tela_le_e_renomeia(tela, qtbot, tmp_path, monkeypatch):
    avisos = avisos_falsos(monkeypatch)
    criar(tmp_path, a__xml=cte("774"), b__xml=cte("775"), **{"776__xml": cte("776")},
          evento__xml="<x/>")
    assert not tela.botao_renomear.isEnabled() and not tela.botao_ler.isEnabled()
    tela.campo_pasta.setText(f'"{tmp_path}"')  # colado do Explorer, com aspas
    tela.ler()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    assert tela.tabela.rowCount() == 4
    valores = {k: i._valor.text() for k, i in tela.indicadores.items()}
    assert valores == {"xmls": "4", "prontos": "2", "ok": "1", "revisar": "1"}
    linhas = {tela.tabela.item(r, COL_ARQUIVO).text(): tela.tabela.item(r, COL_NOVO).text()
              for r in range(4)}
    assert linhas["a.xml"] == "774.xml" and linhas["776.xml"] == "–"
    assert tela.botao_renomear.isEnabled()

    tela.renomear()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    assert nomes(tmp_path) == ["774.xml", "775.xml", "776.xml", "evento.xml"]
    assert avisos == ["XMLs renomeados"]
    assert tela.indicadores["ok"]._valor.text() == "3"
    assert not tela.botao_renomear.isEnabled()  # nada mais a renomear


def test_tela_filtro_para_revisar(tela, qtbot, tmp_path, monkeypatch):
    avisos_falsos(monkeypatch)
    criar(tmp_path, a__xml=cte("1"), evento__xml="<x/>")
    tela.campo_pasta.setText(str(tmp_path))
    tela.ler()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    tela.filtro_status.setCurrentIndex(2)  # Para revisar
    visiveis = [tela.tabela.item(r, COL_ARQUIVO).text() for r in range(2) if not tela.tabela.isRowHidden(r)]
    assert visiveis == ["evento.xml"]


def test_tela_pasta_inexistente_e_pasta_vazia(tela, qtbot, tmp_path, monkeypatch):
    avisos = avisos_falsos(monkeypatch)
    tela.campo_pasta.setText(str(tmp_path / "nao_existe"))
    tela.ler()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    tela.campo_pasta.setText(str(tmp_path))
    tela.ler()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    assert avisos == ["Falha ao ler a pasta", "Nenhum XML encontrado"]


def test_editar_a_pasta_limpa_a_lista(tela, qtbot, tmp_path, monkeypatch):
    avisos_falsos(monkeypatch)
    criar(tmp_path, a__xml=cte("1"))
    tela.campo_pasta.setText(str(tmp_path))
    tela.ler()
    qtbot.waitUntil(lambda: not tela.rodando, timeout=5000)
    qtbot.keyClicks(tela.campo_pasta, "x")
    assert tela.analise is None and tela.tabela.rowCount() == 0
    assert not tela.botao_renomear.isEnabled()
