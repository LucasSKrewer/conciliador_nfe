# Conciliador NF-e

Aplicação Flask local que **concilia notas fiscais eletrônicas** entre duas fontes:

1. **SEFAZ** — planilha `.xlsx` com as NF-e recebidas pelo CNPJ da empresa
   (formato típico do FSist: `FSist-NFe-Recebidas-<CNPJ>-<data>.xlsx`).
2. **Sistema interno (ERP)** — arquivo `.csv` com as notas que **já foram lançadas**
   no seu sistema (delimitado por `;`, com uma coluna `Chave` contendo a chave NF-e
   de 44 dígitos).

Mostra rapidamente:

- Quais notas **ainda não foram lançadas** no sistema (foco do trabalho)
- Quais já foram lançadas (bateram nas duas fontes)
- Quais são pagas com **cartão** e não precisam ser lançadas (marcação manual)
- Quais são **NF de Serviço** (NFS-e da prefeitura — não aparecem no FSist)

## Como funciona

O matching é feito pela **chave NF-e de 44 dígitos**, que está presente nas
duas planilhas. A reimportação é **idempotente**: pode ser rodada quantas
vezes quiser sem perder as marcações manuais de cartão e observações.

## Requisitos

- Python 3.9 ou superior
- Windows, Linux ou macOS

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

### Primeira vez

Coloque os dois arquivos na pasta do projeto:

- O `.xlsx` da SEFAZ (ex: `FSist-NFe-Recebidas-*.xlsx`)
- O `.csv` do sistema interno (ex: `Notas de Entrada.csv`)

E rode:

```bash
python init_db.py
```

Isso cria `conciliador.db` com todas as notas conciliadas. Você também pode
passar os caminhos explicitamente:

```bash
python init_db.py --sefaz caminho/para/FSist.xlsx --sistema caminho/para/notas.csv
```

Se preferir começar com o banco vazio e importar tudo pela interface web depois:

```bash
python init_db.py --vazio
```

### Subir o servidor

```bash
python app.py
```

(ou duplo-clique em `iniciar.bat` no Windows). Acesse no navegador:

- **Neste computador:** http://localhost:5001
- **Outros PCs da rede:** http://[IP-DA-MÁQUINA]:5001

## Status de cada nota

| Status        | Quando aparece                                                              |
|---------------|-----------------------------------------------------------------------------|
| Não lançado   | A nota está na SEFAZ mas **não** foi lançada no sistema                     |
| Lançado       | A nota está nas duas planilhas (SEFAZ + Sistema)                            |
| Cartão        | Você marcou manualmente — pago com cartão, não precisa lançar               |
| NF de Serviço | Está no Sistema mas **não** na SEFAZ — NFS-e da prefeitura (FSist não lista) |

## Funcionalidades

- **Dashboard** com totais por status e por valor, filtrável por mês
- **Lista de notas** com filtros (status, mês, busca por número/emitente/observação, CNPJ)
- **Marcar como cartão** com 1 clique (persistente entre reimportações)
- **Observação livre** por nota (também persistente)
- **Reimportar** pela tela web, sem precisar parar o servidor

## Formato esperado das planilhas

### SEFAZ (.xlsx)

Cabeçalho na linha 1, com colunas (entre outras):

| Coluna  | Conteúdo                |
|---------|-------------------------|
| Emissão | Data de emissão         |
| Chave   | Chave NF-e (44 dígitos) |
| Número  | Número da nota          |
| Valor   | Valor total             |
| Emitente CNPJ | CNPJ do fornecedor |
| Emitente      | Razão social do fornecedor |

Outras colunas presentes no FSist são ignoradas.

### Sistema interno (.csv)

Delimitador `;`, encoding `cp1252` (Windows-1252) ou UTF-8, com pelo menos
estas colunas:

| Coluna         | Conteúdo                |
|----------------|-------------------------|
| Chave          | Chave NF-e (44 dígitos) |
| Número Nota    | Número da nota          |
| Data Emissão   | Data de emissão         |
| Valor Contábil | Valor total (ou `Valor Faturado` / `Valor Produtos` como fallback) |
| Razão Social   | Razão social do fornecedor |

Valores em formato brasileiro (`1.234,56`) são aceitos.

## Backup

Todo o estado fica no arquivo `conciliador.db`. Copie esse arquivo para
backup completo (inclui suas marcações de cartão e observações). As
planilhas em si não precisam ser guardadas — você pode reimportá-las a
qualquer momento.
