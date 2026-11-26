# Renomeador de CT-e

Separa um PDF com vários CT-es (DACTEs) em um arquivo por CT-e, cada um nomeado pelo
número do CT-e. O PDF original nunca é alterado.

## Usar

Baixe o `RenomeadorCTE.exe` da última [Release](../../releases/latest) e abra.

1. Arraste o PDF para a janela (ou clique para escolher o arquivo no computador).
2. Confira a tabela: número, emissão, tomador, páginas e o nome que cada arquivo vai ter.
   Linhas marcadas como "Revisar" pedem atenção (por exemplo, páginas sem chave nem número
   de CT-e, que ficam reunidas em um arquivo à parte).
3. Confirme a pasta de destino (botão **Procurar** para trocar) e clique em
   **Separar e renomear**. Por padrão, a pasta se chama
   `CTEs_<nome do PDF>` e fica ao lado do PDF original. Pode colar um caminho copiado do
   Explorer (com aspas) ou digitar um nome relativo, que vale a partir da pasta do PDF.

PDFs com senha só de proprietário (inclusive com criptografia AES) são lidos normalmente;
PDFs que pedem senha para abrir não são suportados.

O que fica salvo no computador é a escolha de tema (claro ou escuro) e o log. Os PDFs não são
copiados para lugar nenhum além da pasta de destino que você escolheu.

## Log

O `.exe` avulso grava o log em `%LOCALAPPDATA%\RenomeadorCTE\logs\renomeador_cte.log`, com os
erros e as exceções não tratadas. Dentro do Sistema Financeiro, o log é o da casca. Em caso de
problema, envie esse arquivo para a TI.

## Atualização automática

Ao abrir, o programa consulta a última Release no GitHub. Se houver versão nova, baixa em
segundo plano, confere o SHA-256, avisa e reinicia já atualizado. Sem internet, nada aparece.

Alguns antivírus sinalizam executáveis gerados com PyInstaller; se acontecer, libere o arquivo.

## Desenvolver

A interface vem da biblioteca [`tcm-ui`](https://github.com/ErikDeFreitas/Tcm-ui).

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python main.py
```

Para desenvolver junto com o `tcm-ui`, instale-o editável a partir do clone vizinho
(`.venv\Scripts\pip install -e ..\Tcm-ui`) antes do `pip install -e ".[dev]"`.

Testes (nunca escrevem no registro nem na pasta real de dados):

```
.venv\Scripts\python -m pytest -q
```

Os dados do programa (log) ficam em `%LOCALAPPDATA%\RenomeadorCTE`; defina `RENOMEADOR_DADOS`
para usar outra pasta, por exemplo em testes. Não coloque PDFs de CT-e reais no repositório:
eles têm dados de clientes e motoristas (`*.pdf` já está no `.gitignore`).

## Gerar o executável

```
powershell -File build.ps1
```

Gera `dist\RenomeadorCTE.exe` e `dist\RenomeadorCTE.exe.sha256`.

## Lançar uma versão

1. Suba `__version__` em `src/renomeador_cte/__init__.py` (ex.: `2.0.1`).
2. Crie a tag igual, com `v` na frente (`v2.0.1`), e envie-a para o GitHub.

O GitHub Actions (`.github/workflows/release.yml`) confere que a tag bate com `__version__`,
roda os testes, gera o `.exe` e o `.sha256` e publica a Release com os dois arquivos.
O `requirements.txt` fixa o `tcm-ui` numa tag (hoje `v1.5.0`), que precisa existir no GitHub.

## Módulo do Sistema Financeiro

O Renomeador também é um módulo da casca Sistema Financeiro (`MODULO` em
`src/renomeador_cte/modulo.py`, registrado no entry point `sistema_financeiro.modulos`).
Na casca ele aparece para quem está no grupo `SF-RenomeadorCTE`.

## Estrutura

| Pasta/arquivo                       | Conteúdo                                       |
|-------------------------------------|------------------------------------------------|
| `src/renomeador_cte/cte_engine.py`  | Leitura dos PDFs e regras de negócio (sem interface) |
| `src/renomeador_cte/worker.py`      | Execução em segundo plano para a janela        |
| `src/renomeador_cte/tela.py`        | Tela do módulo                                 |
| `src/renomeador_cte/instancia.py`   | Instância do módulo (casca e avulso)           |
| `src/renomeador_cte/modulo.py`      | Registro do módulo (`MODULO`)                  |
| `src/renomeador_cte/dados.py`       | Pasta de dados                                 |
| `main.py`                           | Ponto de entrada do `.exe` avulso              |
| `build.ps1`                         | Gera o `.exe` e o `.sha256`                    |
| `assets/`                           | Ícone do executável (`app.ico`)                |
| `tests/`                            | Testes (pytest)                                |
