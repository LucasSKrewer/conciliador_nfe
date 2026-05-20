"""
init_db.py — Conciliador NF-e

Cria o banco SQLite e importa as 2 planilhas:
  * SEFAZ (.xlsx)    — notas lançadas CONTRA a empresa (export do FSist
                       no formato "FSist-NFe-Recebidas-*.xlsx" ou similar)
  * Sistema (.csv)   — notas lançadas no seu sistema interno (ERP),
                       em CSV ponto-e-vírgula com a coluna "Chave"

A importação é IDEMPOTENTE: pode ser rodada várias vezes sem perder as
marcações manuais de "cartão" nem observações. O matching é feito pela
chave NF-e de 44 dígitos.

Uso:
    python init_db.py
    python init_db.py --sefaz "caminho\\FSist...xlsx" --sistema "caminho\\notas.csv"
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
from datetime import datetime, date

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

import openpyxl

DB_PATH       = "conciliador.db"
SCHEMA_PATH   = "schema.sql"
ARQUIVO_SEFAZ_PADRAO   = None   # detectado automaticamente na pasta atual
ARQUIVO_SISTEMA_PADRAO = "Notas de Entrada.csv"

# ── helpers ──────────────────────────────────────────────────────────────────

def _s(v):
    """Converte valor para string limpa, ou None."""
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None

def _chave(v):
    """Normaliza chave NFe: só dígitos, 44 caracteres."""
    if v is None:
        return None
    s = re.sub(r"\D", "", str(v))
    return s if len(s) == 44 else None

def _cnpj(v):
    """Normaliza CNPJ: só dígitos."""
    if v is None:
        return None
    s = re.sub(r"\D", "", str(v))
    return s if s else None

def _data_iso(v):
    """Aceita datetime/date/str e devolve 'YYYY-MM-DD' ou None."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    # tenta dd/mm/yyyy
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # tenta yyyy-mm-dd
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return None

