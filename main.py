"""Renomeador de CT-e: separa um PDF com vários CT-es e nomeia cada arquivo pelo número."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QThread, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QStackedLayout,
    QStackedWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import cte_engine as engine
from components import (
    BADGE_TONE_ROLE,
    Button,
    Card,
    CheckBox,
    ColorSwatch,
    ComboBox,
    DataTable,
    DropZone,
    EmptyState,
    FormField,
    Header,
    Modal,
    ProgressBar,
    ResponsiveRow,
    SearchInput,
    Sidebar,
    SortableItem,
    StatCard,
    TextArea,
    TextInput,
    text_label,
    themed_icon,
)
from themes import SPACING, default_font, theme

APP_NAME = "Renomeador de CT-e"

COL_NUMBER, COL_DATE, COL_PAYER, COL_PAGES, COL_FILE, COL_STATUS = range(6)
TABLE_COLUMNS = ["Número", "Emissão", "Tomador", "Páginas", "Arquivo", "Status"]
FILTER_ALL, FILTER_READY, FILTER_REVIEW = 0, 1, 2
REVIEW_ROW_ROLE = Qt.ItemDataRole.UserRole + 20


class TaskThread(QThread):
    """Executa uma tarefa fora da thread da interface e informa o progresso."""

    progressed = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[Callable[[int, int], None]], object], parent=None):
        super().__init__(parent)
        self._task = task

    def run(self) -> None:
        try:
            self.succeeded.emit(self._task(self.progressed.emit))
        except engine.PdfAnalysisError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # a interface precisa sempre sair do estado "ocupado"
            self.failed.emit(f"Erro inesperado: {exc}")


def page_scroll_area(content: QWidget) -> QScrollArea:
    content.setProperty("surface", "content")
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content)
    return scroll


def plural(count: int, singular: str, plural_form: str) -> str:
    return f"{count} {singular if count == 1 else plural_form}"


class RenamePage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("surface", "content")
        self._result: engine.AnalysisResult | None = None
        self._export_items: list[engine.ExportItem] | None = None
        self._thread: TaskThread | None = None
        self._folder_chosen_by_user = False
        self._build_ui()
        self._refresh_actions()

    # ------------------------------------------------------------ Construção
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        margin = SPACING["xl"]
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(SPACING["lg"])

        top_row = ResponsiveRow(280, (2, 1))
        top_row.add(self._build_file_card())
        top_row.add(self._build_output_card())
        layout.addWidget(top_row)

        stats = ResponsiveRow(135, (4, 2, 1))
        self._stat_pages = StatCard("Páginas", "file-text")
        self._stat_documents = StatCard("CT-es", "layers", "primary")
        self._stat_ready = StatCard("Prontos", "check-circle", "success")
        self._stat_review = StatCard("Para revisar", "alert-circle", "danger")
        for card in (self._stat_pages, self._stat_documents, self._stat_ready, self._stat_review):
            stats.add(card)
        layout.addWidget(stats)
        layout.addWidget(self._build_table_card(), 1)

    def _build_file_card(self) -> Card:
        card = Card("1. Arquivo", "PDF com um ou mais CT-es.")
        self._drop_zone = DropZone(
            "Arraste o PDF para cá", "ou clique para selecionar no computador", "Selecionar PDF"
        )
        self._drop_zone.browse_requested.connect(self._browse_pdf)
        self._drop_zone.file_dropped.connect(self._start_analysis)
        card.body.addWidget(self._drop_zone, 1)

        self._progress = ProgressBar()
        self._progress_label = text_label("", "caption")
        self._progress.hide()
        self._progress_label.hide()
        card.body.addWidget(self._progress)
        card.body.addWidget(self._progress_label)
        return card

    def _build_output_card(self) -> Card:
        card = Card("2. Destino", "Um PDF será criado para cada CT-e. O arquivo original não é alterado.")

        self._folder_input = TextInput("Selecione a pasta de destino")
        self._folder_input.textEdited.connect(self._on_folder_edited)
        self._folder_input.textChanged.connect(self._folder_input.setToolTip)
        self._browse_folder_button = Button("Procurar", "secondary", "md", "folder")
        self._browse_folder_button.clicked.connect(self._browse_folder)
        folder_row = QWidget()
        row = QHBoxLayout(folder_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING["sm"])
        row.addWidget(self._folder_input, 1)
        row.addWidget(self._browse_folder_button)
        card.body.addWidget(FormField("Pasta de destino", folder_row))

        self._prefix_input = TextInput("Sem prefixo")
        self._prefix_input.textChanged.connect(self._on_prefix_changed)
        self._prefix_field = FormField(
            "Prefixo do nome (opcional)", self._prefix_input, self._prefix_helper()
        )
        card.body.addWidget(self._prefix_field)
        card.body.addStretch()

        self._export_button = Button("Separar e renomear", "primary", "lg", "scissors")
        self._export_button.clicked.connect(self._start_export)
        card.body.addWidget(self._export_button)
        return card

    def _build_table_card(self) -> Card:
        card = Card()
        toolbar = ResponsiveRow(170, (3, 1), SPACING["sm"])
        title = text_label("Documentos", "section")
        self._search = SearchInput("Pesquisar por número, tomador ou arquivo")
        self._search.textChanged.connect(self._apply_filters)
        self._status_filter = ComboBox(["Todos os status", "Prontos", "Para revisar"])
        self._status_filter.currentIndexChanged.connect(self._apply_filters)
        toolbar.add(title, 2)
        toolbar.add(self._search, 3)
        toolbar.add(self._status_filter, 1)
        card.body.addWidget(toolbar)

        self._table = DataTable(TABLE_COLUMNS, stretch_column=COL_PAYER, badge_column=COL_STATUS)
        self._table.setMinimumHeight(300)
        self._table.setSortingEnabled(True)
        self._empty_state = EmptyState(
            "file-text", "Nenhum documento carregado", "Selecione um PDF para ver os CT-es aqui."
        )
        self._table_stack = QStackedLayout()
        self._table_stack.addWidget(self._empty_state)
        self._table_stack.addWidget(self._table)
        card.body.addLayout(self._table_stack, 1)
        return card

    # ------------------------------------------------------------ Seleção
    def _browse_pdf(self) -> None:
        if self._is_busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar PDF", "", "Arquivos PDF (*.pdf)")
        if path:
            self._start_analysis(path)

    def _browse_folder(self) -> None:
        current = self._folder_input.text().strip()
        start = current if current and Path(current).exists() else ""
        path = QFileDialog.getExistingDirectory(self, "Selecionar pasta de destino", start)
        if path:
            self._folder_input.setText(str(Path(path)))
            self._folder_chosen_by_user = True
            self._refresh_actions()

    def _on_folder_edited(self, _text: str) -> None:
        self._folder_chosen_by_user = True
        self._refresh_actions()

    def _prefix_helper(self) -> str:
        example = self._result.documents[0].number if self._result and self._result.documents else "774"
        prefix = engine.sanitize_prefix(self._prefix_input.text())
        return f"Exemplo de nome: {prefix}{example}.pdf"

    def _on_prefix_changed(self, _text: str) -> None:
        self._prefix_field.set_helper(self._prefix_helper())
        self._export_items = None
        self._populate_table()
        self._update_stats()

    # ------------------------------------------------------------ Análise
    def _start_analysis(self, path: str) -> None:
        if self._is_busy():
            return
        source = Path(path)
        self._result = None
        self._export_items = None
        self._populate_table()
        self._update_stats()
        self._drop_zone.set_file(source.name, "Analisando...", "Trocar arquivo")
        if not self._folder_chosen_by_user:
            self._folder_input.setText(str(source.parent / f"CTEs_{source.stem}"))
        self._run_task(
            lambda progress: engine.analyze_pdf(source, progress),
            "Lendo página {0} de {1}",
            self._on_analysis_done,
            self._on_analysis_failed,
        )

    def _on_analysis_done(self, result: engine.AnalysisResult) -> None:
        self._result = result
        self._refresh_actions()
        self._drop_zone.set_file(
            result.source.name,
            f"{plural(result.total_pages, 'página', 'páginas')} · "
            f"{plural(len(result.documents), 'CT-e', 'CT-es')}",
            "Trocar arquivo",
        )
        self._prefix_field.set_helper(self._prefix_helper())
        self._populate_table()
        self._update_stats()
        if not result.documents:
            Modal.ask(
                self,
                "Nenhum CT-e encontrado",
                "Não foi possível ler chave de acesso ou número neste PDF. Se ele for digitalizado "
                "(imagem), é preciso um PDF com texto: o reconhecimento por OCR não é suportado.",
                "danger",
                [("ok", "Entendi", "primary")],
            )

    def _on_analysis_failed(self, message: str) -> None:
        self._drop_zone.set_file("Não foi possível ler o arquivo", message, "Selecionar outro PDF")
        Modal.ask(self, "Falha ao ler o PDF", message, "danger", [("ok", "Entendi", "primary")])

    # ------------------------------------------------------------ Exportação
    def _start_export(self) -> None:
        result = self._result
        folder = self._folder_input.text().strip()
        if self._is_busy() or not result or not result.documents or not folder:
            return
        prefix = self._prefix_input.text()
        on_conflict = engine.ON_CONFLICT_KEEP_BOTH
        existing = engine.find_existing_outputs(result, folder, prefix)
        if existing:
            choice = Modal.ask(
                self,
                "Arquivos já existem",
                f"{plural(len(existing), 'arquivo já existe', 'arquivos já existem')} na pasta de "
                "destino. Deseja substituí-los ou manter os atuais e salvar os novos com outro nome?",
                "info",
                [
                    ("cancel", "Cancelar", "secondary"),
                    ("replace", "Substituir", "danger"),
                    ("keep", "Manter ambos", "primary"),
                ],
            )
            if choice not in ("replace", "keep"):
                return
            if choice == "replace":
                on_conflict = engine.ON_CONFLICT_REPLACE

        self._run_task(
            lambda progress: engine.export_documents(result, folder, prefix, on_conflict, progress),
            "Gerando arquivo {0} de {1}",
            lambda items: self._on_export_done(items, Path(folder)),
            lambda message: Modal.ask(
                self, "Falha ao gerar os arquivos", message, "danger", [("ok", "Entendi", "primary")]
            ),
        )

    def _on_export_done(self, items: list[engine.ExportItem], folder: Path) -> None:
        self._export_items = items
        self._populate_table()
        self._update_stats()
        failures = [item for item in items if item.error]
        saved = len(items) - len(failures)
        actions = [("close", "Fechar", "secondary"), ("open", "Abrir pasta", "primary")]
        if failures:
            first_errors = "\n".join(f"• {item.path.name}: {item.error}" for item in failures[:3])
            message = (
                f"{plural(saved, 'arquivo gerado', 'arquivos gerados')} e "
                f"{plural(len(failures), 'falha', 'falhas')}.\n\n{first_errors}"
            )
            choice = Modal.ask(self, "Concluído com falhas", message, "danger", actions)
        else:
            message = f"{plural(saved, 'arquivo gerado', 'arquivos gerados')} em:\n{folder}"
            choice = Modal.ask(self, "Arquivos gerados", message, "success", actions)
        if choice == "open":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------ Execução
    def _run_task(self, task, progress_format: str, on_success, on_failure) -> None:
        self._thread = TaskThread(task, self)
        self._thread.progressed.connect(
            lambda done, total: self._set_progress(done, total, progress_format)
        )
        self._thread.succeeded.connect(lambda value: self._task_finished(on_success, value))
        self._thread.failed.connect(lambda message: self._task_finished(on_failure, message))
        self._progress.setValue(0)
        self._progress.show()
        self._progress_label.setText("Iniciando...")
        self._progress_label.show()
        self._thread.start()
        self._refresh_actions()

    def _set_progress(self, done: int, total: int, label_format: str) -> None:
        self._progress.setValue(int(done * 100 / total) if total else 100)
        self._progress_label.setText(label_format.format(done, total))

    def _task_finished(self, callback, value) -> None:
        thread, self._thread = self._thread, None
        thread.wait()
        thread.deleteLater()
        self._progress.hide()
        self._progress_label.hide()
        self._refresh_actions()
        callback(value)

    def _is_busy(self) -> bool:
        return self._thread is not None

    def _refresh_actions(self) -> None:
        busy = self._is_busy()
        has_documents = bool(self._result and self._result.documents)
        has_folder = bool(self._folder_input.text().strip())
        self._export_button.setEnabled(not busy and has_documents and has_folder)
        self._drop_zone.setEnabled(not busy)
        for widget in (self._folder_input, self._browse_folder_button, self._prefix_input):
            widget.setEnabled(not busy)

    def wait_for_task(self) -> None:
        if self._thread is not None:
            self._thread.wait()

    # ------------------------------------------------------------ Tabela
    def _populate_table(self) -> None:
        table = self._table
        table.setSortingEnabled(False)
        table.setRowCount(0)
        result = self._result
        if result:
            names = engine.plan_filenames(result.documents, self._prefix_input.text())
            saved = {id(i.document): i for i in self._export_items or [] if i.document}
            for document, name in zip(result.documents, names):
                self._add_document_row(document, name, saved.get(id(document)))
            if result.unidentified_pages:
                self._add_unidentified_row(result.unidentified_pages)
        table.setSortingEnabled(True)
        self._table_stack.setCurrentWidget(table if table.rowCount() else self._empty_state)
        self._apply_filters()

    def _add_document_row(self, document, name: str, item: engine.ExportItem | None) -> None:
        if item:
            name = item.path.name
        if item and item.error:
            status, tone, tip, review = "Erro", "danger", item.error, True
        elif document.needs_review:
            status, tone, tip, review = "Revisar", "info", "\n".join(document.warnings), True
        elif item:
            status, tone, tip, review = "Salvo", "success", str(item.path), False
        else:
            status, tone, tip, review = "Pronto", "success", "", False
        pages = ", ".join(str(page + 1) for page in document.pages)
        self._add_row(
            [
                SortableItem(document.number, int(document.number)),
                SortableItem(document.issue_date, "".join(reversed(document.issue_date.split("/")))),
                SortableItem(document.payer),
                SortableItem(pages, document.pages[0]),
                SortableItem(name),
            ],
            status, tone, tip, review,
        )

    def _add_unidentified_row(self, pages: list[int]) -> None:
        item = next((i for i in self._export_items or [] if i.document is None), None)
        name = item.path.name if item else f"{engine.UNIDENTIFIED_STEM}.pdf"
        if item and item.error:
            status, tone, tip = "Erro", "danger", item.error
        else:
            status, tone = "Revisar", "info"
            tip = "Estas páginas não têm chave nem número de CT-e. Foram reunidas em um arquivo à parte."
        self._add_row(
            [
                SortableItem("–", -1),
                SortableItem("–", ""),
                SortableItem("Páginas não identificadas"),
                SortableItem(", ".join(str(page + 1) for page in pages), pages[0]),
                SortableItem(name),
            ],
            status, tone, tip, True,
        )

    def _add_row(self, items: list[QTableWidgetItem], status: str, tone: str, tip: str, review: bool) -> None:
        table = self._table
        row = table.rowCount()
        table.insertRow(row)
        status_item = SortableItem(status)
        status_item.setData(BADGE_TONE_ROLE, tone)
        status_item.setData(REVIEW_ROW_ROLE, review)
        for column, item in enumerate([*items, status_item]):
            item.setToolTip(tip or item.text())
            table.setItem(row, column, item)

    def _apply_filters(self, *_args) -> None:
        query = self._search.text().strip().casefold()
        filter_index = self._status_filter.currentIndex()
        for row in range(self._table.rowCount()):
            text = " ".join(
                self._table.item(row, column).text() for column in range(self._table.columnCount())
            ).casefold()
            review = bool(self._table.item(row, COL_STATUS).data(REVIEW_ROW_ROLE))
            matches_status = (
                filter_index == FILTER_ALL
                or (filter_index == FILTER_REVIEW and review)
                or (filter_index == FILTER_READY and not review)
            )
            self._table.setRowHidden(row, not (matches_status and query in text))

    def _update_stats(self) -> None:
        result = self._result
        if not result:
            for card in (self._stat_pages, self._stat_documents, self._stat_ready, self._stat_review):
                card.set_value("–")
            return
        failed_ids = {id(i.document) for i in self._export_items or [] if i.error and i.document}
        unidentified_failed = any(
            i.error and i.document is None for i in self._export_items or []
        )
        review = sum(1 for d in result.documents if d.needs_review or id(d) in failed_ids)
        self._stat_pages.set_value(result.total_pages)
        self._stat_documents.set_value(len(result.documents))
        self._stat_ready.set_value(len(result.documents) - review)
        self._stat_review.set_value(
            review + (1 if result.unidentified_pages or unidentified_failed else 0)
        )


class DesignSystemPage(QWidget):
    """Vitrine com todos os componentes, para consulta e conferência visual."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("surface", "content")
        layout = QVBoxLayout(self)
        margin = SPACING["xl"]
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(SPACING["lg"])
        layout.addWidget(self._colors_card())
        layout.addWidget(self._buttons_card())

        row = ResponsiveRow(280, (2, 1))
        row.add(self._form_card())
        row.add(self._feedback_card())
        layout.addWidget(row)
        layout.addWidget(self._table_card())
        layout.addStretch()

    def _colors_card(self) -> Card:
        card = Card("Cores", "Identidade fixa e neutros que mudam conforme o tema.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(SPACING["md"])
        grid.setVerticalSpacing(SPACING["sm"])
        swatches = [
            ("primary", "Azul"), ("primary_hover", "Azul hover"), ("danger", "Vermelho"),
            ("success", "Verde"), ("bg", "Fundo"), ("bg_secondary", "Fundo secundário"),
            ("card", "Card"), ("text", "Texto"), ("text_muted", "Texto suave"), ("border", "Borda"),
        ]
        for index, (token, label) in enumerate(swatches):
            grid.addWidget(ColorSwatch(token, label), index // 5, index % 5)
        card.body.addLayout(grid)
        return card

    def _buttons_card(self) -> Card:
        card = Card("Botões", "Tamanhos de 32, 40 e 48 px, com variantes e estados.")
        sizes = QHBoxLayout()
        sizes.setSpacing(SPACING["sm"])
        sizes.addWidget(Button("Pequeno", "primary", "sm"))
        sizes.addWidget(Button("Padrão", "primary", "md", "check"))
        sizes.addWidget(Button("Grande", "primary", "lg", "upload"))
        sizes.addStretch()
        card.body.addLayout(sizes)

        variants = QHBoxLayout()
        variants.setSpacing(SPACING["sm"])
        variants.addWidget(Button("Secundário", "secondary", "md", "folder"))
        variants.addWidget(Button("Excluir", "danger", "md", "trash"))
        disabled = Button("Desativado", "primary", "md")
        disabled.setEnabled(False)
        variants.addWidget(disabled)
        open_modal = Button("Abrir modal", "secondary", "md")
        open_modal.clicked.connect(self._show_modal)
        variants.addWidget(open_modal)
        variants.addStretch()
        card.body.addLayout(variants)
        return card

    def _form_card(self) -> Card:
        card = Card("Formulário")
        card.body.addWidget(FormField("Nome", TextInput("Digite o nome"), "Texto de apoio do campo."))
        card.body.addWidget(FormField("Pesquisa", SearchInput()))
        card.body.addWidget(FormField("Seleção", ComboBox(["Opção 1", "Opção 2", "Opção 3"])))
        card.body.addWidget(FormField("Observações", TextArea("Digite um texto mais longo")))
        invalid = TextInput()
        invalid.setText("Valor inválido")
        invalid.set_invalid(True)
        card.body.addWidget(FormField("Campo com erro", invalid))
        disabled = TextInput("Campo desativado")
        disabled.setEnabled(False)
        card.body.addWidget(FormField("Desativado", disabled))
        return card

    def _feedback_card(self) -> Card:
        card = Card("Seleção e progresso")
        checked = CheckBox("Opção marcada")
        checked.setChecked(True)
        off = CheckBox("Opção desativada")
        off.setEnabled(False)
        card.body.addWidget(checked)
        card.body.addWidget(CheckBox("Opção desmarcada"))
        card.body.addWidget(off)
        progress = ProgressBar()
        progress.setValue(60)
        card.body.addWidget(FormField("Progresso", progress))
        indicator = StatCard("Indicador", "layers", "primary")
        indicator.set_value(128)
        card.body.addWidget(indicator)
        card.body.addStretch()
        return card

    def _table_card(self) -> Card:
        card = Card("Tabela", "Linhas de 44 px, com seleção e destaque ao passar o cursor.")
        table = DataTable(["Documento", "Descrição", "Status"], stretch_column=1, badge_column=2)
        rows = [("1001", "Linha de exemplo", "Pronto", "success"),
                ("1002", "Linha com aviso", "Revisar", "info"),
                ("1003", "Linha com falha", "Erro", "danger")]
        table.setRowCount(len(rows))
        for row, (document, description, status, tone) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(document))
            table.setItem(row, 1, QTableWidgetItem(description))
            status_item = QTableWidgetItem(status)
            status_item.setData(BADGE_TONE_ROLE, tone)
            table.setItem(row, 2, status_item)
        table.setMinimumHeight(180)
        card.body.addWidget(table)
        return card

    def _show_modal(self) -> None:
        Modal.ask(
            self,
            "Exemplo de modal",
            "Modais têm largura padrão de 480 px e acompanham o tema atual.",
            "info",
            [("cancel", "Cancelar", "secondary"), ("ok", "Confirmar", "primary")],
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(860, 600)
        self.resize(1240, 820)

        self.sidebar = Sidebar(APP_NAME, "truck", "O arquivo original nunca é alterado.")
        self.header = Header()
        self.stack = QStackedWidget()
        self.rename_page = RenamePage()
        self.design_page = DesignSystemPage()
        self._pages = [
            ("Separar e renomear", "scissors", self.rename_page),
            ("Design System", "grid", self.design_page),
        ]
        for title, icon, page in self._pages:
            self.sidebar.add_page(title, icon)
            self.stack.addWidget(page_scroll_area(page))
        self.sidebar.page_selected.connect(self._show_page)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.header)
        right.addWidget(self.stack, 1)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar)
        root.addLayout(right, 1)
        self.setCentralWidget(central)
        self._show_page(0)
        # Evita o anel de foco em um controle ao abrir; Tab continua navegando normalmente.
        central.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        central.setFocus()

    def _show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.header.set_title(self._pages[index][0])

    def closeEvent(self, event) -> None:
        self.rename_page.wait_for_task()
        super().closeEvent(event)


def create_application(argv: list[str]) -> QApplication:
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(default_font())
    theme.apply()
    app.setWindowIcon(_window_icon())
    return app


def _window_icon() -> QIcon:
    return themed_icon("truck", "primary", 32)


def main() -> int:
    app = create_application(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
