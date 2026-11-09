"""Componentes reutilizáveis do Design System."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from icons import svg_markup
from themes import DARK, FONT_SIZE, FONT_WEIGHT_STRONG, LIGHT, RADIUS, SIZES, SPACING, theme

BADGE_TONE_ROLE = Qt.ItemDataRole.UserRole + 10
SORT_VALUE_ROLE = Qt.ItemDataRole.UserRole + 11

_BADGE_COLORS = {"success": "success", "info": "primary", "danger": "danger"}
_PIXMAP_SCALE = 2  # mantém os ícones nítidos em telas de alta densidade


def repolish(widget: QWidget) -> None:
    """Reaplica o QSS após a mudança de uma propriedade dinâmica."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def icon_pixmap(name: str, color_token: str, size: int = SIZES["icon_sm"]) -> QPixmap:
    physical = size * _PIXMAP_SCALE
    pixmap = QPixmap(physical, physical)
    pixmap.fill(Qt.GlobalColor.transparent)
    data = QByteArray(svg_markup(name, theme.color(color_token)).encode("utf-8"))
    painter = QPainter(pixmap)
    QSvgRenderer(data).render(painter, QRectF(0, 0, physical, physical))
    painter.end()
    pixmap.setDevicePixelRatio(_PIXMAP_SCALE)
    return pixmap


def themed_icon(name: str, color_token: str, size: int = SIZES["icon_sm"]) -> QIcon:
    return QIcon(icon_pixmap(name, color_token, size))


def text_label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if role:
        label.setProperty("textRole", role)
    label.setWordWrap(wrap)
    return label


# ---------------------------------------------------------------- Ícones
class IconLabel(QLabel):
    def __init__(self, name: str, color_token: str = "text_muted", size: int = SIZES["icon_md"]):
        super().__init__()
        self._name, self._token, self._icon_size = name, color_token, size
        self.setFixedSize(size, size)
        self._refresh()
        theme.theme_changed.connect(self._refresh)

    def set_icon(self, name: str, color_token: str | None = None) -> None:
        self._name = name
        self._token = color_token or self._token
        self._refresh()

    def _refresh(self, *_args) -> None:
        self.setPixmap(icon_pixmap(self._name, self._token, self._icon_size))


