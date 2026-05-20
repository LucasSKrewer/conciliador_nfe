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
    ultima_importacao  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_nota_status_sefaz   ON nota_consolidada(em_sefaz);
CREATE INDEX IF NOT EXISTS idx_nota_status_sistema ON nota_consolidada(em_sistema);
CREATE INDEX IF NOT EXISTS idx_nota_cartao        ON nota_consolidada(marcacao_cartao);
CREATE INDEX IF NOT EXISTS idx_nota_cnpj          ON nota_consolidada(cnpj_emitente);
CREATE INDEX IF NOT EXISTS idx_nota_data          ON nota_consolidada(data_emissao);

-- ------------------------------------------------------------
-- IMPORTACAO
--   Log de cada execução de importação (auditoria simples).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS importacao (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo_sefaz       TEXT,
    arquivo_sistema     TEXT,
    notas_sefaz         INTEGER NOT NULL DEFAULT 0,
    notas_sistema       INTEGER NOT NULL DEFAULT 0,
    notas_total         INTEGER NOT NULL DEFAULT 0,
    executado_em        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
