"""Tokens do Design System e gerenciamento global de temas."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

from icons import svg_markup

LIGHT = "light"
DARK = "dark"

# Cores de identidade: iguais nos dois temas.
BRAND = {
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "primary_pressed": "#1E40AF",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "danger_pressed": "#991B1B",
    "success": "#16A34A",
    "on_brand": "#FFFFFF",
    "focus_ring": "#93C5FD",
}

# Cores neutras: mudam conforme o tema.
NEUTRALS = {
    LIGHT: {
        "bg": "#FFFFFF",
        "bg_secondary": "#F9FAFB",
        "content_bg": "#F9FAFB",
        "chrome_bg": "#FFFFFF",
        "card": "#FFFFFF",
        "input_bg": "#FFFFFF",
        "text": "#111827",
        "text_muted": "#6B7280",
        "border": "#E5E7EB",
        "border_strong": "#D1D5DB",
        "hover": "#F3F4F6",
        "pressed": "#E5E7EB",
        "selection": "#EFF6FF",
        "disabled_bg": "#F3F4F6",
        "disabled_text": "#9CA3AF",
        "scrollbar": "#D1D5DB",
        "scrollbar_hover": "#9CA3AF",
    },
    DARK: {
        "bg": "#111827",
        "bg_secondary": "#1F2937",
        "content_bg": "#111827",
        "chrome_bg": "#1F2937",
        "card": "#1F2937",
        "input_bg": "#111827",
        "text": "#F9FAFB",
        "text_muted": "#9CA3AF",
        "border": "#374151",
        "border_strong": "#4B5563",
        "hover": "#374151",
        "pressed": "#4B5563",
        "selection": "#1E3A5F",
        "disabled_bg": "#374151",
        "disabled_text": "#6B7280",
        "scrollbar": "#4B5563",
        "scrollbar_hover": "#6B7280",
    },
}

SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = {"xs": 4, "control": 8, "card": 12, "pill": 12}
FONT_FAMILIES = ["Segoe UI", "Inter", ".AppleSystemUIFont", "Helvetica Neue", "Arial"]
FONT_SIZE = {"small": 12, "base": 13, "section": 15, "subtitle": 20, "title": 24}
FONT_WEIGHT_STRONG = 600

SIZES = {
    "button_sm": 32,
    "button_md": 40,
    "button_lg": 48,
    "input": 42,
    "textarea_min": 100,
    "checkbox": 18,
    "sidebar": 240,
    "header": 64,
    "modal": 480,
    "card_padding": 20,
    "table_row": 44,
    "table_header": 40,
    "table_stretch_min": 180,
    "icon_sm": 18,
    "icon_md": 20,
    "icon_display": 32,  # só em estados vazios e na área de envio
    "progress": 6,
    "scrollbar": 10,
    "badge": 24,
    "swatch": 56,
}

_TOKEN_RE = re.compile(r"\{\{(\w+)\}\}")


def resource_path(name: str) -> Path:
    """Localiza um arquivo do projeto, inclusive em executável do PyInstaller."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) / name if base else Path(__file__).resolve().parent / name


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings("TCM", "RenomeadorCTE")
        saved = self._settings.value("theme", LIGHT)
        self._name = saved if saved in NEUTRALS else LIGHT
        self._icon_dir = tempfile.TemporaryDirectory(prefix="renomeador_cte_")

    @property
    def name(self) -> str:
        return self._name

    def color(self, token: str) -> str:
        if token in BRAND:
            return BRAND[token]
        return NEUTRALS[self._name][token]

    def apply(self) -> None:
        """Aplica o tema atual em toda a aplicação."""
        app = QApplication.instance()
        if app is None:
            return
        scheme = Qt.ColorScheme.Dark if self._name == DARK else Qt.ColorScheme.Light
        app.styleHints().setColorScheme(scheme)  # também ajusta a barra de título
        app.setPalette(self._build_palette())
        app.setStyleSheet(self.render_stylesheet())
        self.theme_changed.emit(self._name)

    def set_theme(self, name: str) -> None:
        if name not in NEUTRALS or name == self._name:
            return
        self._name = name
        self._settings.setValue("theme", name)
        self.apply()

    def render_stylesheet(self) -> str:
        template = resource_path("styles.qss").read_text(encoding="utf-8")
        tokens = self._template_tokens()

        def replace(match: re.Match[str]) -> str:
            return str(tokens[match.group(1)])  # token desconhecido é erro de programação

        return _TOKEN_RE.sub(replace, template)

    def _template_tokens(self) -> dict[str, object]:
        tokens: dict[str, object] = {**BRAND, **NEUTRALS[self._name]}
        tokens.update({f"space_{k}": v for k, v in SPACING.items()})
        tokens.update({f"radius_{k}": v for k, v in RADIUS.items()})
        tokens.update({f"font_{k}": v for k, v in FONT_SIZE.items()})
        tokens.update({f"size_{k}": v for k, v in SIZES.items()})
        tokens["font_weight_strong"] = FONT_WEIGHT_STRONG
        tokens["icon_check"] = self._icon_file("check", BRAND["on_brand"], 14)
        tokens["icon_chevron"] = self._icon_file(
            "chevron-down", self.color("text_muted"), SIZES["icon_sm"]
        )
        tokens["icon_chevron_disabled"] = self._icon_file(
            "chevron-down", self.color("disabled_text"), SIZES["icon_sm"]
        )
        return tokens

    def _icon_file(self, icon: str, color: str, size: int) -> str:
        """QSS só referencia imagens por caminho; os ícones são gravados tingidos."""
        path = Path(self._icon_dir.name) / f"{icon}_{color.lstrip('#')}_{size}.svg"
        if not path.exists():
            path.write_text(svg_markup(icon, color, size, stroke_width=3), encoding="utf-8")
        return path.as_posix()

    def _build_palette(self) -> QPalette:
        palette = QPalette()
        roles = {
            QPalette.ColorRole.Window: "content_bg",
            QPalette.ColorRole.WindowText: "text",
            QPalette.ColorRole.Base: "input_bg",
            QPalette.ColorRole.AlternateBase: "bg_secondary",
            QPalette.ColorRole.Text: "text",
            QPalette.ColorRole.Button: "card",
            QPalette.ColorRole.ButtonText: "text",
            QPalette.ColorRole.ToolTipBase: "card",
            QPalette.ColorRole.ToolTipText: "text",
            QPalette.ColorRole.PlaceholderText: "text_muted",
            QPalette.ColorRole.Highlight: "primary",
            QPalette.ColorRole.HighlightedText: "on_brand",
            QPalette.ColorRole.Link: "primary",
        }
        for role, token in roles.items():
            palette.setColor(role, QColor(self.color(token)))
        for role in (
            QPalette.ColorRole.WindowText,
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
        ):
            palette.setColor(
                QPalette.ColorGroup.Disabled, role, QColor(self.color("disabled_text"))
            )
        return palette


def default_font() -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(FONT_SIZE["base"])
    return font


theme = ThemeManager()
