# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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
