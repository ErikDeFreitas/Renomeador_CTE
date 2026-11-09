"""Leitura, separação e renomeação de CT-es contidos em um único PDF.

Este módulo não depende da interface. O PDF original nunca é alterado.

Cada página de um DACTE traz a chave de acesso de 44 dígitos, que identifica o
documento de forma única. As páginas são agrupadas por essa chave, de modo que
um CT-e com várias folhas gera um único arquivo.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

CTE_MODELS = {"57", "67"}  # 57 = CT-e, 67 = CT-e OS
UNIDENTIFIED_STEM = "_paginas_nao_identificadas"

ON_CONFLICT_REPLACE = "replace"
ON_CONFLICT_KEEP_BOTH = "keep_both"

ProgressCallback = Callable[[int, int], None]

_SPACED_KEY_RE = re.compile(r"(?<!\d)\d{4}(?: \d{4}){10}(?!\d)")
_PLAIN_KEY_RE = re.compile(r"(?<!\d)\d{44}(?!\d)")
_NUMBER_RE = re.compile(r"N[ÚU]MERO\s*\n\s*(\d+)", re.IGNORECASE)
_SERIES_RE = re.compile(r"S[ÉE]RIE\s*\n\s*(\d+)", re.IGNORECASE)
_ISSUE_DATE_RE = re.compile(
    r"DATA E HORA DE EMISS[ÃA]O\s*\n\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)
_PAYER_RE = re.compile(r"TOMADOR:[ \t]*(.+)")
_SHEET_RE = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*$", re.MULTILINE)
_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class PdfAnalysisError(Exception):
    """Erro com mensagem pronta para ser exibida ao usuário."""


@dataclass(frozen=True)
class PageInfo:
    key: str | None = None
    key_is_valid: bool = False
    printed_number: str | None = None
    printed_series: str | None = None
    issue_date: str | None = None
    payer: str | None = None
    sheet: int | None = None
    sheet_total: int | None = None

    @property
    def identified(self) -> bool:
        return bool(self.key or self.printed_number)


@dataclass
class CteDocument:
    number: str
    series: str = ""
    key: str | None = None
    issue_date: str = ""
    payer: str = ""
    pages: list[int] = field(default_factory=list)  # índices a partir de 0
    warnings: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.warnings)


@dataclass
class AnalysisResult:
    source: Path
    total_pages: int
    documents: list[CteDocument]
    unidentified_pages: list[int]

    @property
    def has_extractable_text(self) -> bool:
        return bool(self.documents)


@dataclass
class ExportItem:
    document: CteDocument | None  # None = páginas não identificadas
    path: Path
    error: str | None = None


def key_check_digit(key_without_dv: str) -> int:
    """Calcula o dígito verificador (módulo 11) de uma chave de 43 dígitos."""
    total, weight = 0, 2
    for digit in reversed(key_without_dv):
        total += int(digit) * weight
        weight = 2 if weight == 9 else weight + 1
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_key(key: str) -> bool:
    return (
        len(key) == 44
        and key.isdigit()
        and key_check_digit(key[:43]) == int(key[43])
    )


def number_from_key(key: str) -> str:
    return str(int(key[25:34]))


def series_from_key(key: str) -> str:
    return str(int(key[22:25]))


def _find_cte_key(text: str) -> str | None:
    """Localiza a chave do próprio CT-e na página.

    A chave do cabeçalho é impressa em blocos de 4 dígitos, enquanto as chaves
    dos documentos originários são contínuas. Por isso a forma em blocos tem
    prioridade: um CT-e pode citar outro CT-e em seus documentos originários.
    """
    for match in _SPACED_KEY_RE.finditer(text):
        key = match.group().replace(" ", "")
        if key[20:22] in CTE_MODELS:
            return key
    for match in _PLAIN_KEY_RE.finditer(text):
        key = match.group()
        if key[20:22] in CTE_MODELS and is_valid_key(key):
            return key
    return None


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def parse_page_text(text: str) -> PageInfo:
    key = _find_cte_key(text)
    sheets = _SHEET_RE.findall(text)
    sheet, sheet_total = (int(sheets[-1][0]), int(sheets[-1][1])) if sheets else (None, None)
    return PageInfo(
        key=key,
        key_is_valid=bool(key and is_valid_key(key)),
        printed_number=_first_group(_NUMBER_RE, text),
        printed_series=_first_group(_SERIES_RE, text),
        issue_date=_first_group(_ISSUE_DATE_RE, text),
        payer=_first_group(_PAYER_RE, text),
        sheet=sheet,
        sheet_total=sheet_total,
    )


def _resolve_number(info: PageInfo) -> tuple[str, list[str]]:
    warnings: list[str] = []
    if not info.key:
        warnings.append("Chave de acesso não encontrada; número lido do campo NÚMERO.")
        return str(int(info.printed_number)), warnings

    number = number_from_key(info.key)
    if not info.key_is_valid:
        warnings.append("Dígito verificador da chave de acesso é inválido.")
        if info.printed_number:
            number = str(int(info.printed_number))
    if info.printed_number and int(info.printed_number) != int(number_from_key(info.key)):
        warnings.append(
            f"O campo NÚMERO ({int(info.printed_number)}) difere da chave de acesso "
            f"({number_from_key(info.key)})."
        )
    return number, warnings


def group_pages(page_infos: list[PageInfo]) -> tuple[list[CteDocument], list[int]]:
    """Agrupa páginas por CT-e, na ordem em que cada documento aparece."""
    groups: dict[str, list[tuple[int, PageInfo]]] = {}
    unidentified: list[int] = []
    for index, info in enumerate(page_infos):
        if not info.identified:
            unidentified.append(index)
            continue
        group_id = info.key or f"{info.printed_series}-{info.printed_number}"
        groups.setdefault(group_id, []).append((index, info))
    return [_build_document(entries) for entries in groups.values()], unidentified


def _build_document(entries: list[tuple[int, PageInfo]]) -> CteDocument:
    first = entries[0][1]
    number, warnings = _resolve_number(first)
    series = series_from_key(first.key) if first.key else (first.printed_series or "")

    pages_by_sheet: dict[int, int] = {}
    pages_without_sheet: list[int] = []
    duplicated_sheets = 0
    for page_index, info in entries:
        if info.sheet is None:
            pages_without_sheet.append(page_index)
        elif info.sheet in pages_by_sheet:
            duplicated_sheets += 1
        else:
            pages_by_sheet[info.sheet] = page_index

    if pages_without_sheet:
        # Sem numeração em alguma folha: preserva a ordem do arquivo original.
        pages = sorted([*pages_by_sheet.values(), *pages_without_sheet])
    else:
        pages = [pages_by_sheet[sheet] for sheet in sorted(pages_by_sheet)]

    if duplicated_sheets:
        warnings.append(
            f"{duplicated_sheets} folha(s) repetida(s) no PDF; mantida apenas a primeira cópia."
        )
    expected = first.sheet_total
    if expected and not pages_without_sheet and len(pages_by_sheet) != expected:
        warnings.append(f"Esperadas {expected} folha(s), encontradas {len(pages_by_sheet)}.")

    return CteDocument(
        number=number,
        series=series,
        key=first.key,
        issue_date=first.issue_date or "",
        payer=first.payer or "",
        pages=pages,
        warnings=warnings,
    )


def _open_reader(path: Path) -> PdfReader:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PdfAnalysisError("O PDF está protegido por senha.")
        return reader
    except PdfAnalysisError:
        raise
    except FileNotFoundError as exc:
        raise PdfAnalysisError("O arquivo não foi encontrado.") from exc
    except PermissionError as exc:
        raise PdfAnalysisError("Sem permissão para ler o arquivo.") from exc
    except (PyPdfError, OSError, ValueError) as exc:
        raise PdfAnalysisError(f"Não foi possível ler o PDF: {exc}") from exc


def analyze_pdf(path: str | Path, progress: ProgressCallback | None = None) -> AnalysisResult:
    source = Path(path)
    reader = _open_reader(source)
    total = len(reader.pages)
    infos: list[PageInfo] = []
    for index, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except (PyPdfError, ValueError, KeyError, TypeError):
            # Página ilegível não interrompe o lote: vai para "não identificadas".
            text = ""
        infos.append(parse_page_text(text))
        if progress:
            progress(index + 1, total)

    documents, unidentified = group_pages(infos)
    mark_repeated_numbers(documents)
    return AnalysisResult(source, total, documents, unidentified)


def sanitize_prefix(prefix: str) -> str:
    return _INVALID_FILENAME_CHARS_RE.sub("", prefix).strip()


def plan_filenames(documents: list[CteDocument], prefix: str = "") -> list[str]:
    """Define o nome de cada CT-e, numerando CT-es distintos com o mesmo número.

    Filiais diferentes podem emitir o mesmo número; nesse caso, a primeira
    ocorrência fica com o nome simples e as demais recebem um sufixo.
    """
    clean_prefix = sanitize_prefix(prefix)
    occurrences: dict[str, int] = {}
    names: list[str] = []
    for document in documents:
        count = occurrences.get(document.number, 0) + 1
        occurrences[document.number] = count
        suffix = f"_{count}" if count > 1 else ""
        names.append(f"{clean_prefix}{document.number}{suffix}.pdf")
    return names


def mark_repeated_numbers(documents: list[CteDocument]) -> None:
    """Adiciona um aviso aos CT-es distintos que compartilham o mesmo número."""
    counts: dict[str, int] = {}
    for document in documents:
        counts[document.number] = counts.get(document.number, 0) + 1
    for document in documents:
        if counts[document.number] > 1:
            document.warnings.append(
                "Outro CT-e deste PDF tem o mesmo número; o arquivo recebeu um sufixo."
            )


def find_existing_outputs(
    result: AnalysisResult, output_dir: str | Path, prefix: str = ""
) -> list[Path]:
    directory = Path(output_dir)
    names = plan_filenames(result.documents, prefix)
    if result.unidentified_pages:
        names.append(f"{UNIDENTIFIED_STEM}.pdf")
    return [directory / name for name in names if (directory / name).exists()]


def _is_same_file(first: Path, second: Path) -> bool:
    try:
        return first.exists() and second.exists() and first.samefile(second)
    except OSError:
        return False


def _available_path(target: Path) -> Path:
    candidate, counter = target, 2
    while candidate.exists():
        candidate = target.with_name(f"{target.stem}_{counter}{target.suffix}")
        counter += 1
    return candidate


def _resolve_target(target: Path, source: Path, on_conflict: str) -> Path:
    # O PDF de origem nunca é sobrescrito, mesmo quando "substituir" foi escolhido.
    if _is_same_file(target, source) or on_conflict == ON_CONFLICT_KEEP_BOTH:
        return _available_path(target)
    return target


def _write_pages(reader: PdfReader, pages: list[int], target: Path) -> None:
    """Grava em arquivo temporário e só então publica com o nome definitivo."""
    writer = PdfWriter()
    for index in pages:
        writer.add_page(reader.pages[index])

    temporary = target.with_name(f"{target.name}.part")
    try:
        with temporary.open("wb") as stream:
            writer.write(stream)
        written_pages = len(PdfReader(str(temporary)).pages)
        if written_pages != len(pages):
            raise PdfAnalysisError(
                f"Arquivo gerado com {written_pages} página(s); esperadas {len(pages)}."
            )
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def export_documents(
    result: AnalysisResult,
    output_dir: str | Path,
    prefix: str = "",
    on_conflict: str = ON_CONFLICT_KEEP_BOTH,
    progress: ProgressCallback | None = None,
) -> list[ExportItem]:
    """Grava um PDF por CT-e. Falha em um documento não interrompe os demais."""
    directory = Path(output_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PdfAnalysisError(f"Não foi possível criar a pasta de destino: {exc}") from exc

    reader = _open_reader(result.source)
    jobs: list[tuple[CteDocument | None, list[int], str]] = [
        (document, document.pages, name)
        for document, name in zip(result.documents, plan_filenames(result.documents, prefix))
    ]
    if result.unidentified_pages:
        jobs.append((None, result.unidentified_pages, f"{UNIDENTIFIED_STEM}.pdf"))

    items: list[ExportItem] = []
    for position, (document, pages, name) in enumerate(jobs, start=1):
        target = _resolve_target(directory / name, result.source, on_conflict)
        item = ExportItem(document=document, path=target)
        try:
            _write_pages(reader, pages, target)
        except (PyPdfError, PdfAnalysisError, OSError, ValueError) as exc:
            item.error = str(exc)
        items.append(item)
        if progress:
            progress(position, len(jobs))
    return items
