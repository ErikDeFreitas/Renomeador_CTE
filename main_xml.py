"""Ponto de entrada do Renomeador de XML avulso (.exe ou `python main_xml.py`)."""

import sys

from renomeador_cte.modulo_xml import MODULO
from tcm_ui.avulso import rodar_avulso


def main() -> None:
    sys.exit(rodar_avulso(MODULO))


if __name__ == "__main__":
    main()
