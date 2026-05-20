# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

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
