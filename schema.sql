-- ============================================================
-- Conciliador NF-e — Schema SQLite
-- ============================================================

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ------------------------------------------------------------
-- NOTA_CONSOLIDADA
--   1 linha por NFe (chave de 44 dígitos é PK)
--   Flags em_sefaz/em_sistema são reescritas a cada importação.
--   marcacao_cartao e observacao são manuais e PRESERVADAS entre
--   reimportações (a importação faz UPSERT pela chave).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nota_consolidada (
    chave              TEXT    PRIMARY KEY,            -- chave NFe 44 dígitos
    numero             TEXT,                           -- número da nota
    serie              TEXT,
    cnpj_emitente      TEXT,
    emitente           TEXT,                           -- razão social do fornecedor
    valor              REAL,
    data_emissao       TEXT,                           -- ISO 'YYYY-MM-DD'
    em_sefaz           INTEGER NOT NULL DEFAULT 0,     -- 0/1
    em_sistema         INTEGER NOT NULL DEFAULT 0,     -- 0/1
    marcacao_cartao    INTEGER NOT NULL DEFAULT 0,     -- 0/1, manual
    observacao         TEXT,                           -- manual
    usuario_lancamento TEXT,                           -- nome do usuário que lançou no ERP
    ultima_importacao  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_nota_status_sefaz   ON nota_consolidada(em_sefaz);
CREATE INDEX IF NOT EXISTS idx_nota_status_sistema ON nota_consolidada(em_sistema);
CREATE INDEX IF NOT EXISTS idx_nota_cartao        ON nota_consolidada(marcacao_cartao);
CREATE INDEX IF NOT EXISTS idx_nota_cnpj          ON nota_consolidada(cnpj_emitente);
CREATE INDEX IF NOT EXISTS idx_nota_data          ON nota_consolidada(data_emissao);

-- ------------------------------------------------------------
-- CTE_CONSOLIDADA
--   1 linha por CT-e (chave de 44 dígitos, modelo 57)
--   Mesmo padrão da nota_consolidada: flags em_sefaz/em_sistema
--   reescritas por cada importação, marcacao_cartao/observacao
--   preservadas via UPSERT.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cte_consolidada (
    chave              TEXT    PRIMARY KEY,            -- chave CT-e 44 dígitos
    numero             TEXT,
    serie              TEXT,
    cnpj_emitente      TEXT,                           -- CNPJ da transportadora
    emitente           TEXT,                           -- razão social da transportadora
    emitente_uf        TEXT,
    modal              TEXT,                           -- Rodoviário, Aéreo, etc.
    tipo_servico       TEXT,                           -- Normal, Subcontratação, Redespacho...
    valor              REAL,                           -- valor do frete
    valor_carga        REAL,                           -- valor das mercadorias transportadas
    cnpj_remetente     TEXT,                           -- quem despachou a carga
    remetente          TEXT,
    nfe_chaves         TEXT,                           -- chaves NFe transportadas, separadas por vírgula
    data_emissao       TEXT,
    em_sefaz           INTEGER NOT NULL DEFAULT 0,
    em_sistema         INTEGER NOT NULL DEFAULT 0,
    marcacao_cartao    INTEGER NOT NULL DEFAULT 0,
    observacao         TEXT,
    usuario_lancamento TEXT,
    ultima_importacao  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_cte_status_sefaz   ON cte_consolidada(em_sefaz);
CREATE INDEX IF NOT EXISTS idx_cte_status_sistema ON cte_consolidada(em_sistema);
CREATE INDEX IF NOT EXISTS idx_cte_cartao         ON cte_consolidada(marcacao_cartao);
CREATE INDEX IF NOT EXISTS idx_cte_cnpj_emit      ON cte_consolidada(cnpj_emitente);
CREATE INDEX IF NOT EXISTS idx_cte_cnpj_rem       ON cte_consolidada(cnpj_remetente);
CREATE INDEX IF NOT EXISTS idx_cte_data           ON cte_consolidada(data_emissao);

-- ------------------------------------------------------------
-- NFSE_CONSOLIDADA
--   NF de Serviço Eletrônica (NFS-e) recebidas pela empresa,
--   vindas da planilha da prefeitura/nacional (NFSe_Recebidas...xlsx).
--   1 linha por NFS-e (chave DANFSe nacional = 50 dígitos, ou sintética
--   CNPJ+numero quando não disponível).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nfse_consolidada (
    chave              TEXT    PRIMARY KEY,            -- 50 dígitos DANFSe ou sintética
    cnpj_emitente      TEXT,                           -- só dígitos
    emitente           TEXT,                           -- razão social do prestador
    valor              REAL,
    competencia        TEXT,                           -- 'MM/AAAA'
    data_emissao       TEXT,                           -- ISO 'YYYY-MM-DD'
    situacao           TEXT,                           -- 'NFS-e Gerada', etc.
    danfse_url         TEXT,
    em_prefeitura      INTEGER NOT NULL DEFAULT 0,     -- na planilha NFS-e
    em_sistema         INTEGER NOT NULL DEFAULT 0,     -- bateu com CSV do ERP
    marcacao_cartao    INTEGER NOT NULL DEFAULT 0,     -- manual
    observacao         TEXT,                           -- manual
    usuario_lancamento TEXT,                           -- vindo do CSV no match
    ultima_importacao  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_nfse_status_pref ON nfse_consolidada(em_prefeitura);
CREATE INDEX IF NOT EXISTS idx_nfse_status_sis  ON nfse_consolidada(em_sistema);
CREATE INDEX IF NOT EXISTS idx_nfse_cnpj        ON nfse_consolidada(cnpj_emitente);
CREATE INDEX IF NOT EXISTS idx_nfse_data        ON nfse_consolidada(data_emissao);

-- ------------------------------------------------------------
-- FORNECEDOR_OCULTO
--   Lista de fornecedores a serem escondidos em TODAS as visões
--   (dashboard, listas, contagens). Match por CNPJ ou por padrão
--   da razão social (LIKE case-insensitive).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fornecedor_oculto (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj          TEXT,        -- só dígitos; opcional
    padrao_nome   TEXT,        -- string para LIKE %padrao% em emitente; opcional
    rotulo        TEXT,        -- nome amigável pra UI
    criado_em     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ------------------------------------------------------------
-- IMPORTACAO
--   Log de cada execução de importação (auditoria simples).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS importacao (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo_sefaz       TEXT,
    arquivo_cte         TEXT,
    arquivo_nfse        TEXT,
    arquivo_sistema     TEXT,
    notas_sefaz         INTEGER NOT NULL DEFAULT 0,
    ctes_sefaz          INTEGER NOT NULL DEFAULT 0,
    nfses_prefeitura    INTEGER NOT NULL DEFAULT 0,
    notas_sistema       INTEGER NOT NULL DEFAULT 0,
    ctes_sistema        INTEGER NOT NULL DEFAULT 0,
    nfses_sistema       INTEGER NOT NULL DEFAULT 0,
    notas_total         INTEGER NOT NULL DEFAULT 0,
    ctes_total          INTEGER NOT NULL DEFAULT 0,
    nfses_total         INTEGER NOT NULL DEFAULT 0,
    executado_em        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
