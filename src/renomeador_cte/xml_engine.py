"""Motor do Renomeador de XML: dá a cada XML de CT-e de uma pasta o número do CT-e (<nCT>) como nome.

Só stdlib. A leitura não altera nada; a renomeação acontece na própria pasta e nunca sobrescreve arquivos:
se o nome <nCT>.xml já estiver em uso, o XML fica com o nome que tem (estado NOME_EM_USO).
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

NAMESPACE_CTE = "http://www.portalfiscal.inf.br/cte"

PRONTO = "pronto"  # vai ganhar um nome novo
JA_NOMEADO = "ja_nomeado"  # já se chama <nCT>.xml
SEM_NUMERO = "sem_numero"  # XML sem <nCT> (outro documento, evento etc.)
ERRO = "erro"  # não foi possível ler o XML
NOME_EM_USO = "nome_em_uso"  # <nCT>.xml já existe na pasta: o XML não é renomeado

Progresso = Callable[[int, int], None]


class ErroPasta(Exception):
    """A pasta não existe ou não pode ser lida."""


@dataclass
class ItemXml:
    origem: Path
    numero: str = ""
    estado: str = PRONTO
    novo_nome: str = ""  # nome planejado (estado PRONTO)
    aviso: str = ""  # ex.: número repetido em outro XML
    erro: str = ""  # falha na leitura ou na renomeação
    renomeado: Path | None = None  # caminho final, depois de renomear

    @property
    def revisar(self) -> bool:
        return self.estado in (SEM_NUMERO, ERRO, NOME_EM_USO) or bool(self.aviso or self.erro)

    @property
    def nome_desejado(self) -> str:
        return f"{self.numero}.xml" if self.numero else ""


@dataclass
class AnaliseXml:
    pasta: Path
    itens: list[ItemXml] = field(default_factory=list)

    def contar(self, estado: str) -> int:
        return sum(1 for item in self.itens if item.estado == estado)


def ler_numero(caminho: Path) -> str:
    """Número do CT-e (<nCT>) do XML, ou "" se não houver. Aceita o XML com ou sem o namespace do CT-e."""
    raiz = ET.parse(caminho).getroot()
    no = raiz.find(f".//{{{NAMESPACE_CTE}}}nCT")
    if no is None:
        no = next((e for e in raiz.iter() if isinstance(e.tag, str) and e.tag.rsplit("}", 1)[-1] == "nCT"), None)
    texto = (no.text or "").strip() if no is not None else ""
    if texto and not texto.isdigit():
        raise ValueError(f"<nCT> com valor inválido: {texto!r}")
    return texto


def analisar_pasta(pasta: str | Path, progresso: Progresso | None = None) -> AnaliseXml:
    """Lê os XMLs da pasta (sem subpastas) e planeja os nomes novos. Não altera nada."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ErroPasta(f"A pasta não existe ou não é uma pasta:\n{pasta}")
    try:
        arquivos = sorted((p for p in pasta.iterdir() if p.is_file()), key=lambda p: p.name.casefold())
    except OSError as exc:
        raise ErroPasta(f"Não foi possível abrir a pasta:\n{pasta}\n\n{exc}") from exc

    xmls = [p for p in arquivos if p.suffix.lower() == ".xml"]
    analise = AnaliseXml(pasta)
    total = len(xmls)
    if progresso:
        progresso(0, total)
    for indice, caminho in enumerate(xmls, 1):
        item = ItemXml(caminho)
        try:
            item.numero = ler_numero(caminho)
        except Exception as exc:  # XML quebrado, sem permissão, valor inválido...
            item.estado, item.erro = ERRO, str(exc) or type(exc).__name__
        else:
            if not item.numero:
                item.estado = SEM_NUMERO
            elif caminho.name.casefold() == f"{item.numero}.xml":
                item.estado = JA_NOMEADO
        analise.itens.append(item)
        if progresso:
            progresso(indice, total)

    # nome novo: nunca o de um arquivo que já está na pasta nem o de outro XML desta leitura (sem _1, _2...)
    ocupados = {p.name.casefold() for p in arquivos}
    for item in analise.itens:
        if item.estado == PRONTO:
            if item.nome_desejado.casefold() in ocupados:
                item.estado = NOME_EM_USO
            else:
                item.novo_nome = item.nome_desejado
                ocupados.add(item.novo_nome.casefold())

    repetidos = Counter(item.numero for item in analise.itens if item.numero)
    for item in analise.itens:
        if repetidos[item.numero] > 1:
            item.aviso = f"O número {item.numero} aparece em {repetidos[item.numero]} XMLs desta pasta."
    return analise


def renomear(analise: AnaliseXml, progresso: Progresso | None = None) -> AnaliseXml:
    """Renomeia os itens prontos. Uma falha fica no item e não interrompe os demais."""
    prontos = [item for item in analise.itens if item.estado == PRONTO and item.renomeado is None]
    total = len(prontos)
    if progresso:
        progresso(0, total)
    for indice, item in enumerate(prontos, 1):
        destino = analise.pasta / item.novo_nome
        if destino.exists():  # surgiu depois da leitura
            item.estado, item.novo_nome = NOME_EM_USO, ""
        else:
            try:
                os.rename(item.origem, destino)  # no Windows, falha se o destino existir: nunca sobrescreve
            except OSError as exc:
                item.erro = exc.strerror or str(exc)
            else:
                item.renomeado, item.erro = destino, ""
        if progresso:
            progresso(indice, total)
    return analise
