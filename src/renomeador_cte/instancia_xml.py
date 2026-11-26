"""Instância do Renomeador de XML aberta na casca ou no avulso."""

from PySide6.QtWidgets import QWidget
from tcm_ui.modulo import Contexto

from renomeador_cte.tela_xml import TelaRenomearXml


class RenomeadorXml:
    def __init__(self, contexto: Contexto):
        self.contexto = contexto
        self.tela: TelaRenomearXml | None = None

    def widget(self, chave_pagina: str) -> QWidget:
        if chave_pagina != "renomear":
            raise KeyError(chave_pagina)
        if self.tela is None:
            self.tela = TelaRenomearXml(self.contexto)
        return self.tela

    def acoes_cabecalho(self, chave_pagina: str) -> list[QWidget]:
        return []

    def pode_fechar(self) -> bool:
        return self.tela is None or not self.tela.rodando
