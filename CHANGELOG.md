# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.6.0] — 2026-05-20

### Adicionado
- **Suporte a NFS-e** (Nota Fiscal de Serviço Eletrônica) da prefeitura:
  - Nova tabela `nfse_consolidada` com chave DANFSe nacional (50 dígitos)
    ou sintética por CNPJ+competência+valor.
  - Importador `importar_nfse()` lê o `.xlsx` do portal NFS-e
    (`NFSe_Recebidas_*.xlsx`).
  - Rota `/nfse` com lista, filtros (status, mês, busca em chave/CNPJ/
    emitente/observação/valor), marcação cartão e observação.
  - Bloco dedicado no dashboard com 3 cards (não lançadas / lançadas / total).
  - Card "NFS-e não lançadas" no topo do dashboard ao lado de NFe e CT-e.
  - Item "NFS-e" no menu superior.
  - Tela `/importar` aceita agora até **4 arquivos opcionais**.
  - `init_db.py --nfse <caminho>` no CLI.
- **Match inteligente NF sem chave**: quando o CSV traz uma linha NF sem
  chave eletrônica, o importador tenta antes de criar uma NFS sintética:
  (a) achar NFe existente em `nota_consolidada` por **número + razão**
  ou **número + valor exato** — cobre o caso de ERP não preencher chave;
  (b) achar NFSe na planilha da prefeitura por CNPJ ou razão fuzzy.
- **Consolidação automática** (`consolidar_nfs_com_nfes`) roda após cada
  importação do CSV e remove NFS sintéticas duplicadas com NFes reais.
- **Migração de NFS sintéticas** (`migrar_nfs_sinteticas`) move entradas
  antigas pra `nfse_consolidada` quando bater com a planilha da prefeitura.

### Mudado
- **Notas canceladas** (status "Cancelada", "NFS-e Cancelada") nos 3
  importadores agora são puladas e **removidas do banco** se já estavam
  lá. Mantém o banco enxuto e evita conferência de notas sem efeito fiscal.
- **Dashboard reorganizado**: blocos detalhados de CT-e e NFS-e ficam
  ANTES da tabela "Notas não lançadas mais recentes". Tabela reduzida de
  15 para 8 linhas pra não empurrar o conteúdo pra baixo.
- Parser de data `_data_iso` agora aceita ano de 2 dígitos (`dd/mm/yy`) —
  formato comum em exports NFS-e.
- Parser de "Emitida por" usa separador estrito ` - ` (espaço-traço-espaço)
  pra não confundir com o sufixo `-XX` do CNPJ.
- Card "NF de Serviço" removido do topo do dashboard — agora as NFS-e da
  prefeitura têm seu próprio card "NFS-e não lançadas".

## [0.5.0] — 2026-05-20

### Adicionado
- **NF de Serviço sem chave eletrônica** entra no banco via chave
  sintética `NFS-<Código Empresa>-<Número da Nota>`. Antes, qualquer
  linha do CSV sem chave NF-e de 44 dígitos era ignorada, escondendo
  as NFS-e da prefeitura. Agora elas aparecem como status "NF de Serviço"
  (em_sefaz=0, em_sistema=1).
- **Fornecedores ocultos** (`/ocultos`): nova página de gerenciamento e
  tabela `fornecedor_oculto`. Cadastre uma regra por **CNPJ** (só dígitos)
  ou por **padrão na razão social** (LIKE case-insensitive) — ou os dois.
  Notas e CT-e que baterem em qualquer critério ficam invisíveis em
  **todas** as visões: dashboard (contagens e valores), lista `/notas`,
  lista `/ctes`, recentes do dashboard. Migration automática cria a
  tabela em bancos existentes.
- **Busca por valor** nas listas `/notas` e `/ctes`. Aceita formato
  brasileiro (`1.796,52`), português (`1796.52`) ou parcial (`1796`).
  No `/ctes` também procura no campo "Valor da Carga".

