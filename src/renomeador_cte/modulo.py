"""MODULO do Renomeador de CT-e para a casca e o avulso. Leve: só dados e a fábrica (sem pypdf nem a tela)."""

from tcm_ui.modulo import Contexto, Modulo, Pagina

from renomeador_cte import __version__, dados


def criar(contexto: Contexto):
    from renomeador_cte.instancia import Renomeador  # import pesado só quando o módulo é aberto
    return Renomeador(contexto)


MODULO = Modulo(
    id="renomeador_cte",
    nome="Renomeador de CT-e",
    icone="tesoura",
    versao=__version__,
    grupo_ad="SF-RenomeadorCTE",
    repositorio="ErikDeFreitas/Renomeador_CTE",
    nome_exe="RenomeadorCTE.exe",
    pasta_dados=dados.PASTA,
    paginas=(Pagina("separar", "Separar e renomear",
                    "Um PDF por CT-e, nomeado pelo número. O arquivo original não é alterado.", "tesoura"),),
    criar=criar,
)
