"""Instância do Renomeador de CT-e aberta na casca ou no avulso."""

from PySide6.QtWidgets import QWidget
from tcm_ui.modulo import Contexto

from renomeador_cte.tela import TelaRenomear


class Renomeador:
    def __init__(self, contexto: Contexto):
        self.contexto = contexto
        self.tela: TelaRenomear | None = None

    def widget(self, chave_pagina: str) -> QWidget:
        if chave_pagina != "separar":
            raise KeyError(chave_pagina)
        if self.tela is None:
            self.tela = TelaRenomear(self.contexto)
        return self.tela

    def acoes_cabecalho(self, chave_pagina: str) -> list[QWidget]:
        return []

    def pode_fechar(self) -> bool:
        # só no meio de uma leitura/geração; um PDF lido e não gerado se refaz em segundos, e o aviso
        # da janela ("tarefa em andamento... será interrompida") não serve para esse caso
        return self.tela is None or not self.tela.rodando
