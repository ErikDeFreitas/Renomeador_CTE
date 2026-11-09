"""Gera dist/RenomeadorCTE.exe e dist/RenomeadorCTE.exe.sha256.

Uso: python build.py [--tag v1.1.0]
Com --tag, o build é recusado se a tag não coincidir com version.py.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

from updater import EXE_ASSET_NAME, HASH_ASSET_NAME
from version import __version__

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="tag da Release, que deve coincidir com version.py")
    tag = parser.parse_args().tag
    if tag and tag != f"v{__version__}":
        print(f"A tag {tag} não coincide com version.py ({__version__}).", file=sys.stderr)
        return 1

    work_dir = Path(tempfile.gettempdir()) / "renomeador_cte_build"
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--log-level", "WARN",
         "--workpath", str(work_dir), "--distpath", str(DIST), "RenomeadorCTE.spec"],
        cwd=ROOT,
        check=True,
    )

    executable = DIST / EXE_ASSET_NAME
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    (DIST / HASH_ASSET_NAME).write_text(f"{digest}  {EXE_ASSET_NAME}\n", encoding="ascii", newline="\n")
    print(f"Versão {__version__}\n{executable}\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
