import os
import subprocess
import sys
from importlib.metadata import entry_points
from pathlib import Path

import renomeador_cte
from renomeador_cte import dados
from renomeador_cte.modulo import MODULO


def test_valores_do_modulo():
    assert (MODULO.id, MODULO.nome, MODULO.icone) == ("renomeador_cte", "Renomeador de CT-e", "tesoura")
    assert (MODULO.grupo_ad, MODULO.repositorio, MODULO.nome_exe) == (
        "SF-RenomeadorCTE", "ErikDeFreitas/Renomeador_CTE", "RenomeadorCTE.exe")
    assert MODULO.versao == renomeador_cte.__version__ == "2.1.0"
    assert MODULO.pasta_dados == dados.PASTA
    assert MODULO.aplicacao_settings == "RenomeadorCTE"
    assert [(p.chave, p.titulo, p.subtitulo, p.icone) for p in MODULO.paginas] == [
        ("separar", "Separar e renomear",
         "Um PDF por CT-e, nomeado pelo número. O arquivo original não é alterado.", "tesoura")]


def test_entry_point_carrega_o_modulo():
    eps = {ep.name: ep for ep in entry_points(group="sistema_financeiro.modulos")}
    assert eps["renomeador_cte"].load() is MODULO


def test_modulo_e_leve(tmp_path):
    codigo = ("import sys, renomeador_cte.modulo; "
              "print(*[m in sys.modules for m in ('pypdf', 'renomeador_cte.tela')])")
    env = {**os.environ, "RENOMEADOR_DADOS": str(tmp_path / "nao_criar")}
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, check=True)
    assert saida.stdout.split() == ["False"] * 2
    assert not Path(tmp_path / "nao_criar").exists()
