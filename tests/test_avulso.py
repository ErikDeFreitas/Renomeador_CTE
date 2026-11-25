import importlib.util
import re
from pathlib import Path

from PySide6.QtCore import QSettings

from renomeador_cte.modulo import MODULO

RAIZ = Path(__file__).resolve().parent.parent

# Cópia (só para este teste) das regras do atualizador 1.0.0 (updater.py), que ainda roda
# nas máquinas dos usuários e precisa aceitar a Release da 2.0.0.
_HASH_RE_1_0_0 = re.compile(r"^([0-9a-fA-F]{64})(?:\s|$)")
_VERSION_RE_1_0_0 = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_PREFIXO_1_0_0 = "https://github.com/ErikDeFreitas/Renomeador_CTE/releases/download/"
_EXE = "RenomeadorCTE.exe"


def _versao_1_0_0(texto):
    m = _VERSION_RE_1_0_0.match(texto.strip())
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


def _aceita_pelo_atualizador_1_0_0(payload, versao_atual="1.0.0"):
    """Mesmas regras de `updater.parse_release` da 1.0.0: True se a Release seria oferecida."""
    tag = payload.get("tag_name") or ""
    nova, atual = _versao_1_0_0(tag), _versao_1_0_0(versao_atual)
    if payload.get("draft") or payload.get("prerelease") or not (nova and atual and nova > atual):
        return False
    ativos = {a.get("name"): a for a in payload.get("assets") or []}
    exe, sha = ativos.get(_EXE), ativos.get(f"{_EXE}.sha256")
    if not exe or not sha:
        return False
    return (exe.get("browser_download_url", "").startswith(_PREFIXO_1_0_0)
            and sha.get("browser_download_url", "").startswith(_PREFIXO_1_0_0))


def _carregar_main():
    spec = importlib.util.spec_from_file_location("main_renomeador", RAIZ / "main.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_build_usa_nome_do_exe():
    script = (RAIZ / "build.ps1").read_text(encoding="utf-8")
    workflow = (RAIZ / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert MODULO.nome_exe == "RenomeadorCTE.exe"
    assert '$nome = "RenomeadorCTE"' in script
    # o .sha256 é gravado como "<hash>  RenomeadorCTE.exe" + quebra de linha
    assert '"$hash  $nome.exe`n"' in script
    assert "--collect-data tcm_ui --collect-data renomeador_cte" in script
    assert "assets/app.ico" in script
    assert "dist/RenomeadorCTE.exe" in workflow and "dist/RenomeadorCTE.exe.sha256" in workflow
    assert (RAIZ / "assets" / "app.ico").is_file()


def test_requirements_fixa_tcm_ui():
    texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"tcm-ui @ git\+https://github.com/ErikDeFreitas/Tcm-ui@v\d+\.\d+\.\d+", texto)


def test_workflow_confere_versao():
    texto = (RAIZ / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "renomeador_cte.__version__" in texto


def test_release_aceita_pelo_atualizador_1_0_0():
    base = _PREFIXO_1_0_0 + "v2.0.0/"
    payload = {
        "tag_name": "v2.0.0", "draft": False, "prerelease": False,
        "assets": [
            {"name": _EXE, "size": 40_000_000, "browser_download_url": base + _EXE},
            {"name": f"{_EXE}.sha256", "size": 90, "browser_download_url": base + f"{_EXE}.sha256"},
        ],
    }
    assert _aceita_pelo_atualizador_1_0_0(payload)
    assert not _aceita_pelo_atualizador_1_0_0({**payload, "assets": payload["assets"][:1]})

    # o .sha256 que o build.ps1 grava ("<hash>  RenomeadorCTE.exe\n") vale para as duas regex
    from tcm_ui import atualizador

    hash_ = "ab12" * 16
    conteudo = f"{hash_}  {_EXE}\n"
    antiga = _HASH_RE_1_0_0.match(conteudo.strip())
    nova = re.match(r"\s*([0-9a-fA-F]{64})", conteudo)  # regra de tcm_ui.atualizador.baixar_e_verificar
    assert antiga[1].lower() == nova[1].lower() == hash_
    assert atualizador.versao_tupla("v2.0.0") > atualizador.versao_tupla("1.0.0")


def test_migrar_tema(tmp_path):
    main = _carregar_main()

    def config(nome):
        return QSettings(str(tmp_path / nome), QSettings.IniFormat)

    escuro = config("a.ini")
    escuro.setValue("theme", "dark")
    main.migrar_tema(escuro)
    assert escuro.value("aparencia/tema") == "escuro"
    assert escuro.value("theme") == "dark"

    claro = config("b.ini")
    claro.setValue("theme", "light")
    main.migrar_tema(claro)
    assert claro.value("aparencia/tema") == "claro"
    assert claro.value("theme") == "light"

    ja_gravado = config("c.ini")
    ja_gravado.setValue("theme", "dark")
    ja_gravado.setValue("aparencia/tema", "claro")
    main.migrar_tema(ja_gravado)
    assert ja_gravado.value("aparencia/tema") == "claro"

    outro = config("d.ini")
    outro.setValue("theme", "sepia")
    main.migrar_tema(outro)
    assert not outro.contains("aparencia/tema")

    vazio = config("e.ini")
    main.migrar_tema(vazio)
    assert not vazio.contains("aparencia/tema")
