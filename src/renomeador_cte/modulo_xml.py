"""MODULO do Renomeador de XML (mesmo repositório e versão do Renomeador de CT-e). Leve: sem a tela."""

from tcm_ui.modulo import Contexto, Modulo, Pagina

from renomeador_cte import __version__, dados


def criar(contexto: Contexto):
    from renomeador_cte.instancia_xml import RenomeadorXml  # import pesado só quando o módulo é aberto
    return RenomeadorXml(contexto)


MODULO = Modulo(
    id="renomeador_xml",
    nome="Renomeador de XML",
    icone="arquivo",
    versao=__version__,
    grupo_ad="SF-RenomeadorCTE",  # mesmo grupo do Renomeador de CT-e
    repositorio="ErikDeFreitas/Renomeador_CTE",
    nome_exe="RenomeadorXML.exe",
    pasta_dados=dados.PASTA,
    paginas=(Pagina("renomear", "Renomear XMLs",
                    "Cada XML de CT-e da pasta recebe o número do CT-e como nome.", "arquivo"),),
    criar=criar,
)
