"""Tela do Renomeador de CT-e: escolhe o PDF, mostra os CT-es lidos e grava um arquivo por CT-e."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QStackedLayout, QWidget
from tcm_ui.components import (
    BarraProgresso, Botao, Campo, CampoPesquisa, CampoTexto, Cartao, CartaoIndicador, EstadoVazio, Etiqueta,
    GradeResponsiva, Modal, Pagina, Selecao, Tabela, Texto, ZonaArquivo,
)
from tcm_ui.modulo import Contexto
from tcm_ui.themes import ESPACO

from renomeador_cte import cte_engine
from renomeador_cte.worker import Tarefa

COLUNAS = ["Número", "Emissão", "Tomador", "Páginas", "Arquivo", "Status"]
COL_NUMERO, COL_EMISSAO, COL_TOMADOR, COL_PAGINAS, COL_ARQUIVO, COL_STATUS = range(6)
FILTROS = ["Todos os status", "Prontos", "Para revisar"]
FILTRO_TODOS, FILTRO_PRONTOS, FILTRO_REVISAR = range(3)
PAPEL_REVISAR = Qt.UserRole + 20  # no item da coluna Status: a linha precisa de revisão (Qt.UserRole é do texto)

TEXTO_NAO_IDENTIFICADAS = "Estas páginas não têm chave nem número de CT-e. Foram reunidas em um arquivo à parte."
LIMITE_ESPERA_MS = 10_000  # ao fechar o programa, quanto esperar a tarefa antes de derrubá-la


def normalizar_pasta(texto: str, pdf: Path | None) -> str:
    """Pasta digitada pelo usuário: sem aspas (cópia do Explorer) e, se relativa, a partir da pasta do PDF."""
    limpo = texto.strip().strip('"').strip()
    if not limpo:
        return ""
    pasta = Path(limpo)
    if not pasta.is_absolute() and pdf is not None:
        pasta = pdf.parent / pasta
    return str(pasta)


def plural(quantidade: int, singular: str, plural_: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural_}"


def _linha(principal: QWidget, *outros: QWidget) -> QHBoxLayout:
    """Linha horizontal em que o primeiro widget ocupa o espaço que sobra."""
    caixa = QHBoxLayout()
    caixa.setSpacing(ESPACO["sm"])
    caixa.addWidget(principal, 1)
    for widget in outros:
        caixa.addWidget(widget)
    return caixa


class TelaRenomear(Pagina):
    """Página única do Renomeador (o antigo RenamePage, sem janela, barra lateral e cabeçalho)."""

    def __init__(self, contexto: Contexto):
        super().__init__()
        self.contexto = contexto
        self._resultado: cte_engine.AnalysisResult | None = None
        self._itens: list[cte_engine.ExportItem] | None = None  # saída da última geração
        self._tarefa: Tarefa | None = None
        self._formato_progresso = ""
        self._ao_sucesso = None
        self._ao_falha = None
        self._pasta_do_usuario = False
        self._nome_pdf = ""
        self._encerrando = False

        # --- 1. Arquivo ---------------------------------------------------
        self.zona = ZonaArquivo("Arraste o PDF para cá", "ou clique para selecionar no computador",
                                "Selecionar PDF")
        self.zona.procurar.connect(self._procurar_pdf)
        self.zona.arquivo_solto.connect(self.analisar)
        self.progresso = BarraProgresso()
        self.rotulo_progresso = Texto("", "dica")
        self.progresso.hide()
        self.rotulo_progresso.hide()
        arquivo = Cartao("1. Arquivo", "PDF com um ou mais CT-es.")
        arquivo.corpo.addWidget(self.zona, 1)
        arquivo.corpo.addWidget(self.progresso)
        arquivo.corpo.addWidget(self.rotulo_progresso)

        # --- 2. Destino ---------------------------------------------------
        self.campo_pasta = CampoTexto("Selecione a pasta de destino")
        self.campo_pasta.textEdited.connect(self._ao_editar_pasta)
        self.campo_pasta.textChanged.connect(self.campo_pasta.setToolTip)
        self.botao_procurar = Botao("Procurar", "secundario", icone="pasta")
        self.botao_procurar.clicked.connect(self._procurar_pasta)
        linha_pasta = QWidget()
        caixa = _linha(self.campo_pasta, self.botao_procurar)
        caixa.setContentsMargins(0, 0, 0, 0)
        linha_pasta.setLayout(caixa)

        self.campo_prefixo = CampoTexto("Sem prefixo")
        self.campo_prefixo.textChanged.connect(self._ao_mudar_prefixo)
        self.campo_prefixo_field = Campo("Prefixo do nome (opcional)", self.campo_prefixo, self._dica_exemplo())
        self.botao_gerar = Botao("Separar e renomear", "primario", "lg", "tesoura")
        self.botao_gerar.clicked.connect(self.gerar)
        destino = Cartao("2. Destino", "Um PDF será criado para cada CT-e. O arquivo original não é alterado.")
        destino.corpo.addWidget(Campo("Pasta de destino", linha_pasta))
        destino.corpo.addWidget(self.campo_prefixo_field)
        destino.corpo.addStretch(1)
        destino.corpo.addWidget(self.botao_gerar)

        topo = GradeResponsiva(320)
        topo.adicionar(arquivo)
        topo.adicionar(destino)

        # --- Indicadores --------------------------------------------------
        self.indicadores = {
            "paginas": CartaoIndicador("Páginas", "–", "arquivo", "neutro"),
            "ctes": CartaoIndicador("CT-es", "–", "camadas", "primaria"),
            "prontos": CartaoIndicador("Prontos", "–", "check_circulo", "sucesso"),
            "revisar": CartaoIndicador("Para revisar", "–", "alerta", "perigo"),
        }
        grade = GradeResponsiva(200)
        for indicador in self.indicadores.values():
            grade.adicionar(indicador)

        # --- Documentos ---------------------------------------------------
        self.pesquisa = CampoPesquisa("Pesquisar por número, tomador ou arquivo")
        self.pesquisa.textChanged.connect(self._filtrar)
        self.filtro_status = Selecao(FILTROS)
        self.filtro_status.setMinimumWidth(180)
        self.filtro_status.currentIndexChanged.connect(self._filtrar)
        self.tabela = Tabela(COLUNAS, coluna_flexivel=COL_TOMADOR)
        self.tabela.setMinimumHeight(300)
        self.tabela.setSortingEnabled(True)
        self.vazio = EstadoVazio("Nenhum documento carregado", "Selecione um PDF para ver os CT-es aqui.", "arquivo")
        self._pilha = QStackedLayout()
        self._pilha.addWidget(self.vazio)
        self._pilha.addWidget(self.tabela)
        documentos = Cartao("Documentos")
        documentos.corpo.addLayout(_linha(self.pesquisa, self.filtro_status))
        documentos.corpo.addLayout(self._pilha, 1)

        self.conteudo.addWidget(topo)
        self.conteudo.addWidget(grade)
        self.conteudo.addWidget(documentos, 1)
        self._atualizar_acoes()

        # Ao fechar o programa a tarefa tem de terminar antes de o processo acabar (a confirmação já vem do
        # pode_fechar na janela). A conexão com um método de QObject some sozinha quando a tela é destruída.
        QApplication.instance().aboutToQuit.connect(self._encerrar)

    # --- Estado ---------------------------------------------------------
    @property
    def rodando(self) -> bool:
        return self._tarefa is not None

    @property
    def resultado(self) -> "cte_engine.AnalysisResult | None":
        return self._resultado

    @property
    def pendente(self) -> bool:
        """Há CT-es lidos que ainda não foram gravados."""
        return bool(self._resultado and self._resultado.documents and self._itens is None)

    def _atualizar_acoes(self) -> None:
        ocupado = self.rodando
        tem_cte = bool(self._resultado and self._resultado.documents)
        self.botao_gerar.setEnabled(not ocupado and tem_cte and bool(self._pasta_destino()))
        for widget in (self.zona, self.campo_pasta, self.botao_procurar, self.campo_prefixo):
            widget.setEnabled(not ocupado)

    # --- Escolha de arquivo e pasta -------------------------------------
    def _procurar_pdf(self) -> None:
        if self.rodando:
            return
        caminho, _ = QFileDialog.getOpenFileName(self.contexto.janela, "Selecionar PDF", "", "Arquivos PDF (*.pdf)")
        if caminho:
            self.analisar(caminho)

    def _procurar_pasta(self) -> None:
        atual = self._pasta_destino()
        inicio = atual if atual and Path(atual).exists() else ""
        pasta = QFileDialog.getExistingDirectory(self.contexto.janela, "Selecionar pasta de destino", inicio)
        if pasta:
            self.campo_pasta.setText(str(Path(pasta)))
            self._pasta_do_usuario = True
            self._atualizar_acoes()

    def _pasta_destino(self) -> str:
        return normalizar_pasta(self.campo_pasta.text(), self._resultado.source if self._resultado else None)

    def _ao_editar_pasta(self, _texto: str) -> None:
        self._pasta_do_usuario = True
        self._atualizar_acoes()

    def _dica_exemplo(self) -> str:
        exemplo = self._resultado.documents[0].number if self._resultado and self._resultado.documents else "774"
        return f"Exemplo de nome: {cte_engine.sanitize_prefix(self.campo_prefixo.text())}{exemplo}.pdf"

    def _ao_mudar_prefixo(self, _texto: str) -> None:
        self.campo_prefixo_field.definir_dica(self._dica_exemplo())
        self._itens = None
        self._preencher()
        self._atualizar_indicadores()

    # --- Leitura --------------------------------------------------------
    def analisar(self, caminho: str) -> None:
        if self.rodando:
            return
        origem = Path(caminho)
        self._nome_pdf = origem.name
        self._resultado = None
        self._itens = None
        self._preencher()
        self._atualizar_indicadores()
        self.zona.definir_arquivo(origem.name, "Analisando...", "Trocar arquivo")
        if not self._pasta_do_usuario:
            self.campo_pasta.setText(str(origem.parent / f"CTEs_{origem.stem}"))
        self._executar(
            lambda progresso: cte_engine.analyze_pdf(origem, progresso),
            "Lendo página {0} de {1}", self._ao_analisar, self._ao_falhar_analise,
        )

    def _ao_analisar(self, resultado: "cte_engine.AnalysisResult") -> None:
        self._resultado = resultado
        self.zona.definir_arquivo(
            resultado.source.name,
            f"{plural(resultado.total_pages, 'página', 'páginas')} · "
            f"{plural(len(resultado.documents), 'CT-e', 'CT-es')}",
            "Trocar arquivo",
        )
        self.campo_prefixo_field.definir_dica(self._dica_exemplo())
        self._preencher()
        self._atualizar_indicadores()
        self._atualizar_acoes()
        if not resultado.documents:
            Modal.informar(
                self.contexto.janela, "Nenhum CT-e encontrado",
                "Não foi possível ler chave de acesso ou número neste PDF. Se ele for digitalizado "
                "(imagem), é preciso um PDF com texto: o reconhecimento por OCR não é suportado.",
                "perigo",
            )

    def _ao_falhar_analise(self, mensagem: str) -> None:
        self.zona.definir_arquivo("Não foi possível ler o arquivo", mensagem, "Selecionar outro PDF")
        Modal.informar(self.contexto.janela, "Falha ao ler o PDF", mensagem, "perigo")

    # --- Geração --------------------------------------------------------
    def gerar(self) -> None:
        resultado = self._resultado
        pasta = self._pasta_destino()
        if self.rodando or not resultado or not resultado.documents or not pasta:
            return
        prefixo = self.campo_prefixo.text()
        conflito = cte_engine.ON_CONFLICT_KEEP_BOTH
        existentes = cte_engine.find_existing_outputs(resultado, pasta, prefixo)
        if existentes:
            escolha = Modal.escolher(
                self.contexto.janela, "Arquivos já existem",
                f"{plural(len(existentes), 'arquivo já existe', 'arquivos já existem')} na pasta de "
                "destino. Deseja substituí-los ou manter os atuais e salvar os novos com outro nome?",
                [("Cancelar", "secundario", None), ("Substituir", "perigo", "substituir"),
                 ("Manter ambos", "primario", "manter")],
                "info",
            )
            if escolha not in ("substituir", "manter"):
                return
            if escolha == "substituir":
                conflito = cte_engine.ON_CONFLICT_REPLACE
        self._executar(
            lambda progresso: cte_engine.export_documents(resultado, pasta, prefixo, conflito, progresso),
            "Gerando arquivo {0} de {1}", lambda itens: self._ao_gerar(itens, Path(pasta)),
            lambda mensagem: Modal.informar(self.contexto.janela, "Falha ao gerar os arquivos", mensagem, "perigo"),
        )

    def _ao_gerar(self, itens: "list[cte_engine.ExportItem]", pasta: Path) -> None:
        self._itens = itens
        self._preencher()
        self._atualizar_indicadores()
        falhas = [item for item in itens if item.error]
        salvos = len(itens) - len(falhas)
        acoes = [("Fechar", "secundario", False), ("Abrir pasta", "primario", True)]
        if falhas:
            primeiras = "\n".join(f"• {item.path.name}: {item.error}" for item in falhas[:3])
            texto = (f"{plural(salvos, 'arquivo gerado', 'arquivos gerados')} e "
                     f"{plural(len(falhas), 'falha', 'falhas')}.\n\n{primeiras}")
            abrir = Modal.escolher(self.contexto.janela, "Concluído com falhas", texto, acoes, "perigo")
        else:
            texto = f"{plural(salvos, 'arquivo gerado', 'arquivos gerados')} em:\n{pasta}"
            abrir = Modal.escolher(self.contexto.janela, "Arquivos gerados", texto, acoes, "sucesso")
        if abrir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))

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
        """Fim da tarefa: espera a thread acabar de vez antes de soltá-la e volta a tela ao estado livre."""
        tarefa, self._tarefa = self._tarefa, None
        if tarefa is not None:
            tarefa.wait()  # os sinais saem de dentro da thread, que ainda está terminando
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
        """Cancelada pelo usuário ou pelo fechamento: só limpa o estado, sem aviso."""
        self._liberar()
        if self._resultado is None:  # a leitura foi interrompida
            self.zona.definir_arquivo(self._nome_pdf, "Leitura cancelada", "Selecionar outro PDF")

    def parar(self) -> None:
        if self._tarefa is not None:
            self._tarefa.cancelar()
            self.rotulo_progresso.setText("Cancelando...")

    def aguardar(self, limite_ms: int = LIMITE_ESPERA_MS) -> None:
        """Espera a tarefa terminar; presa além do limite (ex.: página enorme), é derrubada à força."""
        tarefa = self._tarefa
        if tarefa is not None and not tarefa.wait(limite_ms):
            self.contexto.log.warning("Tarefa não terminou em %d ms ao fechar; interrompida à força", limite_ms)
            tarefa.terminate()  # a gravação usa .part + os.replace: o PDF final nunca fica pela metade
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
        resultado = self._resultado
        if resultado:
            nomes = cte_engine.plan_filenames(resultado.documents, self.campo_prefixo.text())
            salvos = {id(i.document): i for i in self._itens or [] if i.document}
            for documento, nome in zip(resultado.documents, nomes):
                self._adicionar_documento(documento, nome, salvos.get(id(documento)))
            if resultado.unidentified_pages:
                self._adicionar_nao_identificadas(resultado.unidentified_pages)
        tabela.setSortingEnabled(True)
        self._pilha.setCurrentWidget(tabela if tabela.rowCount() else self.vazio)
        self._filtrar()

    def _adicionar_documento(self, documento, nome: str, item: "cte_engine.ExportItem | None") -> None:
        if item:
            nome = item.path.name
        if item and item.error:
            status, tom, detalhe, revisar = "Erro", "perigo", item.error, True
        elif documento.needs_review:
            status, tom, detalhe, revisar = "Revisar", "aviso", "\n".join(documento.warnings), True
        elif item:
            status, tom, detalhe, revisar = "Salvo", "sucesso", str(item.path), False
        else:
            status, tom, detalhe, revisar = "Pronto", "sucesso", "", False
        numero = documento.number
        self._adicionar_linha(
            [(numero, int(numero) if numero.isdigit() else numero),
             (documento.issue_date, "".join(reversed(documento.issue_date.split("/")))),
             (documento.payer, None),
             (", ".join(str(pagina + 1) for pagina in documento.pages), documento.pages[0]),
             (nome, None)],
            status, tom, detalhe, revisar,
        )

    def _adicionar_nao_identificadas(self, paginas: list[int]) -> None:
        item = next((i for i in self._itens or [] if i.document is None), None)
        nome = item.path.name if item else f"{cte_engine.UNIDENTIFIED_STEM}.pdf"
        if item and item.error:
            status, tom, detalhe = "Erro", "perigo", item.error
        else:
            status, tom, detalhe = "Revisar", "aviso", TEXTO_NAO_IDENTIFICADAS
        self._adicionar_linha(
            [("–", -1), ("–", ""), ("Páginas não identificadas", None),
             (", ".join(str(pagina + 1) for pagina in paginas), paginas[0]), (nome, None)],
            status, tom, detalhe, True,
        )

    def _adicionar_linha(self, celulas: list, status: str, tom: str, detalhe: str, revisar: bool) -> None:
        tabela = self.tabela
        linha = tabela.rowCount()
        tabela.insertRow(linha)
        for coluna, (texto, ordem) in enumerate(celulas):
            tabela.definir_celula(linha, coluna, texto, ordem).setToolTip(detalhe or texto)
        etiqueta = Etiqueta(status, tom, clicavel=bool(detalhe) and tom != "sucesso", dica=detalhe)
        etiqueta.clicada.connect(lambda: Modal.informar(self.contexto.janela, status, detalhe, tom))
        tabela.definir_celula(linha, COL_STATUS, etiqueta, status).setData(PAPEL_REVISAR, revisar)

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
        resultado = self._resultado
        if not resultado:
            for indicador in self.indicadores.values():
                indicador.definir_valor("–")
            return
        itens = self._itens or []
        com_falha = {id(i.document) for i in itens if i.error and i.document}
        nao_identificadas_falhou = any(i.error and i.document is None for i in itens)
        revisar = sum(1 for d in resultado.documents if d.needs_review or id(d) in com_falha)
        self.indicadores["paginas"].definir_valor(str(resultado.total_pages))
        self.indicadores["ctes"].definir_valor(str(len(resultado.documents)))
        self.indicadores["prontos"].definir_valor(str(len(resultado.documents) - revisar))
        self.indicadores["revisar"].definir_valor(
            str(revisar + (1 if resultado.unidentified_pages or nao_identificadas_falhou else 0)))
