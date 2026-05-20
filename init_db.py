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
    cols = {row[1] for row in conn.execute("PRAGMA table_info(nota_consolidada)")}
    if "usuario_lancamento" not in cols:
        conn.execute("ALTER TABLE nota_consolidada ADD COLUMN usuario_lancamento TEXT")

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

        inseridos = atualizados = ignorados = 0
        for linha in reader:
            chave = _chave(col(linha, "Chave"))
            if not chave:
                ignorados += 1
                continue
            numero       = _s(col(linha, "Número Nota", "Numero Nota"))
            data_emissao = _data_iso(col(linha, "Data Emissão", "Data Emissao"))
            valor        = _num_br(col(linha, "Valor Contábil", "Valor Contabil",
                                       "Valor Faturado", "Valor Produtos"))
            emitente     = _s(col(linha, "Razão Social", "Razao Social", "Nome Empresa"))
            usuario      = _s(col(linha, "Usuário", "Usuario"))

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

            if ja_existe:
                atualizados += 1
            else:
                inseridos += 1
    finally:
        f.close()
    return {"inseridos": inseridos, "atualizados": atualizados, "ignorados": ignorados}

# ── orquestração ─────────────────────────────────────────────────────────────

def executar_importacao(caminho_sefaz, caminho_sistema, db_path=DB_PATH):
    """Importa as 2 fontes e registra a execução.

    Comportamento ACUMULATIVO: importar uma planilha NÃO zera as flags
    em_sefaz/em_sistema das notas que vieram em importações anteriores.
    Assim você pode importar mês a mês (Abril, depois Maio, depois Junho)
    e o banco acumula tudo. Uma nota que saiu de uma planilha posterior
    permanece com a flag que ganhou na importação anterior.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    criar_banco(conn)

    r_sefaz = {"inseridos": 0, "atualizados": 0, "ignorados": 0}
    r_sis   = {"inseridos": 0, "atualizados": 0, "ignorados": 0}

    if caminho_sefaz and os.path.exists(caminho_sefaz):
        print(f"→ SEFAZ:  {caminho_sefaz}")
        r_sefaz = importar_sefaz(conn, caminho_sefaz)
        print(f"  inseridos={r_sefaz['inseridos']}  atualizados={r_sefaz['atualizados']}  ignorados={r_sefaz['ignorados']}")
    else:
        print(f"! Arquivo SEFAZ não encontrado: {caminho_sefaz}")

    if caminho_sistema and os.path.exists(caminho_sistema):
        print(f"→ Sistema: {caminho_sistema}")
        r_sis = importar_sistema(conn, caminho_sistema)
        print(f"  inseridos={r_sis['inseridos']}  atualizados={r_sis['atualizados']}  ignorados={r_sis['ignorados']}")
    else:
        print(f"! Arquivo Sistema não encontrado: {caminho_sistema}")

    notas_sefaz   = conn.execute("SELECT COUNT(*) FROM nota_consolidada WHERE em_sefaz=1").fetchone()[0]
    notas_sistema = conn.execute("SELECT COUNT(*) FROM nota_consolidada WHERE em_sistema=1").fetchone()[0]
    notas_total   = conn.execute("SELECT COUNT(*) FROM nota_consolidada").fetchone()[0]

    conn.execute("""
        INSERT INTO importacao (arquivo_sefaz, arquivo_sistema,
                                notas_sefaz, notas_sistema, notas_total)
        VALUES (?, ?, ?, ?, ?)
    """, (caminho_sefaz, caminho_sistema, notas_sefaz, notas_sistema, notas_total))

    conn.commit()
    conn.close()

    return {
        "sefaz":      r_sefaz,
        "sistema":    r_sis,
        "totais": {
            "em_sefaz":   notas_sefaz,
            "em_sistema": notas_sistema,
            "total":      notas_total,
        },
    }

def main():
    parser = argparse.ArgumentParser(description="Importa as planilhas SEFAZ e Sistema para o banco.")
    parser.add_argument("--sefaz",   help="Caminho do .xlsx FSist da SEFAZ (auto-detecta na pasta se omitido)")
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
    sistema = args.sistema if (args.sistema and os.path.exists(args.sistema)) else None

    if not sefaz and not sistema:
        print(f"Nenhuma planilha encontrada na pasta atual.\n"
              f"  - SEFAZ:   coloque um arquivo .xlsx do FSist (ou use --sefaz <caminho>)\n"
              f"  - Sistema: coloque '{ARQUIVO_SISTEMA_PADRAO}' (ou use --sistema <caminho>)\n"
              f"Para criar apenas o banco vazio e importar pela tela web, rode:\n"
              f"  python init_db.py --vazio", file=sys.stderr)
        sys.exit(1)

    resumo = executar_importacao(sefaz, sistema)

    print("\n── Resumo ──────────────────────────────────────────────")
    print(f"  Em SEFAZ:       {resumo['totais']['em_sefaz']:>6}")
    print(f"  Em Sistema:     {resumo['totais']['em_sistema']:>6}")
    print(f"  Total no banco: {resumo['totais']['total']:>6}")
    print("Pronto. Rode  python app.py  e acesse http://localhost:5000")

if __name__ == "__main__":
    main()
