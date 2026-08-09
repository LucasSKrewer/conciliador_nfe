# Conciliador NF-e

Local Flask application that **reconciles Brazilian electronic tax documents** (NF-e,
CT-e and NFS-e) between what the tax authority recorded and what was actually entered
into the company's ERP.

> **Context for non-Brazilian readers:** every commercial invoice in Brazil is issued
> electronically and registered with the state tax authority (SEFAZ), each carrying a
> 44-digit access key. Companies must enter those same documents into their own ERP.
> The two sides drift apart constantly, and finding the gap by hand is a monthly chore.
> This tool does the matching.

Inputs:

1. **NF-e from SEFAZ** — `.xlsx` listing the invoices issued against the company's tax ID
   (typical FSist export: `FSist-NFe-Recebidas-<CNPJ>-<date>.xlsx`).
2. **CT-e from SEFAZ** — `.xlsx` listing incoming freight documents (`FSist-CTe-...-<date>.xlsx`).
3. **NFS-e from the city** — `.xlsx` from the national/municipal service-invoice portal
   (`NFSe_Recebidas_<period>.xlsx`). The unique 50-digit DANFSe key is extracted from the URL.
4. **Internal system (ERP)** — `.csv` with NF-e *and* CT-e *and* NF-S already entered
   (`;`-delimited, with a `Chave` column holding the 44-digit key where applicable).
   Routing is automatic:
   - Model 55 → NF-e (`nota_consolidada`)
   - Model 57 → CT-e (`cte_consolidada`)
   - No key → tries to match an existing NFe or NFS-e; otherwise creates a synthetic NFS

It shows at a glance:

- Which documents have **not been entered** into the ERP yet (the point of the tool)
- Which are already entered (present in both sources)
- Which were paid by **card** and don't need entering (marked manually)
- Which are **service invoices** (municipal NFS-e — these never appear in FSist)

## How it works

Matching is done on the **44-digit NF-e key**, which is present in both spreadsheets.
Re-importing is **idempotent**: run it as many times as you like without losing manual
card markings or notes.

## Requirements

- Python 3.9 or newer
- Windows, Linux or macOS

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### First run

Put both files in the project folder:

- The SEFAZ `.xlsx` (e.g. `FSist-NFe-Recebidas-*.xlsx`)
- The internal system `.csv` (e.g. `Notas de Entrada.csv`)

Then run:

```bash
python init_db.py
```

That creates `conciliador.db` with every reconciled document. You can also pass paths
explicitly:

```bash
python init_db.py --sefaz path/FSist-NFe.xlsx --cte path/FSist-CTe.xlsx --sistema path/notas.csv
```

To start with an empty database and import everything through the web UI instead:

```bash
python init_db.py --vazio
```

### Starting the server

```bash
python app.py
```

(or double-click `iniciar.bat` on Windows). Then open:

- **On this machine:** http://localhost:5001
- **Other PCs on the network:** http://[MACHINE-IP]:5001

## Document statuses

Status labels are shown in the UI in Portuguese:

| Status          | When it appears                                                          |
|-----------------|--------------------------------------------------------------------------|
| `Não lançado`   | Registered at SEFAZ but **not** entered in the ERP                        |
| `Lançado`       | Present in both sources (SEFAZ + ERP)                                     |
| `Cartão`        | Marked manually — paid by card, no entry needed                           |
| `NF de Serviço` | In the ERP but **not** at SEFAZ — municipal NFS-e, which FSist never lists |

## Features

- **Dashboard** with totals by status and by amount, filterable by month
- **Document list** with filters (status, month, search by key/number/issuer/note/amount, tax ID)
- **CT-e list** with the same filters, plus carrier and shipper
- **Mark as card** in one click (survives re-imports) — NF-e only; CT-e has no card flag
- **Free-text note** per document (also persistent)
- **"Lançou" column** showing which ERP user entered the document (when the CSV has a `Usuário` column)
- **NF-S without an electronic key** (municipal NFS-e) enter via a synthetic key
  `NFS-<code>-<number>` and show up as "NF de Serviço"
- **Hidden suppliers** (`/ocultos`): register tax IDs or company-name patterns to hide their
  documents from every view — useful for recurring services, intra-group billing, etc.
- **Amount search** accepts Brazilian (`1.796,52`) and international (`1796.52`) formats,
  as well as partial matches (`1796`)
- **Cancelled documents** (status "Cancelada" / "NFS-e Cancelada") are skipped automatically
  by all three importers and removed from the database if already present
- **Re-import** from the web UI (1 to 4 optional files) — no server restart

## Expected spreadsheet formats

Column names below are the literal headers in the source files and stay in Portuguese.

### SEFAZ (.xlsx)

Header on row 1, with (among others) these columns:

| Column        | Content                    |
|---------------|----------------------------|
| Emissão       | Issue date                 |
| Chave         | NF-e key (44 digits)       |
| Número        | Document number            |
| Valor         | Total amount               |
| Emitente CNPJ | Supplier tax ID            |
| Emitente      | Supplier legal name        |

Any other FSist columns are ignored.

### CT-e from SEFAZ (.xlsx, optional)

Typical FSist format (`FSist-CTe-*.xlsx`). Columns used:

| Column                         | Content                                         |
|--------------------------------|-------------------------------------------------|
| Chave                          | CT-e key (44 digits)                            |
| Emissão                        | Issue date                                      |
| Número / Série                 | CT-e identification                             |
| Modal                          | Road, air, etc.                                 |
| Tipo Serviço                   | Normal, subcontracted, …                        |
| Valor                          | Freight amount                                  |
| Valor da Carga                 | Value of the goods being transported            |
| Emitente CNPJ / Emitente / UF  | Carrier                                         |
| Remetente CNPJ/CPF / Remetente | Who shipped the load                            |
| NFe Chaves                     | Keys of the invoices carried (kept for future cross-referencing) |

### Internal system (.csv)

`;`-delimited, encoded as `cp1252` (Windows-1252) or UTF-8, with at least these columns:

| Column         | Content                                                              |
|----------------|----------------------------------------------------------------------|
| Chave          | NF-e key (44 digits)                                                 |
| Número Nota    | Document number                                                      |
| Data Emissão   | Issue date                                                           |
| Valor Contábil | Total amount (falls back to `Valor Faturado` / `Valor Produtos`)      |
| Razão Social   | Supplier legal name                                                  |
| Usuário        | Who entered the document in the ERP (optional — shown in the "Lançou" column) |

Amounts in Brazilian format (`1.234,56`) are accepted.

## Backup

All state lives in `conciliador.db`. Copy that single file for a full backup (it includes
your card markings and notes). The spreadsheets themselves don't need to be kept — you can
re-import them at any time.