# ---------------------------------------------------------------- Botões
class Button(QPushButton):
    _HEIGHTS = {"sm": "button_sm", "md": "button_md", "lg": "button_lg"}
    _ICON_TOKENS = {"primary": "on_brand", "danger": "on_brand", "secondary": "text"}

    def __init__(self, text: str = "", variant: str = "primary", size: str = "md",
                 icon: str | None = None, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setProperty("btnSize", size)
        self.setFixedHeight(SIZES[self._HEIGHTS[size]])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_name, self._variant = icon, variant
        if icon:
            self.setIconSize(QSize(SIZES["icon_sm"], SIZES["icon_sm"]))
            self.setText(text)
            self._refresh_icon()
            theme.theme_changed.connect(self._refresh_icon)

    def setText(self, text: str) -> None:
        # O QSS não tem "gap": o espaço separa o ícone do texto.
        super().setText(f" {text}" if self._icon_name else text)

    def _refresh_icon(self, *_args) -> None:
        self.setIcon(themed_icon(self._icon_name, self._ICON_TOKENS[self._variant]))


class NavButton(QPushButton):
    def __init__(self, text: str, icon: str):
        super().__init__(text)
        self.setProperty("nav", True)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setFixedHeight(SIZES["button_md"])
        self.setIconSize(QSize(SIZES["icon_sm"], SIZES["icon_sm"]))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._icon_name = icon
        self._refresh_icon()
        self.toggled.connect(self._refresh_icon)
        theme.theme_changed.connect(self._refresh_icon)

    def _refresh_icon(self, *_args) -> None:
        token = "on_brand" if self.isChecked() else "text_muted"
        self.setIcon(themed_icon(self._icon_name, token))


# ---------------------------------------------------------------- Entradas
class TextInput(QLineEdit):
    def __init__(self, placeholder: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(SIZES["input"])

    def set_invalid(self, invalid: bool) -> None:
        self.setProperty("invalid", invalid)
        repolish(self)


class SearchInput(TextInput):
    def __init__(self, placeholder: str = "Pesquisar...", parent: QWidget | None = None):
        super().__init__(placeholder, parent)
        self.setClearButtonEnabled(True)
        self._action = self.addAction(
            themed_icon("search", "text_muted"), QLineEdit.ActionPosition.LeadingPosition
        )
        theme.theme_changed.connect(self._refresh_icon)

    def _refresh_icon(self, *_args) -> None:
        self._action.setIcon(themed_icon("search", "text_muted"))


class ComboBox(QComboBox):
    def __init__(self, items: list[str] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setView(QListView())  # necessário para o QSS estilizar os itens
        self.setFixedHeight(SIZES["input"])
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if items:
            self.addItems(items)


class TextArea(QPlainTextEdit):
    def __init__(self, placeholder: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumHeight(SIZES["textarea_min"])


class CheckBox(QCheckBox):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class ProgressBar(QProgressBar):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setValue(0)


class FormField(QWidget):
    """Rótulo + campo + texto de apoio, com espaçamento padronizado."""

    def __init__(self, label: str, field: QWidget, helper: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["xs"])
        layout.addWidget(text_label(label, "field"))
        layout.addWidget(field)
        self.helper = text_label(helper, "caption", wrap=True)
        self.helper.setVisible(bool(helper))
        layout.addWidget(self.helper)

    def set_helper(self, text: str) -> None:
        self.helper.setText(text)
        self.helper.setVisible(bool(text))


# ---------------------------------------------------------------- Containers
class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.body = QVBoxLayout(self)
        padding = SIZES["card_padding"]
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(SPACING["lg"])
        if title:
            heading = QVBoxLayout()
            heading.setSpacing(SPACING["xs"])
            heading.addWidget(text_label(title, "section"))
            if subtitle:
                heading.addWidget(text_label(subtitle, "muted", wrap=True))
            self.body.addLayout(heading)


class StatCard(Card):
    def __init__(self, label: str, icon: str, icon_token: str = "text_muted"):
        super().__init__()
        self.body.setSpacing(SPACING["sm"])
        top = QHBoxLayout()
        top.setSpacing(SPACING["sm"])
        top.addWidget(text_label(label, "muted"))
        top.addStretch()
        top.addWidget(IconLabel(icon, icon_token, SIZES["icon_md"]))
        self.body.addLayout(top)
        self._value = text_label("–", "title")
        self.body.addWidget(self._value)

    def set_value(self, value: int | str) -> None:
        self._value.setText(str(value))


class ResponsiveRow(QWidget):
    """Distribui os filhos em colunas e reorganiza conforme a largura disponível.

    Usa a maior quantidade de `columns` em que cada item mantém `item_min_width`.
    """

    def __init__(self, item_min_width: int, columns: tuple[int, ...] = (2, 1),
                 spacing: int = SPACING["lg"]):
        super().__init__()
        self._item_min_width = item_min_width
        self._column_options = sorted(columns, reverse=True)
        self._spacing = spacing
        self._current_columns = 0
        self._items: list[tuple[QWidget, int]] = []
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)
        # Mínimo explícito: impede que os filhos forcem rolagem horizontal na página.
        self.setMinimumWidth(1)

    def add(self, widget: QWidget, stretch: int = 1) -> None:
        self._items.append((widget, stretch))
        self._arrange(self._column_options[0])

    def _columns_for(self, width: int) -> int:
        for columns in self._column_options:
            if columns * self._item_min_width + (columns - 1) * self._spacing <= width:
                return columns
        return self._column_options[-1]

    def _arrange(self, columns: int) -> None:
        self._current_columns = columns
        for widget, _stretch in self._items:
            self._layout.removeWidget(widget)
        for column in range(max(self._column_options)):
            self._layout.setColumnStretch(column, 0)
        for index, (widget, stretch) in enumerate(self._items):
            self._layout.addWidget(widget, index // columns, index % columns)
            # Proporções próprias só valem quando todos os itens estão na mesma linha.
            single_line = columns >= len(self._items)
            column_stretch = stretch if single_line else 1
            self._layout.setColumnStretch(index % columns, column_stretch)

    def resizeEvent(self, event) -> None:
        columns = self._columns_for(event.size().width())
        if columns != self._current_columns:
            self._arrange(columns)
        super().resizeEvent(event)


class EmptyState(QWidget):
    def __init__(self, icon: str, title: str, message: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACING["sm"])
        layout.addStretch()
        layout.addWidget(
            IconLabel(icon, "text_muted", SIZES["icon_display"]), 0, Qt.AlignmentFlag.AlignHCenter
        )
        for label in (text_label(title, "section"), text_label(message, "muted", wrap=True)):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        layout.addStretch()


class DropZone(QFrame):
    """Área para arrastar um arquivo ou abrir o seletor de arquivos."""

    file_dropped = Signal(str)
    browse_requested = Signal()

    def __init__(self, title: str, hint: str, button_text: str, extension: str = ".pdf"):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._extension = extension.lower()

        layout = QVBoxLayout(self)
        padding = SPACING["lg"]
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(SPACING["sm"])
        layout.addStretch()

        self._icon = IconLabel("upload", "primary", SIZES["icon_display"])
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self._title = text_label(title, "section", wrap=True)
        self._hint = text_label(hint, "muted", wrap=True)
        for label in (self._title, self._hint):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(label)
        layout.addSpacing(SPACING["xs"])
        self.button = Button(button_text, "secondary", "md", "folder")
        self.button.clicked.connect(self.browse_requested)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch()

    def set_file(self, title: str, hint: str, button_text: str) -> None:
        self._icon.set_icon("file-text")
        self._title.setText(title)
        self._hint.setText(hint)
        self.button.setText(button_text)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.browse_requested.emit()
        super().mouseReleaseEvent(event)

    def _dropped_path(self, event) -> str | None:
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            path = urls[0].toLocalFile()
            if path.lower().endswith(self._extension):
                return path
        return None

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        repolish(self)

    def dragEnterEvent(self, event) -> None:
        if self.isEnabled() and self._dropped_path(event):
            event.acceptProposedAction()
            self._set_drag_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_active(False)

    def dropEvent(self, event) -> None:
        self._set_drag_active(False)
        path = self._dropped_path(event)
        if path:
            event.acceptProposedAction()
            self.file_dropped.emit(path)


# ---------------------------------------------------------------- Tabela
class SortableItem(QTableWidgetItem):
    """Item cuja ordenação usa um valor próprio (ex.: número em vez de texto)."""

    def __init__(self, text: str, sort_value: object | None = None):
        super().__init__(text)
        self.setData(SORT_VALUE_ROLE, text if sort_value is None else sort_value)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        return self.data(SORT_VALUE_ROLE) < other.data(SORT_VALUE_ROLE)


class RowHoverDelegate(QStyledItemDelegate):
    """Destaca a linha inteira sob o cursor, não apenas a célula."""

    def __init__(self, table: "DataTable"):
        super().__init__(table)
        self._table = table

    def initStyleOption(self, option: QStyleOptionViewItem, index) -> None:
        super().initStyleOption(option, index)
        if index.row() == self._table.hovered_row:
            option.state |= QStyle.StateFlag.State_MouseOver
        else:
            option.state &= ~QStyle.StateFlag.State_MouseOver
        option.state &= ~QStyle.StateFlag.State_HasFocus


class BadgeDelegate(RowHoverDelegate):
    """Desenha o texto da célula como uma etiqueta colorida."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        cell = QStyleOptionViewItem(option)
        self.initStyleOption(cell, index)
        text, cell.text = cell.text, ""
        widget = option.widget
        widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, cell, painter, widget)
        if not text:
            return

        tone = index.data(BADGE_TONE_ROLE) or "info"
        font = painter.font()
        font.setPixelSize(FONT_SIZE["small"])
        font.setWeight(QFont.Weight(FONT_WEIGHT_STRONG))
        painter.save()
        painter.setFont(font)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = painter.fontMetrics().horizontalAdvance(text) + 2 * SPACING["md"]
        height = SIZES["badge"]
        pill = QRectF(
            option.rect.x() + SPACING["md"],
            option.rect.y() + (option.rect.height() - height) / 2,
            width,
            height,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.color(_BADGE_COLORS[tone])))
        painter.drawRoundedRect(pill, RADIUS["pill"], RADIUS["pill"])
        painter.setPen(QColor(theme.color("on_brand")))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        hint = super().sizeHint(option, index)
        return QSize(hint.width() + 2 * SPACING["xl"], hint.height())


class DataTable(QTableWidget):
    def __init__(self, columns: list[str], stretch_column: int | None = None,
                 badge_column: int | None = None, parent: QWidget | None = None):
        super().__init__(0, len(columns), parent)
        self.hovered_row = -1
        self.setHorizontalHeaderLabels(columns)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setAlternatingRowColors(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)

        vertical = self.verticalHeader()
        vertical.setVisible(False)
        vertical.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vertical.setDefaultSectionSize(SIZES["table_row"])

        horizontal = self.horizontalHeader()
        horizontal.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        horizontal.setHighlightSections(False)
        horizontal.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        horizontal.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._stretch_column = stretch_column
        if stretch_column is not None:
            horizontal.setSectionResizeMode(stretch_column, QHeaderView.ResizeMode.Interactive)
            horizontal.sectionResized.connect(self._on_section_resized)

        self.setItemDelegate(RowHoverDelegate(self))
        if badge_column is not None:
            self.setItemDelegateForColumn(badge_column, BadgeDelegate(self))

    def _on_section_resized(self, column: int, _old: int, _new: int) -> None:
        if column != self._stretch_column:
            self._fit_stretch_column()

    def _fit_stretch_column(self) -> None:
        """Ocupa a sobra de largura, sem deixar a coluna principal ficar ilegível."""
        if self._stretch_column is None:
            return
        header = self.horizontalHeader()
        others = sum(
            header.sectionSize(column)
            for column in range(self.columnCount())
            if column != self._stretch_column
        )
        width = max(SIZES["table_stretch_min"], self.viewport().width() - others)
        header.resizeSection(self._stretch_column, width)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_stretch_column()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.viewport():
            if event.type() == QEvent.Type.MouseMove:
                self._set_hovered_row(self.rowAt(event.position().toPoint().y()))
            elif event.type() == QEvent.Type.Leave:
                self._set_hovered_row(-1)
        return super().eventFilter(watched, event)

    def _set_hovered_row(self, row: int) -> None:
        if row != self.hovered_row:
            self.hovered_row = row
            self.viewport().update()


# ---------------------------------------------------------------- Modal
class Modal(QDialog):
    """Modal padrão: ícone, título, mensagem e botões de ação."""

    _TONES = {
        "info": ("alert-circle", "primary"),
        "success": ("check-circle", "success"),
        "danger": ("alert-circle", "danger"),
    }

    def __init__(self, parent: QWidget | None, title: str, message: str, tone: str = "info"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(SIZES["modal"])
        self.result_key: str | None = None

        layout = QVBoxLayout(self)
        padding = SPACING["xl"]
        layout.setContentsMargins(padding, padding, padding, padding)
        layout.setSpacing(SPACING["lg"])

        heading = QHBoxLayout()
        heading.setSpacing(SPACING["md"])
        icon, token = self._TONES[tone]
        heading.addWidget(IconLabel(icon, token, SIZES["icon_md"]))
        heading.addWidget(text_label(title, "subtitle", wrap=True), 1)
        layout.addLayout(heading)

        self.message = text_label(message, "muted", wrap=True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.message)

        self.content = QVBoxLayout()
        self.content.setSpacing(SPACING["sm"])
        layout.addLayout(self.content)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(SPACING["sm"])
        self.actions.addStretch()
        layout.addSpacing(SPACING["sm"])
        layout.addLayout(self.actions)

    def add_action(self, key: str, text: str, variant: str = "secondary") -> Button:
        button = Button(text, variant)
        button.clicked.connect(lambda: self._finish(key))
        self.actions.addWidget(button)
        return button

    def _finish(self, key: str) -> None:
        self.result_key = key
        self.accept()

    @classmethod
    def ask(cls, parent: QWidget | None, title: str, message: str, tone: str,
            actions: list[tuple[str, str, str]]) -> str | None:
        """Exibe o modal. `actions` = (chave, texto, variante); a última recebe o foco."""
        modal = cls(parent, title, message, tone)
        for key, text, variant in actions:
            button = modal.add_action(key, text, variant)
        button.setDefault(True)
        button.setFocus()
        modal.exec()
        return modal.result_key


# ---------------------------------------------------------------- Estrutura
class ThemeSwitch(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("ThemeSwitch")
        self.setFixedHeight(SIZES["button_md"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["xs"], SPACING["xs"], SPACING["xs"], SPACING["xs"])
        layout.setSpacing(SPACING["xs"])

        self._buttons: dict[str, tuple[QPushButton, str]] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for name, text, icon in ((LIGHT, "Claro", "sun"), (DARK, "Escuro", "moon")):
            button = QPushButton()
            button.setToolTip(text)
            button.setAccessibleName(f"Tema {text.lower()}")
            button.setProperty("segment", True)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(SIZES["button_sm"], SIZES["button_sm"])
            button.setIconSize(QSize(SIZES["icon_sm"], SIZES["icon_sm"]))
            button.clicked.connect(lambda _checked, theme_name=name: theme.set_theme(theme_name))
            group.addButton(button)
            layout.addWidget(button)
            self._buttons[name] = (button, icon)
        self._sync()
        theme.theme_changed.connect(self._sync)

    def _sync(self, *_args) -> None:
        for name, (button, icon) in self._buttons.items():
            checked = name == theme.name
            button.setChecked(checked)
            button.setIcon(themed_icon(icon, "on_brand" if checked else "text_muted"))


class Sidebar(QFrame):
    page_selected = Signal(int)

    def __init__(self, brand: str, brand_icon: str, footer: str = ""):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIZES["sidebar"])
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(SPACING["md"], 0, SPACING["md"], SPACING["lg"])
        self._layout.setSpacing(SPACING["xs"])

        brand_row = QHBoxLayout()
        brand_row.setSpacing(SPACING["sm"])
        brand_row.setContentsMargins(SPACING["xs"], 0, 0, 0)
        brand_row.addWidget(IconLabel(brand_icon, "primary", SIZES["icon_md"]))
        brand_row.addWidget(text_label(brand, "section"), 1)
        brand_holder = QWidget()
        brand_holder.setFixedHeight(SIZES["header"])
        brand_holder.setLayout(brand_row)
        self._layout.addWidget(brand_holder)
        self._layout.addSpacing(SPACING["sm"])

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self.page_selected)
        self._layout.addStretch()
        if footer:
            self._layout.addWidget(text_label(footer, "caption", wrap=True))

    def add_page(self, text: str, icon: str) -> None:
        button = NavButton(text, icon)
        index = len(self._group.buttons())
        self._group.addButton(button, index)
        stretch_position = self._layout.count() - 2  # antes do espaçador e do rodapé
        self._layout.insertWidget(stretch_position, button)
        if index == 0:
            button.setChecked(True)


class Header(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Header")
        self.setFixedHeight(SIZES["header"])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], 0, SPACING["xl"], 0)
        layout.setSpacing(SPACING["lg"])
        self._title = text_label("", "subtitle")
        layout.addWidget(self._title)
        layout.addStretch()
        layout.addWidget(ThemeSwitch())

    def set_title(self, title: str) -> None:
        self._title.setText(title)


class ColorSwatch(QWidget):
    """Amostra de um token de cor; redesenhada automaticamente na troca de tema."""

    def __init__(self, token: str, label: str):
        super().__init__()
        self._token = token
        self._label = label
        self.setMinimumHeight(SIZES["swatch"] + SPACING["xl"] * 2)
        self.setMinimumWidth(SIZES["swatch"] * 2)
        theme.theme_changed.connect(self.update)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        block = QRectF(0.5, 0.5, self.width() - 1, SIZES["swatch"])
        painter.setPen(QColor(theme.color("border")))
        painter.setBrush(QColor(theme.color(self._token)))
        painter.drawRoundedRect(block, RADIUS["control"], RADIUS["control"])
        font = painter.font()
        font.setPixelSize(FONT_SIZE["small"])
        painter.setFont(font)
        line = painter.fontMetrics().height()
        painter.setPen(QColor(theme.color("text")))
        top = SIZES["swatch"] + SPACING["xs"]
        painter.drawText(0, top, self.width(), line, Qt.AlignmentFlag.AlignLeft, self._label)
        painter.setPen(QColor(theme.color("text_muted")))
        painter.drawText(0, top + line, self.width(), line, Qt.AlignmentFlag.AlignLeft,
                         theme.color(self._token))