def _num_br(v):
    """Converte número em formato BR ('1.234,56') ou normal para float."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    # remove separador de milhar (.) e troca decimal , por .
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

# ── banco ────────────────────────────────────────────────────────────────────

def criar_banco(conn):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    _aplicar_migrations(conn)
    conn.commit()

def _aplicar_migrations(conn):
    """Migrations idempotentes para bancos criados antes de novas colunas."""
    cols_nota = {row[1] for row in conn.execute("PRAGMA table_info(nota_consolidada)")}
    if "usuario_lancamento" not in cols_nota:
        conn.execute("ALTER TABLE nota_consolidada ADD COLUMN usuario_lancamento TEXT")

    cols_imp = {row[1] for row in conn.execute("PRAGMA table_info(importacao)")}
    for col, decl in [
        ("arquivo_cte",   "TEXT"),
        ("ctes_sefaz",    "INTEGER NOT NULL DEFAULT 0"),
        ("ctes_sistema",  "INTEGER NOT NULL DEFAULT 0"),
        ("ctes_total",    "INTEGER NOT NULL DEFAULT 0"),
    ]:
        if col not in cols_imp:
            conn.execute(f"ALTER TABLE importacao ADD COLUMN {col} {decl}")

# ── importadores ─────────────────────────────────────────────────────────────

def detectar_arquivo_sefaz(pasta="."):
    """Acha o arquivo FSist-NFe-Recebidas-*.xlsx mais recente."""
    candidatos = []
    for nome in os.listdir(pasta):
        if nome.lower().startswith("fsist-nfe-recebidas") and nome.lower().endswith(".xlsx"):
            candidatos.append(os.path.join(pasta, nome))
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)

def detectar_arquivo_cte(pasta="."):
    """Acha o arquivo FSist-CTe-*.xlsx mais recente."""
    candidatos = []
    for nome in os.listdir(pasta):
        low = nome.lower()
        if low.startswith("fsist-cte") and low.endswith(".xlsx"):
            candidatos.append(os.path.join(pasta, nome))
    if not candidatos:
        return None
    return max(candidatos, key=os.path.getmtime)

def importar_sefaz(conn, caminho):
    """Lê o xlsx da SEFAZ (FSist) e marca em_sefaz=1 nas notas encontradas.

    Colunas esperadas (cabeçalho na linha 1):
      0  Emissão
      1  Emissão Data/Hora
      2  Chave
      3  Mês/Ano
      4  Número
      5  Série
      6  Tipo
      7  Valor
      8  Status
      9  Manifestação
      10 Emitente CNPJ
      11 Emitente
      ...
    """
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    ws = wb.active
    inseridos = atualizados = ignorados = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        chave = _chave(row[2])
        if not chave:
            ignorados += 1
            continue
        data_emissao = _data_iso(row[0])
        numero       = _s(row[4])
        serie        = _s(row[5])
        valor        = _num_br(row[7])
        cnpj_emit    = _cnpj(row[10])
        emitente     = _s(row[11])

        ja_existe = conn.execute(
            "SELECT 1 FROM nota_consolidada WHERE chave=?", (chave,)
        ).fetchone()

        conn.execute("""
            INSERT INTO nota_consolidada
                (chave, numero, serie, cnpj_emitente, emitente, valor,
                 data_emissao, em_sefaz, ultima_importacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now','localtime'))
            ON CONFLICT(chave) DO UPDATE SET
                numero         = COALESCE(excluded.numero, nota_consolidada.numero),
                serie          = COALESCE(excluded.serie, nota_consolidada.serie),
                cnpj_emitente  = COALESCE(excluded.cnpj_emitente, nota_consolidada.cnpj_emitente),
                emitente       = COALESCE(excluded.emitente, nota_consolidada.emitente),
                valor          = COALESCE(excluded.valor, nota_consolidada.valor),
                data_emissao   = COALESCE(excluded.data_emissao, nota_consolidada.data_emissao),
                em_sefaz       = 1,
                ultima_importacao = datetime('now','localtime')
        """, (chave, numero, serie, cnpj_emit, emitente, valor, data_emissao))

        if ja_existe:
            atualizados += 1
        else:
            inseridos += 1

    wb.close()
    return {"inseridos": inseridos, "atualizados": atualizados, "ignorados": ignorados}

def importar_cte(conn, caminho):
    """Lê o xlsx de CT-e (FSist-CTe) e marca em_sefaz=1 em cte_consolidada.

    Colunas esperadas (cabeçalho linha 1):
      0  Chave
      1  Emissão
      4  Número
      5  Série
      7  Modal
      8  Tipo Serviço
      9  Valor (do frete)
     12  Valor da Carga
     13  Emitente CNPJ      (transportadora)
     14  Emitente
     16  Emitente UF
     25  Remetente CNPJ/CPF (quem despachou)
     26  Remetente
     38  NFe Chaves (com vírgula)
    """
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    ws = wb.active
    inseridos = atualizados = ignorados = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        chave = _chave(row[0])
        if not chave:
            ignorados += 1
            continue
        data_emissao  = _data_iso(row[1])
        numero        = _s(row[4])
        serie         = _s(row[5])
        modal         = _s(row[7])
        tipo_servico  = _s(row[8])
        valor         = _num_br(row[9])
        valor_carga   = _num_br(row[12])
        cnpj_emit     = _cnpj(row[13])
        emitente      = _s(row[14])
        emitente_uf   = _s(row[16])
        cnpj_rem      = _cnpj(row[25])
        remetente     = _s(row[26])
        nfe_chaves    = _s(row[38])

        ja_existe = conn.execute(
            "SELECT 1 FROM cte_consolidada WHERE chave=?", (chave,)
        ).fetchone()

        conn.execute("""
            INSERT INTO cte_consolidada
                (chave, numero, serie, cnpj_emitente, emitente, emitente_uf,
                 modal, tipo_servico, valor, valor_carga,
                 cnpj_remetente, remetente, nfe_chaves,
                 data_emissao, em_sefaz, ultima_importacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, datetime('now','localtime'))
            ON CONFLICT(chave) DO UPDATE SET
                numero         = COALESCE(excluded.numero, cte_consolidada.numero),
                serie          = COALESCE(excluded.serie, cte_consolidada.serie),
                cnpj_emitente  = COALESCE(excluded.cnpj_emitente, cte_consolidada.cnpj_emitente),
                emitente       = COALESCE(excluded.emitente, cte_consolidada.emitente),
                emitente_uf    = COALESCE(excluded.emitente_uf, cte_consolidada.emitente_uf),
                modal          = COALESCE(excluded.modal, cte_consolidada.modal),
                tipo_servico   = COALESCE(excluded.tipo_servico, cte_consolidada.tipo_servico),
                valor          = COALESCE(excluded.valor, cte_consolidada.valor),
                valor_carga    = COALESCE(excluded.valor_carga, cte_consolidada.valor_carga),
                cnpj_remetente = COALESCE(excluded.cnpj_remetente, cte_consolidada.cnpj_remetente),
                remetente      = COALESCE(excluded.remetente, cte_consolidada.remetente),
                nfe_chaves     = COALESCE(excluded.nfe_chaves, cte_consolidada.nfe_chaves),
                data_emissao   = COALESCE(excluded.data_emissao, cte_consolidada.data_emissao),
                em_sefaz       = 1,
                ultima_importacao = datetime('now','localtime')
        """, (chave, numero, serie, cnpj_emit, emitente, emitente_uf,
              modal, tipo_servico, valor, valor_carga,
              cnpj_rem, remetente, nfe_chaves, data_emissao))

        if ja_existe:
            atualizados += 1
        else:
            inseridos += 1

    wb.close()
    return {"inseridos": inseridos, "atualizados": atualizados, "ignorados": ignorados}

def _abrir_csv(caminho):
    """Abre o CSV tentando encodings comuns para texto pt-BR."""
    for enc in ("utf-8-sig", "cp1252", "latin-1", "utf-8"):
        try:
            f = open(caminho, "r", encoding=enc, newline="")
            f.readline()
            f.seek(0)
            return f, enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Não consegui ler {caminho} com encodings comuns.")

def importar_sistema(conn, caminho):
    """Lê o CSV do sistema interno e marca em_sistema=1 nas notas encontradas.

    Cabeçalho (delimitador ';'):
      Ano;Mes;Dia;Data Entrada;Número Nota;Data Emissão;Usuário;Tipo Documento;
      Tipo Vencimento;Código Empresa;Nome Empresa;Razão Social;Inscr.Est.;
      Código Estabelecimento;Cidade;UF;Natureza;Descrição;CFOP;
      Valor Produtos;Valor Faturado;Valor Contábil;...;Chave
    """
    f, _enc = _abrir_csv(caminho)
    try:
        reader = csv.DictReader(f, delimiter=";")
        # mapeia nomes possíveis ignorando acentos/maiúsculas — só precisamos da Chave
        def col(d, *names):
            for n in names:
                for k in d.keys():
                    if k and k.strip().lower() == n.lower():
                        return d[k]
            return None

        ins_nfe = atu_nfe = ins_cte = atu_cte = ignorados = 0
        for linha in reader:
            chave = _chave(col(linha, "Chave"))
            if not chave:
                ignorados += 1
                continue
            modelo = chave[20:22]   # 55=NFe, 57=CTe
            numero       = _s(col(linha, "Número Nota", "Numero Nota"))
            data_emissao = _data_iso(col(linha, "Data Emissão", "Data Emissao"))
            valor        = _num_br(col(linha, "Valor Contábil", "Valor Contabil",
                                       "Valor Faturado", "Valor Produtos"))
            emitente     = _s(col(linha, "Razão Social", "Razao Social", "Nome Empresa"))
            usuario      = _s(col(linha, "Usuário", "Usuario"))

            if modelo == "57":
                ja_existe = conn.execute(
                    "SELECT 1 FROM cte_consolidada WHERE chave=?", (chave,)
                ).fetchone()
                conn.execute("""
                    INSERT INTO cte_consolidada
                        (chave, numero, emitente, valor, data_emissao,
                         em_sistema, usuario_lancamento, ultima_importacao)
                    VALUES (?, ?, ?, ?, ?, 1, ?, datetime('now','localtime'))
                    ON CONFLICT(chave) DO UPDATE SET
                        numero             = COALESCE(cte_consolidada.numero, excluded.numero),
                        emitente           = COALESCE(cte_consolidada.emitente, excluded.emitente),
                        valor              = COALESCE(cte_consolidada.valor, excluded.valor),
                        data_emissao       = COALESCE(cte_consolidada.data_emissao, excluded.data_emissao),
                        em_sistema         = 1,
                        usuario_lancamento = COALESCE(excluded.usuario_lancamento, cte_consolidada.usuario_lancamento),
                        ultima_importacao  = datetime('now','localtime')
                """, (chave, numero, emitente, valor, data_emissao, usuario))
                if ja_existe: atu_cte += 1
                else:         ins_cte += 1
            else:
                ja_existe = conn.execute(
                    "SELECT 1 FROM nota_consolidada WHERE chave=?", (chave,)
                ).fetchone()
                conn.execute("""
                    INSERT INTO nota_consolidada
                        (chave, numero, emitente, valor, data_emissao,
                         em_sistema, usuario_lancamento, ultima_importacao)
                    VALUES (?, ?, ?, ?, ?, 1, ?, datetime('now','localtime'))
                    ON CONFLICT(chave) DO UPDATE SET
                        numero             = COALESCE(nota_consolidada.numero, excluded.numero),
                        emitente           = COALESCE(nota_consolidada.emitente, excluded.emitente),
                        valor              = COALESCE(nota_consolidada.valor, excluded.valor),
                        data_emissao       = COALESCE(nota_consolidada.data_emissao, excluded.data_emissao),
                        em_sistema         = 1,
                        usuario_lancamento = COALESCE(excluded.usuario_lancamento, nota_consolidada.usuario_lancamento),
                        ultima_importacao  = datetime('now','localtime')
                """, (chave, numero, emitente, valor, data_emissao, usuario))
                if ja_existe: atu_nfe += 1
                else:         ins_nfe += 1
    finally:
        f.close()
    return {
        "nfe": {"inseridos": ins_nfe, "atualizados": atu_nfe},
        "cte": {"inseridos": ins_cte, "atualizados": atu_cte},
        "ignorados": ignorados,
    }

# ── orquestração ─────────────────────────────────────────────────────────────

def executar_importacao(caminho_sefaz, caminho_sistema, db_path=DB_PATH, caminho_cte=None):
    """Importa as 3 fontes (NFe SEFAZ, CTe SEFAZ, CSV do ERP) e registra a execução.

    Comportamento ACUMULATIVO: importar uma planilha NÃO zera as flags
    em_sefaz/em_sistema. Cada parâmetro de caminho é opcional.

    O CSV do ERP traz NFe e CT-e misturados; o roteamento é feito pelo
    modelo da chave (55=NFe → nota_consolidada, 57=CTe → cte_consolidada).
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    criar_banco(conn)

    r_sefaz = {"inseridos": 0, "atualizados": 0, "ignorados": 0}
    r_cte   = {"inseridos": 0, "atualizados": 0, "ignorados": 0}
    r_sis   = {"nfe": {"inseridos": 0, "atualizados": 0},
               "cte": {"inseridos": 0, "atualizados": 0},
               "ignorados": 0}

    if caminho_sefaz and os.path.exists(caminho_sefaz):
        print(f"→ NFe SEFAZ: {caminho_sefaz}")
        r_sefaz = importar_sefaz(conn, caminho_sefaz)
        print(f"  inseridos={r_sefaz['inseridos']}  atualizados={r_sefaz['atualizados']}  ignorados={r_sefaz['ignorados']}")

    if caminho_cte and os.path.exists(caminho_cte):
        print(f"→ CT-e SEFAZ: {caminho_cte}")
        r_cte = importar_cte(conn, caminho_cte)
        print(f"  inseridos={r_cte['inseridos']}  atualizados={r_cte['atualizados']}  ignorados={r_cte['ignorados']}")

    if caminho_sistema and os.path.exists(caminho_sistema):
        print(f"→ Sistema (ERP): {caminho_sistema}")
        r_sis = importar_sistema(conn, caminho_sistema)
        print(f"  NFe: inseridos={r_sis['nfe']['inseridos']} atualizados={r_sis['nfe']['atualizados']}"
              f" | CTe: inseridos={r_sis['cte']['inseridos']} atualizados={r_sis['cte']['atualizados']}"
              f" | ignorados={r_sis['ignorados']}")

    notas_sefaz   = conn.execute("SELECT COUNT(*) FROM nota_consolidada WHERE em_sefaz=1").fetchone()[0]
    notas_sistema = conn.execute("SELECT COUNT(*) FROM nota_consolidada WHERE em_sistema=1").fetchone()[0]
    notas_total   = conn.execute("SELECT COUNT(*) FROM nota_consolidada").fetchone()[0]
    ctes_sefaz    = conn.execute("SELECT COUNT(*) FROM cte_consolidada WHERE em_sefaz=1").fetchone()[0]
    ctes_sistema  = conn.execute("SELECT COUNT(*) FROM cte_consolidada WHERE em_sistema=1").fetchone()[0]
    ctes_total    = conn.execute("SELECT COUNT(*) FROM cte_consolidada").fetchone()[0]

    conn.execute("""
        INSERT INTO importacao (arquivo_sefaz, arquivo_cte, arquivo_sistema,
                                notas_sefaz, ctes_sefaz, notas_sistema, ctes_sistema,
                                notas_total, ctes_total)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (caminho_sefaz, caminho_cte, caminho_sistema,
          notas_sefaz, ctes_sefaz, notas_sistema, ctes_sistema,
          notas_total, ctes_total))

    conn.commit()
    conn.close()

    return {
        "sefaz":   r_sefaz,
        "cte":     r_cte,
        "sistema": r_sis,
        "totais": {
            "nfe": {"em_sefaz": notas_sefaz, "em_sistema": notas_sistema, "total": notas_total},
            "cte": {"em_sefaz": ctes_sefaz,  "em_sistema": ctes_sistema,  "total": ctes_total},
        },
    }

def main():
    parser = argparse.ArgumentParser(description="Importa as planilhas SEFAZ (NFe + CTe) e o CSV do ERP.")
    parser.add_argument("--sefaz",   help="Caminho do .xlsx FSist-NFe-Recebidas (auto-detecta na pasta se omitido)")
    parser.add_argument("--cte",     help="Caminho do .xlsx FSist-CTe (auto-detecta na pasta se omitido)")
    parser.add_argument("--sistema", help="Caminho do .csv Notas de Entrada", default=ARQUIVO_SISTEMA_PADRAO)
    parser.add_argument("--vazio",   action="store_true",
                        help="Cria apenas o banco vazio (sem importar nada); use a tela web depois")
    args = parser.parse_args()

    if args.vazio:
        conn = sqlite3.connect(DB_PATH)
        criar_banco(conn)
        conn.close()
        print(f"Banco vazio criado em {DB_PATH}. Rode  python app.py  e importe pela tela web.")
        return

    sefaz   = args.sefaz   or detectar_arquivo_sefaz(".")
    cte     = args.cte     or detectar_arquivo_cte(".")
    sistema = args.sistema if (args.sistema and os.path.exists(args.sistema)) else None

    if not sefaz and not cte and not sistema:
        print(f"Nenhuma planilha encontrada na pasta atual.\n"
              f"  - NFe SEFAZ: coloque um arquivo FSist-NFe-Recebidas-*.xlsx (ou --sefaz)\n"
              f"  - CT-e SEFAZ: coloque um arquivo FSist-CTe-*.xlsx (ou --cte)\n"
              f"  - ERP:       coloque '{ARQUIVO_SISTEMA_PADRAO}' (ou --sistema)\n"
              f"Para criar apenas o banco vazio e importar pela tela web, rode:\n"
              f"  python init_db.py --vazio", file=sys.stderr)
        sys.exit(1)

    resumo = executar_importacao(sefaz, sistema, caminho_cte=cte)

    print("\n── Resumo ──────────────────────────────────────────────")
    print(f"  NFe — em SEFAZ:  {resumo['totais']['nfe']['em_sefaz']:>6}  em Sistema: {resumo['totais']['nfe']['em_sistema']:>6}  total: {resumo['totais']['nfe']['total']:>6}")
    print(f"  CTe — em SEFAZ:  {resumo['totais']['cte']['em_sefaz']:>6}  em Sistema: {resumo['totais']['cte']['em_sistema']:>6}  total: {resumo['totais']['cte']['total']:>6}")
    print("Pronto. Rode  python app.py  e acesse http://localhost:5001")

if __name__ == "__main__":
    main()
