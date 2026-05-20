# Conciliador NF-e

Aplicação Flask local que **concilia documentos fiscais eletrônicos** (NF-e,
CT-e e NFS-e) entre o que foi recebido na SEFAZ/prefeitura e o que foi
lançado no sistema interno (ERP):

1. **NF-e SEFAZ** — planilha `.xlsx` com as NF-e recebidas pelo CNPJ da empresa
   (formato típico do FSist: `FSist-NFe-Recebidas-<CNPJ>-<data>.xlsx`).
2. **CT-e SEFAZ** — planilha `.xlsx` com os Conhecimentos de Transporte
   recebidos (formato `FSist-CTe-...-<data>.xlsx`).
3. **NFS-e Prefeitura** — planilha `.xlsx` do portal NFS-e nacional/municipal
   (formato `NFSe_Recebidas_<período>.xlsx`). Chave única DANFSe de 50 dígitos
   extraída da URL.
4. **Sistema interno (ERP)** — arquivo `.csv` com NF-e *e* CT-e *e* NF-S já
   lançados (delimitado por `;`, com coluna `Chave` contendo a chave de 44
   dígitos quando aplicável). O roteamento é automático:
   - Modelo 55 → NF-e (`nota_consolidada`)
   - Modelo 57 → CT-e (`cte_consolidada`)
   - Sem chave → tenta casar com NFe ou NFS-e existentes; senão cria NFS sintética

Mostra rapidamente:

- Quais documentos **ainda não foram lançados** no sistema (foco do trabalho)
- Quais já foram lançados (bateram nas duas fontes)
- Quais são pagos com **cartão** e não precisam ser lançados (marcação manual)
- Quais NF-e são **NF de Serviço** (NFS-e da prefeitura — não aparecem no FSist)

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
python init_db.py --sefaz caminho/FSist-NFe.xlsx --cte caminho/FSist-CTe.xlsx --sistema caminho/notas.csv
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
- **Lista de notas** com filtros (status, mês, busca por chave/número/emitente/observação/valor, CNPJ)
- **Lista de CT-e** com mesmos filtros, mais transportadora e remetente
- **Marcar como cartão** com 1 clique (persistente entre reimportações) — só NF-e, CT-e não tem
- **Observação livre** por documento (também persistente)
- **Coluna "Lançou"** exibindo qual usuário do ERP lançou (se a coluna `Usuário` estiver presente no CSV)
- **NF-S sem chave eletrônica** (NFS-e da prefeitura) entram via chave sintética `NFS-<cód>-<nº>` e aparecem como "NF de Serviço"
- **Fornecedores ocultos** (`/ocultos`): cadastre CNPJs ou padrões de razão social pra esconder notas/CT-e desses fornecedores de todas as visões (útil pra serviços recorrentes, intra-grupo, etc.)
- **Busca por valor** aceita formato BR (`1.796,52`) e PT (`1796.52`), além de parcial (`1796`)
- **Notas canceladas** (status "Cancelada" / "NFS-e Cancelada") são puladas
  automaticamente nos 3 importadores e removidas do banco se já existiam
- **Reimportar** pela tela web (1 a 4 arquivos opcionais) — sem parar o servidor

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

### CT-e SEFAZ (.xlsx, opcional)

Formato típico do FSist (`FSist-CTe-*.xlsx`). Colunas usadas:

| Coluna             | Conteúdo                       |
|--------------------|--------------------------------|
| Chave              | Chave CT-e (44 dígitos)        |
| Emissão            | Data de emissão                |
| Número / Série     | Identificação do CT-e          |
| Modal              | Rodoviário, Aéreo, etc.        |
| Tipo Serviço       | Normal, Subcontratação, …      |
| Valor              | Valor do frete                 |
| Valor da Carga     | Valor das mercadorias transportadas |
| Emitente CNPJ / Emitente / UF | Transportadora        |
| Remetente CNPJ/CPF / Remetente | Quem despachou a carga |
| NFe Chaves         | Chaves das NF-e transportadas (preservado pra cross-reference futura) |

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
| Usuário        | Quem lançou a nota no ERP (opcional — aparece na coluna "Lançou" na tela) |

Valores em formato brasileiro (`1.234,56`) são aceitos.

## Backup

Todo o estado fica no arquivo `conciliador.db`. Copie esse arquivo para
backup completo (inclui suas marcações de cartão e observações). As
planilhas em si não precisam ser guardadas — você pode reimportá-las a
qualquer momento.
