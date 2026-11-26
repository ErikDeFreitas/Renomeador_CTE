"""Executa tarefas do motor fora da thread da interface, com progresso e cancelamento."""

import threading
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal

from renomeador_cte import cte_engine as engine
from renomeador_cte.xml_engine import ErroPasta


class Cancelado(Exception):
    """Lançada pelo callback de progresso quando o usuário cancela."""


class Tarefa(QThread):
    progresso = Signal(int, int)
    concluida = Signal(object)
    falhou = Signal(str)
    cancelada = Signal()

    def __init__(self, funcao: Callable[[Callable[[int, int], None]], object], parent=None):
        super().__init__(parent)
        self._funcao = funcao
        self._cancelar = threading.Event()

    def cancelar(self) -> None:
        self._cancelar.set()

    def _ao_progredir(self, feito: int, total: int) -> None:
        self.progresso.emit(feito, total)
        if self._cancelar.is_set():
            raise Cancelado()

    def run(self) -> None:
        try:
            resultado = self._funcao(self._ao_progredir)
        except Cancelado:
            self.cancelada.emit()
        except (engine.PdfAnalysisError, ErroPasta) as exc:
            self.falhou.emit(str(exc))
        except Exception as exc:  # a interface precisa sempre sair do estado "ocupado"
            self.falhou.emit(f"Erro inesperado: {exc}")
        else:
            self.concluida.emit(resultado)
