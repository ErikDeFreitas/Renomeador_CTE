"""Atualização automática a partir das Releases do GitHub. Não depende da interface.

Sequência: consulta a última Release, baixa o executável ao lado do atual, confere
o SHA-256, troca os arquivos e abre a nova versão. O Windows não permite apagar um
executável em uso, então a versão anterior é renomeada para ".old" e quem a apaga é
a nova versão, ao abrir. Se a nova versão não abrir, o ".old" continua disponível.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from version import __version__

REPOSITORY = "ErikDeFreitas/Renomeador_CTE"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
DOWNLOAD_URL_PREFIX = f"https://github.com/{REPOSITORY}/releases/download/"
EXE_ASSET_NAME = "RenomeadorCTE.exe"
HASH_ASSET_NAME = f"{EXE_ASSET_NAME}.sha256"

CHECK_TIMEOUT_SECONDS = 8
CHECK_ATTEMPTS = 3
DOWNLOAD_TIMEOUT_SECONDS = 30
DOWNLOAD_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2.0
CHUNK_SIZE = 256 * 1024
MAX_HASH_FILE_SIZE = 1024
CLEANUP_ATTEMPTS = 60
CLEANUP_DELAY_SECONDS = 1.0
RENAME_ATTEMPTS = 5
RENAME_DELAY_SECONDS = 0.5

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_HASH_RE = re.compile(r"^([0-9a-fA-F]{64})(?:\s|$)")
_NETWORK_ERRORS = (OSError, http.client.HTTPException)


class UpdateError(Exception):
    """Erro com mensagem pronta para ser exibida ao usuário."""


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    exe_url: str
    hash_url: str
    size: int


def can_self_update() -> bool:
    """Só o executável empacotado para Windows pode se substituir."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION_RE.match(text.strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def is_newer(candidate: str, current: str) -> bool:
    candidate_version, current_version = parse_version(candidate), parse_version(current)
    return bool(candidate_version and current_version and candidate_version > current_version)


def parse_hash(text: str) -> str:
    match = _HASH_RE.match(text.strip())
    if not match:
        raise UpdateError("O arquivo de verificação da atualização é inválido.")
    return match[1].lower()


def parse_release(payload: dict, current_version: str = __version__) -> ReleaseInfo | None:
    """Devolve a Release somente se for mais nova e tiver os dois arquivos esperados."""
    tag = payload.get("tag_name") or ""
    if payload.get("draft") or payload.get("prerelease") or not is_newer(tag, current_version):
        return None
    assets = {asset.get("name"): asset for asset in payload.get("assets") or []}
    exe, hash_file = assets.get(EXE_ASSET_NAME), assets.get(HASH_ASSET_NAME)
    if not exe or not hash_file:
        return None
    exe_url, hash_url = exe.get("browser_download_url", ""), hash_file.get("browser_download_url", "")
    if not (exe_url.startswith(DOWNLOAD_URL_PREFIX) and hash_url.startswith(DOWNLOAD_URL_PREFIX)):
        return None
    return ReleaseInfo(tag.lstrip("v"), exe_url, hash_url, int(exe.get("size") or 0))


def _open_url(url: str, timeout: int):
    request = urllib.request.Request(url, headers={"User-Agent": f"RenomeadorCTE/{__version__}"})
    return urllib.request.urlopen(request, timeout=timeout)


def find_update(
    current_version: str = __version__, stop: threading.Event | None = None
) -> ReleaseInfo | None:
    """Sem internet, sem Release ou com resposta inesperada: apenas não há atualização.

    Falhas de rede são repetidas porque podem ser momentâneas. Uma resposta HTTP de
    erro não é: 404, por exemplo, significa que ainda não há Release publicada.
    `stop` interrompe as novas tentativas quando o programa está fechando.
    """
    for attempt in range(CHECK_ATTEMPTS):
        try:
            with _open_url(LATEST_RELEASE_URL, CHECK_TIMEOUT_SECONDS) as response:
                return parse_release(json.loads(response.read()), current_version)
        except urllib.error.HTTPError:
            return None
        except _NETWORK_ERRORS:
            pause = stop.wait(RETRY_DELAY_SECONDS) if stop else time.sleep(RETRY_DELAY_SECONDS)
            if pause or attempt == CHECK_ATTEMPTS - 1:
                return None
        except (ValueError, TypeError, AttributeError):
            return None
    return None


