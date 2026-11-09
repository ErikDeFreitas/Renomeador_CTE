# Gera dist/RenomeadorCTE.exe. Requer: pip install pyinstaller
# Uso: pyinstaller --noconfirm RenomeadorCTE.spec

a = Analysis(
    ["main.py"],
    datas=[("styles.qss", ".")],
    excludes=["tkinter", "numpy", "PIL", "matplotlib", "pandas", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="RenomeadorCTE",
    icon="assets/app.ico",
    console=False,
)
