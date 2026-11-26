"""Tela do Renomeador de XML: escolhe a pasta, mostra o nome novo de cada XML de CT-e e renomeia."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QStackedLayout, QWidget
from tcm_ui.components import (
    BarraProgresso, Botao, Campo, CampoPesquisa, CampoTexto, Cartao, CartaoIndicador, EstadoVazio, Etiqueta,
    GradeResponsiva, Modal, Pagina, Selecao, Tabela, Texto,
)
from tcm_ui.modulo import Contexto

from renomeador_cte import xml_engine
from renomeador_cte.tela import FILTRO_PRONTOS, FILTRO_REVISAR, FILTRO_TODOS, FILTROS, _linha, plural
from renomeador_cte.worker import Tarefa

COLUNAS = ["Arquivo atual", "Número", "Novo nome", "Status"]
COL_ARQUIVO, COL_NUMERO, COL_NOVO, COL_STATUS = range(4)
PAPEL_REVISAR = Qt.UserRole + 20
LIMITE_ESPERA_MS = 10_000

TEXTO_SEM_NUMERO = "Este XML não tem o campo <nCT> (número do CT-e). Ele não será renomeado."


def normalizar_pasta(texto: str) -> str:
    """Pasta digitada: sem espaços e aspas nas pontas (cópia do Explorer)."""
    return texto.strip().strip('"').strip()


class TelaRenomearXml(Pagina):
    def __init__(self, contexto: Contexto):
        super().__init__()
        self.contexto = contexto
        self._analise: xml_engine.AnaliseXml | None = None
        self._tarefa: Tarefa | None = None
        self._formato_progresso = ""
        self._ao_sucesso = None
        self._ao_falha = None
        self._encerrando = False

        # --- Pasta ----------------------------------------------------------
        self.campo_pasta = CampoTexto("Selecione a pasta com os XMLs")
        self.campo_pasta.textEdited.connect(self._ao_editar_pasta)
        self.campo_pasta.textChanged.connect(self.campo_pasta.setToolTip)
        self.campo_pasta.returnPressed.connect(self.ler)
        self.botao_procurar = Botao("Procurar", "secundario", icone="pasta")
        self.botao_procurar.clicked.connect(self._procurar_pasta)
        self.botao_ler = Botao("Ler XMLs", "secundario", icone="pesquisa")
        self.botao_ler.clicked.connect(self.ler)
        linha_pasta = QWidget()
        caixa = _linha(self.campo_pasta, self.botao_procurar, self.botao_ler)
        caixa.setContentsMargins(0, 0, 0, 0)
        linha_pasta.setLayout(caixa)

        self.progresso = BarraProgresso()
        self.rotulo_progresso = Texto("", "dica")
        self.progresso.hide()
        self.rotulo_progresso.hide()
        self.botao_renomear = Botao("Renomear XMLs", "primario", "lg", "arquivo")
        self.botao_renomear.clicked.connect(self.renomear)
        pasta = Cartao("Pasta", "Cada XML de CT-e recebe o número do CT-e como nome (ex.: 774.xml), na própria "
                                "pasta. Nenhum arquivo é sobrescrito: se o nome já existir, o XML fica como está.")
        pasta.corpo.addWidget(Campo("Pasta dos XMLs", linha_pasta))
        pasta.corpo.addWidget(self.progresso)
        pasta.corpo.addWidget(self.rotulo_progresso)
        pasta.corpo.addWidget(self.botao_renomear, 0, Qt.AlignLeft)

        # --- Indicadores ----------------------------------------------------
        self.indicadores = {
            "xmls": CartaoIndicador("XMLs", "–", "arquivo", "neutro"),
            "prontos": CartaoIndicador("A renomear", "–", "camadas", "primaria"),
            "ok": CartaoIndicador("Já com o nome", "–", "check_circulo", "sucesso"),
            "revisar": CartaoIndicador("Para revisar", "–", "alerta", "perigo"),
        }
        grade = GradeResponsiva(200)
        for indicador in self.indicadores.values():
            grade.adicionar(indicador)

        # --- Arquivos -------------------------------------------------------
        self.pesquisa = CampoPesquisa("Pesquisar por arquivo ou número")
        self.pesquisa.textChanged.connect(self._filtrar)
        self.filtro_status = Selecao(FILTROS)
        self.filtro_status.setMinimumWidth(180)
        self.filtro_status.currentIndexChanged.connect(self._filtrar)
        self.tabela = Tabela(COLUNAS, coluna_flexivel=COL_ARQUIVO)
        self.tabela.setMinimumHeight(300)
        self.tabela.setSortingEnabled(True)
        self.vazio = EstadoVazio("Nenhum XML carregado", "Escolha a pasta para ver os XMLs aqui.", "arquivo")
        self._pilha = QStackedLayout()
        self._pilha.addWidget(self.vazio)
        self._pilha.addWidget(self.tabela)
        arquivos = Cartao("Arquivos")
        arquivos.corpo.addLayout(_linha(self.pesquisa, self.filtro_status))
        arquivos.corpo.addLayout(self._pilha, 1)

        self.conteudo.addWidget(pasta)
        self.conteudo.addWidget(grade)
        self.conteudo.addWidget(arquivos, 1)
        self._atualizar_acoes()
        QApplication.instance().aboutToQuit.connect(self._encerrar)

    # --- Estado ---------------------------------------------------------
    @property
    def rodando(self) -> bool:
        return self._tarefa is not None

    @property
    def analise(self) -> "xml_engine.AnaliseXml | None":
        return self._analise

    def _a_renomear(self) -> int:
        if not self._analise:
            return 0
        return sum(1 for i in self._analise.itens if i.estado == xml_engine.PRONTO and i.renomeado is None)

    def _atualizar_acoes(self) -> None:
        ocupado = self.rodando
        self.botao_renomear.setEnabled(not ocupado and self._a_renomear() > 0)
        self.botao_ler.setEnabled(not ocupado and bool(normalizar_pasta(self.campo_pasta.text())))
        for widget in (self.campo_pasta, self.botao_procurar):
            widget.setEnabled(not ocupado)

    # --- Pasta ----------------------------------------------------------
    def _procurar_pasta(self) -> None:
        atual = normalizar_pasta(self.campo_pasta.text())
        inicio = atual if atual and Path(atual).is_dir() else ""
        pasta = QFileDialog.getExistingDirectory(self.contexto.janela, "Selecionar pasta dos XMLs", inicio)
        if pasta:
            self.campo_pasta.setText(str(Path(pasta)))
            self.ler()

    def _ao_editar_pasta(self, _texto: str) -> None:
        if self._analise is not None:  # a lista mostrada era de outra pasta
            self._analise = None
            self._preencher()
            self._atualizar_indicadores()
        self._atualizar_acoes()

    # --- Leitura --------------------------------------------------------
    def ler(self) -> None:
        pasta = normalizar_pasta(self.campo_pasta.text())
        if self.rodando or not pasta:
            return
        self._analise = None
        self._preencher()
        self._atualizar_indicadores()
        self._executar(
            lambda progresso: xml_engine.analisar_pasta(pasta, progresso),
            "Lendo XML {0} de {1}", self._ao_ler,
            lambda mensagem: Modal.informar(self.contexto.janela, "Falha ao ler a pasta", mensagem, "perigo"),
        )

    def _ao_ler(self, analise: "xml_engine.AnaliseXml") -> None:
        self._analise = analise
        self._preencher()
        self._atualizar_indicadores()
        self._atualizar_acoes()
        if not analise.itens:
            Modal.informar(self.contexto.janela, "Nenhum XML encontrado",
                           f"A pasta não tem arquivos .xml (subpastas não são lidas):\n{analise.pasta}", "info")

    # --- Renomeação -----------------------------------------------------
    def renomear(self) -> None:
        analise = self._analise
        if self.rodando or not analise or not self._a_renomear():
            return
        self._executar(
            lambda progresso: xml_engine.renomear(analise, progresso),
            "Renomeando XML {0} de {1}", self._ao_renomear,
            lambda mensagem: Modal.informar(self.contexto.janela, "Falha ao renomear", mensagem, "perigo"),
        )

    def _ao_renomear(self, analise: "xml_engine.AnaliseXml") -> None:
        self._preencher()
        self._atualizar_indicadores()
        feitos = [i for i in analise.itens if i.renomeado is not None]
        falhas = [i for i in analise.itens if i.estado == xml_engine.PRONTO and i.erro]
        self.contexto.log.info("Renomeador de XML: %d renomeados e %d falhas em %s",
                               len(feitos), len(falhas), analise.pasta)
        acoes = [("Fechar", "secundario", False), ("Abrir pasta", "primario", True)]
        if falhas:
            primeiras = "\n".join(f"• {i.origem.name}: {i.erro}" for i in falhas[:3])
            texto = (f"{plural(len(feitos), 'XML renomeado', 'XMLs renomeados')} e "
                     f"{plural(len(falhas), 'falha', 'falhas')}.\n\n{primeiras}")
            abrir = Modal.escolher(self.contexto.janela, "Concluído com falhas", texto, acoes, "perigo")
        else:
            texto = f"{plural(len(feitos), 'XML renomeado', 'XMLs renomeados')} em:\n{analise.pasta}"
            abrir = Modal.escolher(self.contexto.janela, "XMLs renomeados", texto, acoes, "sucesso")
        if abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(analise.pasta)))

    # --- Tarefa em segundo plano ----------------------------------------
    def _executar(self, funcao, formato: str, ao_sucesso, ao_falha) -> None:
        self._formato_progresso, self._ao_sucesso, self._ao_falha = formato, ao_sucesso, ao_falha
        tarefa = Tarefa(funcao, self)
        tarefa.progresso.connect(self._ao_progredir)
        tarefa.concluida.connect(self._ao_concluir)
        tarefa.falhou.connect(self._ao_falhar)
        tarefa.cancelada.connect(self._ao_cancelar)
        self._tarefa = tarefa
        self.progresso.setValue(0)
        self.progresso.show()
        self.rotulo_progresso.setText("Iniciando...")
        self.rotulo_progresso.show()
        tarefa.start()
        self._atualizar_acoes()

    def _ao_progredir(self, feito: int, total: int) -> None:
        self.progresso.setValue(int(feito * 100 / total) if total else 100)
        self.rotulo_progresso.setText(self._formato_progresso.format(feito, total))

    def _liberar(self) -> None:
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.wait()
            tarefa.deleteLater()
        self.progresso.hide()
        self.rotulo_progresso.hide()
        self._atualizar_acoes()

    def _ao_concluir(self, valor) -> None:
        self._liberar()
        if not self._encerrando:
            self._ao_sucesso(valor)

    def _ao_falhar(self, mensagem: str) -> None:
        self._liberar()
        if not self._encerrando:
            self._ao_falha(mensagem)

    def _ao_cancelar(self) -> None:
        self._liberar()
        if self._analise is not None:  # renomeação interrompida: mostra o que já foi feito
            self._preencher()
            self._atualizar_indicadores()

    def parar(self) -> None:
        if self._tarefa is not None:
            self._tarefa.cancelar()
            self.rotulo_progresso.setText("Cancelando...")

    def aguardar(self, limite_ms: int = LIMITE_ESPERA_MS) -> None:
        tarefa = self._tarefa
        if tarefa is not None and not tarefa.wait(limite_ms):
            self.contexto.log.warning("Tarefa não terminou em %d ms ao fechar; interrompida à força", limite_ms)
            tarefa.terminate()
            tarefa.wait()

    def _encerrar(self) -> None:
        self._encerrando = True
        self.parar()
        self.aguardar()

    # --- Tabela ---------------------------------------------------------
    def _preencher(self) -> None:
        tabela = self.tabela
        tabela.setSortingEnabled(False)
        tabela.setRowCount(0)
        for item in self._analise.itens if self._analise else []:
            self._adicionar(item)
        tabela.setSortingEnabled(True)
        self._pilha.setCurrentWidget(tabela if tabela.rowCount() else self.vazio)
        self._filtrar()

    def _adicionar(self, item: "xml_engine.ItemXml") -> None:
        if item.erro:
            status, tom, detalhe = "Erro", "perigo", item.erro
        elif item.estado == xml_engine.SEM_NUMERO:
            status, tom, detalhe = "Sem número", "aviso", TEXTO_SEM_NUMERO
        elif item.estado == xml_engine.NOME_EM_USO:
            status, tom = "Nome em uso", "aviso"
            detalhe = (f"Já existe {item.nome_desejado} nesta pasta. Este XML não foi renomeado, para não "
                       "sobrescrever o outro. Confira se é o mesmo CT-e.")
        elif item.renomeado is not None:
            status, tom, detalhe = "Renomeado", "sucesso", item.aviso or str(item.renomeado)
        elif item.estado == xml_engine.JA_NOMEADO:
            status, tom, detalhe = "Já com o nome", "sucesso", item.aviso
        else:
            status, tom, detalhe = "Pronto", "sucesso", item.aviso
        if item.aviso and tom == "sucesso":
            tom = "aviso"
        novo = item.novo_nome if item.estado == xml_engine.PRONTO else "–"
        numero = item.numero or "–"
        tabela = self.tabela
        linha = tabela.rowCount()
        tabela.insertRow(linha)
        celulas = [(item.origem.name, None), (numero, int(numero) if numero.isdigit() else -1), (novo, None)]
        for coluna, (texto, ordem) in enumerate(celulas):
            tabela.definir_celula(linha, coluna, texto, ordem).setToolTip(detalhe or texto)
        etiqueta = Etiqueta(status, tom, clicavel=bool(detalhe) and tom != "sucesso", dica=detalhe)
        etiqueta.clicada.connect(lambda: Modal.informar(self.contexto.janela, status, detalhe, tom))
        tabela.definir_celula(linha, COL_STATUS, etiqueta, status).setData(PAPEL_REVISAR, item.revisar)

    def _filtrar(self, *_args) -> None:
        busca = self.pesquisa.text().strip().casefold()
        filtro = self.filtro_status.currentIndex()
        tabela = self.tabela
        for linha in range(tabela.rowCount()):
            itens = [tabela.item(linha, c) for c in range(tabela.columnCount())]
            texto = " ".join((i.text() or i.data(Qt.UserRole) or "") for i in itens).casefold()
            revisar = bool(itens[COL_STATUS].data(PAPEL_REVISAR))
            status_ok = (filtro == FILTRO_TODOS or (filtro == FILTRO_REVISAR and revisar)
                         or (filtro == FILTRO_PRONTOS and not revisar))
            tabela.setRowHidden(linha, not (status_ok and busca in texto))

    def _atualizar_indicadores(self) -> None:
        analise = self._analise
        if not analise:
            for indicador in self.indicadores.values():
                indicador.definir_valor("–")
            return
        self.indicadores["xmls"].definir_valor(str(len(analise.itens)))
        self.indicadores["prontos"].definir_valor(str(self._a_renomear()))
        ok = sum(1 for i in analise.itens if i.estado == xml_engine.JA_NOMEADO or i.renomeado is not None)
        self.indicadores["ok"].definir_valor(str(ok))
        self.indicadores["revisar"].definir_valor(str(sum(1 for i in analise.itens if i.revisar)))