def download_update(
    release: ReleaseInfo,
    target: Path,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
) -> bool:
    """Baixa e confere o executável, repetindo em caso de queda de conexão.

    Devolve False se o usuário cancelar.
    """
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            return _download_once(release, target, progress, cancel)
        except urllib.error.HTTPError as exc:
            raise UpdateError(f"Não foi possível baixar a atualização: {exc}") from exc
        except PermissionError as exc:
            raise UpdateError("Sem permissão para gravar na pasta do programa.") from exc
        except _NETWORK_ERRORS as exc:
            if attempt == DOWNLOAD_ATTEMPTS - 1:
                raise UpdateError(f"Não foi possível baixar a atualização: {exc}") from exc
            if cancel and cancel.wait(RETRY_DELAY_SECONDS):
                return False
    return False


def _download_once(
    release: ReleaseInfo,
    target: Path,
    progress: Callable[[int, int], None] | None,
    cancel: threading.Event | None,
) -> bool:
    """Em qualquer resultado diferente de sucesso, o arquivo parcial é removido."""
    completed = False
    try:
        with _open_url(release.hash_url, DOWNLOAD_TIMEOUT_SECONDS) as response:
            raw_hash = response.read(MAX_HASH_FILE_SIZE)
        expected = parse_hash(raw_hash.decode("ascii", errors="replace"))

        digest = hashlib.sha256()
        received = 0
        with _open_url(release.exe_url, DOWNLOAD_TIMEOUT_SECONDS) as response, target.open("wb") as stream:
            total = release.size or int(response.headers.get("Content-Length") or 0)
            while chunk := response.read(CHUNK_SIZE):
                if cancel and cancel.is_set():
                    return False
                stream.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)

        if digest.hexdigest() != expected:
            raise UpdateError("O arquivo baixado não passou na verificação de integridade.")
        completed = True
        return True
    finally:
        if not completed:
            _discard(target)


def _discard(path: Path) -> None:
    """Um antivírus pode segurar o arquivo; nesse caso, a próxima abertura o remove."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _move_with_retry(source: Path, destination: Path) -> None:
    """Antivírus e OneDrive podem segurar o arquivo por alguns instantes."""
    for attempt in range(RENAME_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == RENAME_ATTEMPTS - 1:
                raise
            time.sleep(RENAME_DELAY_SECONDS)


def launch_executable(executable: Path) -> None:
    # A variável faz o novo processo extrair seus próprios arquivos em vez de
    # herdar a pasta temporária desta instância, que será apagada ao fechar.
    environment = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        [str(executable)], env=environment, cwd=str(executable.parent), creationflags=flags
    )


def previous_version_path(executable: Path) -> Path:
    return executable.with_name(f"{executable.name}.old")


def download_path(executable: Path) -> Path:
    return executable.with_name(f"{executable.name}.new")


def install_and_restart(
    new_file: Path,
    executable: Path,
    launcher: Callable[[Path], None] = launch_executable,
) -> None:
    """Coloca a nova versão no lugar da atual e a abre, desfazendo tudo em caso de falha."""
    previous = previous_version_path(executable)
    try:
        previous.unlink(missing_ok=True)
        _move_with_retry(executable, previous)
    except OSError as exc:
        _discard(new_file)
        raise UpdateError(f"Não foi possível preparar a atualização: {exc}") from exc

    try:
        _move_with_retry(new_file, executable)
        launcher(executable)
    except OSError as exc:
        os.replace(previous, executable)  # restaura a versão que estava funcionando
        _discard(new_file)
        raise UpdateError(f"Não foi possível instalar a atualização: {exc}") from exc


def remove_previous_version(
    executable: Path,
    attempts: int = CLEANUP_ATTEMPTS,
    delay: float = CLEANUP_DELAY_SECONDS,
) -> bool:
    """Apaga a versão anterior, aguardando o processo antigo terminar de fechar."""
    _discard(download_path(executable))
    previous = previous_version_path(executable)
    for attempt in range(attempts):
        try:
            previous.unlink(missing_ok=True)
            return True
        except OSError:
            if attempt < attempts - 1:
                time.sleep(delay)
    return False


def start_cleanup() -> None:
    executable = Path(sys.executable)
    threading.Thread(target=remove_previous_version, args=(executable,), daemon=True).start()