### Mudado
- **CT-e perdeu a opção de "Cartão"** na UI (frete não é pago por
  cartão). Removida coluna do checkbox da lista `/ctes`, card "CT-e
  cartão" do dashboard, e opção "Cartão" do filtro de status. Endpoint
  POST `/ctes/<chave>/cartao` permanece no backend pra compatibilidade.
- Filtro de status do `/ctes` ganha opção "Só no Sistema" no lugar de
  "NF de Serviço" (nome mais semântico no contexto de CT-e).

## [0.4.0] — 2026-05-19

### Adicionado
- **Suporte a CT-e** (Conhecimento de Transporte Eletrônico):
  - Nova tabela `cte_consolidada` com campos específicos (modal,
    transportadora, remetente, valor da carga, chaves NF-e transportadas).
  - Novo importador `importar_cte()` lê a planilha FSist-CTe.
  - O importador do CSV do ERP agora **roteia automaticamente** pela
    chave: modelo 55 → `nota_consolidada`, modelo 57 → `cte_consolidada`.
  - Nova rota `/ctes` com lista, filtros (status, mês, busca em
    chave/número/transportadora/remetente/observação) e ações de
    marcação cartão / observação.
  - Dashboard mostra um card **"CT-e não lançados"** no topo, ao lado
    do card de notas; e uma seção dedicada de CT-e abaixo com 4 cards.
  - Item "CT-e" no menu superior.
- Tela `/importar` aceita até 3 arquivos opcionais (NFe SEFAZ, CT-e
  SEFAZ, CSV do ERP). Selecione apenas os que tiver agora.
- `init_db.py --cte <caminho>` para importação via CLI.
- Migration idempotente para adicionar `cte_consolidada` e as novas
  colunas em `importacao` em bancos criados antes desta versão.

### Mudado
- Card **"Não lançadas"** do dashboard renomeado para **"Notas não
  lançadas"** para diferenciar do novo card **"CT-e não lançados"**.
- Card "Lançadas" renomeado para "Notas lançadas" pela mesma razão.

## [0.3.0] — 2026-05-19

### Mudado
- **Importação agora é acumulativa.** Antes, `executar_importacao()`
  zerava `em_sefaz`/`em_sistema` de todas as notas antes de importar —
  ou seja, importar uma planilha de outro mês fazia as notas do mês
  anterior caírem para o status `desconhecido`. Agora as flags são só
  *somadas* a cada importação, permitindo importar mês a mês sem perder
  o estado dos anteriores. Notas marcadas como cartão e observações já
  eram preservadas; com essa mudança, o status visual também passa a
  ser estável entre importações de períodos diferentes.

## [0.2.0] — 2026-05-19

### Adicionado
- Coluna **"Lançou"** na lista de notas, mostrando o usuário do ERP que
  fez o lançamento (lido da coluna `Usuário` / `Usuario` do CSV).
- Migration automática (`_aplicar_migrations` em `init_db.py`) que adiciona
  a nova coluna em bancos criados antes desta versão, sem perder dados.

### Corrigido
- Destaque do menu superior agora distingue **"Notas"** (lista completa,
  sem filtro de status) de **"Não lançadas"** (apenas `status=nao_lancado`).
  Antes os dois links ficavam realçados ao mesmo tempo na rota `/notas`.

## [0.1.0] — 2026-05-19

### Adicionado
- Versão inicial.
- Importação de NF-e da SEFAZ (`.xlsx` no formato FSist) e do sistema
  interno (`.csv` com coluna `Chave`).
- Matching pela chave NF-e de 44 dígitos com UPSERT idempotente.
- 4 status derivados: Não lançado, Lançado, Cartão (manual), NF de Serviço.
- Dashboard com totais e valor por status, filtrável por mês de emissão.
- Lista de notas com filtros (status, mês, busca textual em chave/número/
  emitente/observação, CNPJ emitente) e paginação.
- Marcação manual de "cartão" e campo de observação por nota,
  **preservados entre reimportações**.
- Importação pela interface web (upload das duas planilhas).
- Log rotativo de erros (`conciliador_erros.log`).
