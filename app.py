"""
app.py — Conciliador NF-e
Servidor Flask local. Acesse em http://localhost:5001
"""

import logging
import os
import socket
import sqlite3
import sys
import tempfile
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler

from flask import (Flask, g, redirect, render_template_string, request,
                   url_for, flash, jsonify)
from werkzeug.exceptions import HTTPException

import init_db as importador

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

DB_PATH  = "conciliador.db"
LOG_PATH = "conciliador_erros.log"

app = Flask(__name__)
app.secret_key = "conciliador-nfe-local"   # uso local, sem login

# ── log ──────────────────────────────────────────────────────────────────────

def _configurar_log():
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s — %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG); fh.setFormatter(fmt)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO); ch.setFormatter(fmt)
    root = logging.getLogger(); root.setLevel(logging.DEBUG)
    root.addHandler(fh); root.addHandler(ch)
    app.logger.addHandler(fh); app.logger.setLevel(logging.DEBUG)

_configurar_log()
log = logging.getLogger("conciliador")

@app.errorhandler(Exception)
def handle_exception(e):
    if isinstance(e, HTTPException):
        return e
    log.error(f"ERRO {request.method} {request.path}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    return ("<div style='font-family:monospace;padding:32px'>"
            f"<h2 style='color:#c0392b'>Erro interno</h2>"
            f"<p>{type(e).__name__}: {e}</p>"
            f"<p>Detalhes em <code>{LOG_PATH}</code>.</p></div>", 500)

# ── banco ────────────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def fechar_db(_=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows

# ── helpers de exibição ──────────────────────────────────────────────────────

# definição centralizada do "status" derivado
STATUS_SQL = """
    CASE
        WHEN marcacao_cartao=1                  THEN 'cartao'
        WHEN em_sefaz=1 AND em_sistema=1        THEN 'lancado'
        WHEN em_sefaz=1 AND em_sistema=0        THEN 'nao_lancado'
        WHEN em_sefaz=0 AND em_sistema=1        THEN 'nf_servico'
        ELSE 'desconhecido'
    END
"""

STATUS_LABEL = {
    "cartao":       ("Cartão",        "badge-laranja"),
    "lancado":      ("Lançado",       "badge-verde"),
    "nao_lancado":  ("Não lançado",   "badge-vermelho"),
    "nf_servico":   ("NF de Serviço", "badge-azul"),
    "desconhecido": ("?",              "badge-cinza"),
}

def fmt_data(d):
    if not d:
        return ""
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return d or ""

def fmt_cnpj(c):
    if not c or len(c) != 14:
        return c or ""
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"

def fmt_valor(v):
    if v is None:
        return ""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ── layout ───────────────────────────────────────────────────────────────────

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;font-size:14px;background:#f4f5f0;color:#1a1a2e}
a{color:#1B5E20;text-decoration:none}a:hover{color:#E65100;text-decoration:underline}
.nav{background:#1B5E20;color:#fff;padding:0 24px;display:flex;align-items:center;height:60px;gap:20px;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.18)}
.nav-brand{background:#fff;padding:6px 14px;border-radius:8px;display:flex;align-items:center;line-height:0}
.nav-brand img{height:38px;display:block}
.nav a{color:#c8e0c8;font-size:13px;padding:6px 12px;border-radius:6px;transition:.15s}
.nav a:hover,.nav a.ativo{color:#fff;background:rgba(255,255,255,.13);text-decoration:none}
.nav-sep{flex:1}
.nav-user{font-size:12px;color:#a8c8a8}
.page{max-width:1400px;margin:0 auto;padding:24px 20px}
.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:10px}
.page-title{font-size:20px;font-weight:600;color:#1B5E20}
.page-sub{font-size:12px;color:#999}
.card{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:20px;margin-bottom:16px}
.card-title{font-size:13px;font-weight:600;color:#555;margin-bottom:14px;text-transform:uppercase;letter-spacing:.5px}
.stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.stat{background:#fff;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(0,0,0,.07);text-decoration:none;color:inherit;display:block;transition:.15s}
.stat:hover{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.12);text-decoration:none}
.stat-label{font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}
.stat-val{font-size:24px;font-weight:700;color:#1a1a2e}
.stat-sub{font-size:11px;color:#999;margin-top:3px}
.stat.verde .stat-val{color:#2E7D32}
.stat.vermelho .stat-val{color:#c0392b}
.stat.laranja .stat-val{color:#E65100}
.stat.cinza .stat-val{color:#666}
.stat.azul .stat-val{color:#1B5E20}
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eaf2ea;color:#1B5E20;font-weight:600;padding:10px 12px;text-align:left;border-bottom:2px solid #c8e0c8;white-space:nowrap}
td{padding:9px 12px;border-bottom:1px solid #ecefe9;color:#333;vertical-align:middle}
tr:hover td{background:#f5faf5}
.right{text-align:right}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.mono{font-family:Consolas,Menlo,monospace;font-size:12px}
.chave{font-family:Consolas,Menlo,monospace;font-size:11px;color:#666}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;white-space:nowrap}
.badge-verde{background:#e8f5e9;color:#1B5E20}
.badge-vermelho{background:#fdecea;color:#b71c1c}
.badge-laranja{background:#fff3e0;color:#E65100}
.badge-azul{background:#e3f2fd;color:#0D47A1}
.badge-cinza{background:#f1f3f5;color:#666}
.btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:.15s;text-decoration:none}
.btn-primary{background:#E65100;color:#fff}.btn-primary:hover{background:#BF360C;color:#fff;text-decoration:none}
.btn-secondary{background:#eaf2ea;color:#1B5E20}.btn-secondary:hover{background:#d6e8d6;color:#1B5E20;text-decoration:none}
.btn-sm{padding:5px 12px;font-size:12px}
.btn-laranja{background:#fff3e0;color:#E65100;border:1px solid #ffd9b3}
.btn-laranja:hover{background:#E65100;color:#fff;text-decoration:none}
.btn-cinza{background:#f1f3f5;color:#666;border:1px solid #d8dde2}
.btn-cinza:hover{background:#d8dde2;color:#333;text-decoration:none}
.filtros{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px;align-items:flex-end}
.form-group{display:flex;flex-direction:column;gap:4px}
.form-group label{font-size:12px;color:#666;font-weight:500}
.form-group input,.form-group select,.form-group textarea{padding:8px 10px;border:1px solid #d0dccc;border-radius:7px;font-size:13px;color:#1a1a2e;background:#fff}
.form-group input:focus,.form-group select:focus,.form-group textarea:focus{border-color:#1B5E20;outline:none;box-shadow:0 0 0 3px rgba(27,94,32,.12)}
.paginacao{display:flex;gap:6px;align-items:center;margin-top:14px;justify-content:flex-end;flex-wrap:wrap}
.paginacao a,.paginacao span{padding:5px 12px;border-radius:6px;font-size:13px;border:1px solid #d0dccc;color:#444;text-decoration:none}
.paginacao a:hover{background:#eaf2ea;text-decoration:none}
.paginacao .ativo{background:#1B5E20;color:#fff;border-color:#1B5E20}
.alert{padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:13px}
.alert-ok{background:#e8f5e9;color:#1B5E20;border:1px solid #c8e6c9}
.alert-erro{background:#fdecea;color:#b71c1c;border:1px solid #f5c6c4}
.obs-input{width:100%;min-width:120px;padding:4px 8px;border:1px solid #d0dccc;border-radius:6px;font-size:12px;background:#fff}
.obs-input:focus{border-color:#1B5E20;outline:none}
.acao-cell{white-space:nowrap}
.empty{padding:40px;text-align:center;color:#999;font-size:13px}
@media print{
  .nav,.no-print,.btn{display:none!important}
  body{background:#fff}
  .page{padding:0}
  .card{box-shadow:none;border:1px solid #ddd}
}
"""

NAV = """
<nav class="nav">
  <a href="{{ url_for('dashboard') }}" class="nav-brand"><img src="{{ url_for('static', filename='LOGO.svg') }}" alt="Conciliador NF-e"></a>
  <a href="{{ url_for('dashboard') }}" {% if endpoint=='dashboard' %}class="ativo"{% endif %}>Dashboard</a>
  <a href="{{ url_for('lista_notas') }}" {% if endpoint=='lista_notas' %}class="ativo"{% endif %}>Notas</a>
  <a href="{{ url_for('lista_notas', status='nao_lancado') }}">Não lançadas</a>
  <a href="{{ url_for('importar') }}" {% if endpoint=='importar' %}class="ativo"{% endif %}>Importar</a>
  <div class="nav-sep"></div>
  <div class="nav-user">Conciliador NF-e</div>
</nav>
"""

PAGE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo }} — Conciliador NF-e</title>
<style>""" + CSS + """</style>
</head>
<body>
""" + NAV + """
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}
    <div class="page" style="padding-bottom:0">
      {% for cat, msg in msgs %}
        <div class="alert alert-{{ cat or 'ok' }}">{{ msg }}</div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
{{ corpo|safe }}
</body>
</html>"""

def render_pagina(titulo, corpo_html):
    return render_template_string(
        PAGE,
        titulo=titulo,
        corpo=corpo_html,
        endpoint=request.endpoint,
    )

# ── rotas ────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return redirect(url_for("dashboard"))

MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
            "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

def fmt_mes(ym):
    """'2026-04' → 'Abril/2026'."""
    if not ym or len(ym) < 7:
        return ym or ""
    try:
        y, m = ym.split("-")
        return f"{MESES_PT[int(m)]}/{y}"
    except (ValueError, IndexError):
        return ym

def meses_disponiveis():
    """Retorna lista de 'YYYY-MM' presentes nas notas, mais recentes primeiro."""
    rows = query("""
        SELECT DISTINCT substr(data_emissao,1,7) AS ym
        FROM nota_consolidada
        WHERE data_emissao IS NOT NULL AND length(data_emissao) >= 7
        ORDER BY ym DESC
    """)
    return [r["ym"] for r in rows]


@app.route("/dashboard")
def dashboard():
    mes = request.args.get("mes", "").strip()    # 'YYYY-MM' ou ''
    meses = meses_disponiveis()
    if mes and mes not in meses:
        mes = ""

    where_extra = ""
    args = []
    if mes:
        where_extra = " AND substr(data_emissao,1,7) = ?"
        args = [mes]

    totais = query(f"""
        SELECT
            SUM(CASE WHEN {STATUS_SQL}='nao_lancado' THEN 1 ELSE 0 END) AS nao_lancado,
            SUM(CASE WHEN {STATUS_SQL}='lancado'     THEN 1 ELSE 0 END) AS lancado,
            SUM(CASE WHEN {STATUS_SQL}='cartao'      THEN 1 ELSE 0 END) AS cartao,
            SUM(CASE WHEN {STATUS_SQL}='nf_servico'  THEN 1 ELSE 0 END) AS nf_servico,
            COUNT(*) AS total,
            COALESCE(SUM(CASE WHEN {STATUS_SQL}='nao_lancado' THEN valor END),0) AS val_nao_lancado,
            COALESCE(SUM(CASE WHEN {STATUS_SQL}='lancado'     THEN valor END),0) AS val_lancado,
            COALESCE(SUM(CASE WHEN {STATUS_SQL}='cartao'      THEN valor END),0) AS val_cartao,
            COALESCE(SUM(CASE WHEN {STATUS_SQL}='nf_servico'  THEN valor END),0) AS val_nf_servico
        FROM nota_consolidada
        WHERE 1=1{where_extra}
    """, args, one=True)

    ultima_imp = query("SELECT * FROM importacao ORDER BY id DESC LIMIT 1", one=True)

    nao_lancadas_recentes = query(f"""
        SELECT chave, numero, emitente, cnpj_emitente, valor, data_emissao
        FROM nota_consolidada
        WHERE {STATUS_SQL}='nao_lancado'{where_extra}
        ORDER BY data_emissao DESC, numero DESC
        LIMIT 15
    """, args)

    def stat(label, valor, sub, classe, status_filtro=None):
        if status_filtro:
            params = {"status": status_filtro}
            if mes:
                params["mes"] = mes
            href = url_for("lista_notas", **params)
        else:
            href = "#"
        return f"""
        <a class="stat {classe}" href="{href}">
          <div class="stat-label">{label}</div>
          <div class="stat-val">{valor}</div>
          <div class="stat-sub">{sub}</div>
        </a>"""

    stats_html = (
        stat("Não lançadas", totais["nao_lancado"] or 0, fmt_valor(totais["val_nao_lancado"]), "vermelho", "nao_lancado") +
        stat("Lançadas",      totais["lancado"]     or 0, fmt_valor(totais["val_lancado"]),     "verde",    "lancado") +
        stat("Cartão",        totais["cartao"]      or 0, fmt_valor(totais["val_cartao"]),      "laranja",  "cartao") +
        stat("NF de Serviço", totais["nf_servico"]  or 0, fmt_valor(totais["val_nf_servico"]),  "azul",     "nf_servico") +
        stat("Total no banco", totais["total"]      or 0, "no período" if mes else "todas as notas", "cinza")
    )

    rows = []
    for n in nao_lancadas_recentes:
        rows.append(f"""
        <tr>
          <td>{fmt_data(n['data_emissao'])}</td>
          <td class="mono">{n['numero'] or ''}</td>
          <td>{n['emitente'] or ''}<br><span class="mono" style="color:#888">{fmt_cnpj(n['cnpj_emitente'])}</span></td>
          <td class="num">{fmt_valor(n['valor'])}</td>
          <td><a class="btn btn-sm btn-laranja" href="{url_for('lista_notas', q=n['chave'])}">Detalhe</a></td>
        </tr>""")
    tabela_html = "".join(rows) or '<tr><td colspan="5" class="empty">Nenhuma nota não lançada nesse período. Tudo conferido!</td></tr>'

    info_imp = ""
    if ultima_imp:
        info_imp = (f"Última importação em <b>{ultima_imp['executado_em']}</b> — "
                    f"SEFAZ: {ultima_imp['notas_sefaz']}, Sistema: {ultima_imp['notas_sistema']}, "
                    f"total no banco: {ultima_imp['notas_total']}")
    else:
        info_imp = "Banco vazio. Vá em <a href='" + url_for('importar') + "'>Importar</a> para começar."

    # opções do filtro de mês
    opts = ['<option value="">(Todos os meses)</option>']
    for m in meses:
        sel = " selected" if m == mes else ""
        opts.append(f'<option value="{m}"{sel}>{fmt_mes(m)}</option>')
    mes_select = "".join(opts)

    # botão "Ver todas as não lançadas" preserva o mês
    params_ver = {"status": "nao_lancado"}
    if mes:
        params_ver["mes"] = mes
    url_ver_todas = url_for("lista_notas", **params_ver)

    periodo_titulo = f" — {fmt_mes(mes)}" if mes else ""

    corpo = f"""
    <div class="page">
      <div class="page-header">
        <div>
          <h1 class="page-title">Conferência de Notas Fiscais{periodo_titulo}</h1>
          <div class="page-sub">{info_imp}</div>
        </div>
        <div>
          <a class="btn btn-secondary" href="{url_for('importar')}">Importar planilhas</a>
        </div>
      </div>

      <form method="get" class="filtros" style="margin-bottom:16px">
        <div class="form-group" style="min-width:220px">
          <label>Período (mês de emissão)</label>
          <select name="mes" onchange="this.form.submit()">{mes_select}</select>
        </div>
        <button class="btn btn-primary" type="submit">Filtrar</button>
        {'<a class="btn btn-cinza" href="' + url_for('dashboard') + '">Limpar</a>' if mes else ''}
      </form>

      <div class="stats">{stats_html}</div>
      <div class="card">
        <div class="card-title">Notas não lançadas mais recentes{periodo_titulo}</div>
        <div class="tbl-wrap">
          <table>
            <tr><th>Emissão</th><th>Número</th><th>Emitente</th><th class="right">Valor</th><th></th></tr>
            {tabela_html}
          </table>
        </div>
        <div style="margin-top:12px;text-align:right">
          <a class="btn btn-primary" href="{url_ver_todas}">Ver todas as não lançadas{periodo_titulo}</a>
        </div>
      </div>
    </div>"""
    return render_pagina("Dashboard", corpo)


POR_PAGINA = 50

@app.route("/notas")
def lista_notas():
    status   = request.args.get("status", "").strip()
    busca    = request.args.get("q", "").strip()
    cnpj     = request.args.get("cnpj", "").strip()
    mes      = request.args.get("mes", "").strip()
    pag      = max(1, int(request.args.get("pag", "1") or "1"))

    meses = meses_disponiveis()
    if mes and mes not in meses:
        mes = ""

    where = ["1=1"]
    args  = []
    if status in STATUS_LABEL:
        where.append(f"{STATUS_SQL} = ?")
        args.append(status)
    if mes:
        where.append("substr(data_emissao,1,7) = ?")
        args.append(mes)
    if busca:
        where.append("(chave LIKE ? OR numero LIKE ? OR emitente LIKE ? OR observacao LIKE ?)")
        args += [f"%{busca}%", f"%{busca}%", f"%{busca}%", f"%{busca}%"]
    if cnpj:
        cnpj_dig = "".join(ch for ch in cnpj if ch.isdigit())
        where.append("cnpj_emitente LIKE ?")
        args.append(f"%{cnpj_dig}%")
    ws = " AND ".join(where)

    total = query(f"SELECT COUNT(*) AS n FROM nota_consolidada WHERE {ws}", args, one=True)["n"]
    total_paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pag = min(pag, total_paginas)

    soma_valor = query(f"SELECT COALESCE(SUM(valor),0) AS s FROM nota_consolidada WHERE {ws}", args, one=True)["s"]

    rows = query(f"""
        SELECT chave, numero, serie, cnpj_emitente, emitente, valor, data_emissao,
               em_sefaz, em_sistema, marcacao_cartao, observacao,
               {STATUS_SQL} AS status
        FROM nota_consolidada
        WHERE {ws}
        ORDER BY data_emissao DESC, numero DESC
        LIMIT ? OFFSET ?
    """, args + [POR_PAGINA, (pag - 1) * POR_PAGINA])

    # filtros (form)
    def opt(val, label, sel):
        s = ' selected' if val == sel else ''
        return f'<option value="{val}"{s}>{label}</option>'
    status_opts = (opt("", "(Todos)", status)
                 + opt("nao_lancado", "Não lançado", status)
                 + opt("lancado", "Lançado", status)
                 + opt("cartao", "Cartão", status)
                 + opt("nf_servico", "NF de Serviço", status))

    mes_opts = '<option value="">(Todos os meses)</option>' + "".join(
        f'<option value="{m}"{" selected" if m==mes else ""}>{fmt_mes(m)}</option>'
        for m in meses
    )

    # linhas
    linhas = []
    for n in rows:
        label, cls_badge = STATUS_LABEL[n["status"]]
        cartao_check = "checked" if n["marcacao_cartao"] else ""
        obs = (n["observacao"] or "").replace('"', '&quot;')
        flags = []
        if n["em_sefaz"]:   flags.append('<span class="badge badge-verde" title="Na planilha da SEFAZ">SEFAZ</span>')
        if n["em_sistema"]: flags.append('<span class="badge badge-verde" title="Lançada no sistema interno">Sistema</span>')
        flags_html = " ".join(flags) or '<span class="badge badge-cinza">—</span>'
        linhas.append(f"""
        <tr data-chave="{n['chave']}">
          <td>{fmt_data(n['data_emissao'])}</td>
          <td class="mono">{n['numero'] or ''}{('/'+n['serie']) if n['serie'] else ''}</td>
          <td>
            {n['emitente'] or ''}<br>
            <span class="mono" style="color:#888">{fmt_cnpj(n['cnpj_emitente'])}</span>
          </td>
          <td class="num">{fmt_valor(n['valor'])}</td>
          <td>{flags_html}</td>
          <td><span class="badge {cls_badge}">{label}</span></td>
          <td class="acao-cell">
            <label style="font-size:12px;cursor:pointer;display:inline-flex;align-items:center;gap:5px">
              <input type="checkbox" class="cartao-chk" {cartao_check}> Cartão
            </label>
          </td>
          <td><input class="obs-input" data-chave="{n['chave']}" value="{obs}" placeholder="observação"></td>
          <td class="chave" title="{n['chave']}">{n['chave'][:8]}…{n['chave'][-4:]}</td>
        </tr>""")
    linhas_html = "".join(linhas) or '<tr><td colspan="9" class="empty">Nenhuma nota com esses filtros.</td></tr>'

    # paginação
    def pag_link(p, txt=None, ativo=False):
        if ativo:
            return f'<span class="ativo">{txt or p}</span>'
        argsd = dict(request.args)
        argsd["pag"] = p
        return f'<a href="{url_for("lista_notas", **argsd)}">{txt or p}</a>'
    pags = []
    if pag > 1:
        pags.append(pag_link(pag - 1, "‹ anterior"))
    janela = range(max(1, pag - 3), min(total_paginas, pag + 3) + 1)
    for p in janela:
        pags.append(pag_link(p, ativo=(p == pag)))
    if pag < total_paginas:
        pags.append(pag_link(pag + 1, "próxima ›"))
    pag_html = "".join(pags)

    js = """
    <script>
    document.querySelectorAll('.cartao-chk').forEach(chk => {
      chk.addEventListener('change', async (ev) => {
        const tr = ev.target.closest('tr');
        const chave = tr.dataset.chave;
        const marcado = ev.target.checked ? 1 : 0;
        const r = await fetch('/notas/' + chave + '/cartao', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({cartao: marcado})
        });
        if (!r.ok) { alert('Falha ao salvar marcação.'); ev.target.checked = !ev.target.checked; return; }
        // recarrega pra atualizar o badge de status
        window.location.reload();
      });
    });
    document.querySelectorAll('.obs-input').forEach(inp => {
      let timer = null;
      inp.addEventListener('input', (ev) => {
        clearTimeout(timer);
        const chave = ev.target.dataset.chave;
        const val = ev.target.value;
        timer = setTimeout(async () => {
          const r = await fetch('/notas/' + chave + '/observacao', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({observacao: val})
          });
          if (r.ok) { ev.target.style.borderColor = '#2E7D32'; setTimeout(()=>{ev.target.style.borderColor='';}, 600); }
        }, 600);
      });
    });
    </script>"""

    titulo_status = STATUS_LABEL.get(status, ("Todas as notas", ""))[0] if status else "Todas as notas"
    titulo_mes = f" — {fmt_mes(mes)}" if mes else ""

    corpo = f"""
    <div class="page">
      <div class="page-header">
        <div>
          <h1 class="page-title">{titulo_status}{titulo_mes}</h1>
          <div class="page-sub">{total} nota(s) — total {fmt_valor(soma_valor)}</div>
        </div>
        <div>
          <a class="btn btn-secondary" href="{url_for('dashboard')}">← Dashboard</a>
        </div>
      </div>

      <form class="filtros" method="get">
        <div class="form-group" style="min-width:160px">
          <label>Status</label>
          <select name="status">{status_opts}</select>
        </div>
        <div class="form-group" style="min-width:180px">
          <label>Mês de emissão</label>
          <select name="mes">{mes_opts}</select>
        </div>
        <div class="form-group" style="flex:1;min-width:220px">
          <label>Busca (chave, número, emitente ou observação)</label>
          <input name="q" value="{busca}" placeholder="Ex: 4317, fornecedor ou pago via Pix">
        </div>
        <div class="form-group" style="min-width:160px">
          <label>CNPJ emitente</label>
          <input name="cnpj" value="{cnpj}" placeholder="Ex: 89.054.050">
        </div>
        <button class="btn btn-primary" type="submit">Filtrar</button>
        <a class="btn btn-cinza" href="{url_for('lista_notas')}">Limpar</a>
      </form>

      <div class="card" style="padding:0">
        <div class="tbl-wrap">
          <table>
            <tr>
              <th>Emissão</th>
              <th>Nº/Série</th>
              <th>Emitente</th>
              <th class="right">Valor</th>
              <th>Fontes</th>
              <th>Status</th>
              <th>Cartão?</th>
              <th>Observação</th>
              <th>Chave</th>
            </tr>
            {linhas_html}
          </table>
        </div>
      </div>
      <div class="paginacao">{pag_html}</div>
    </div>
    {js}"""
    return render_pagina(titulo_status, corpo)


@app.route("/notas/<chave>/cartao", methods=["POST"])
def marcar_cartao(chave):
    data = request.get_json(silent=True) or {}
    marcado = 1 if data.get("cartao") else 0
    db = get_db()
    cur = db.execute("UPDATE nota_consolidada SET marcacao_cartao=? WHERE chave=?", (marcado, chave))
    if cur.rowcount == 0:
        return jsonify(ok=False, erro="nota não encontrada"), 404
    db.commit()
    return jsonify(ok=True, cartao=bool(marcado))


@app.route("/notas/<chave>/observacao", methods=["POST"])
def salvar_observacao(chave):
    data = request.get_json(silent=True) or {}
    obs = (data.get("observacao") or "").strip()
    db = get_db()
    cur = db.execute("UPDATE nota_consolidada SET observacao=? WHERE chave=?",
                     (obs if obs else None, chave))
    if cur.rowcount == 0:
        return jsonify(ok=False, erro="nota não encontrada"), 404
    db.commit()
    return jsonify(ok=True)


@app.route("/importar", methods=["GET", "POST"])
def importar():
    if request.method == "POST":
        arq_sefaz = request.files.get("sefaz")
        arq_sis   = request.files.get("sistema")
        if not arq_sefaz or not arq_sefaz.filename:
            flash("Selecione o arquivo .xlsx da SEFAZ.", "erro")
            return redirect(url_for("importar"))
        if not arq_sis or not arq_sis.filename:
            flash("Selecione o arquivo .csv do sistema.", "erro")
            return redirect(url_for("importar"))

        # salva temporários
        tmp_dir = tempfile.mkdtemp(prefix="conciliador_")
        path_sefaz = os.path.join(tmp_dir, os.path.basename(arq_sefaz.filename))
        path_sis   = os.path.join(tmp_dir, os.path.basename(arq_sis.filename))
        arq_sefaz.save(path_sefaz)
        arq_sis.save(path_sis)

        # fecha conexão do request antes de o importador abrir a sua
        fechar_db()

        try:
            resumo = importador.executar_importacao(path_sefaz, path_sis, db_path=DB_PATH)
        except Exception as e:
            log.error(f"Erro na importação: {e}\n{traceback.format_exc()}")
            flash(f"Erro na importação: {e}", "erro")
            return redirect(url_for("importar"))

        flash(
            f"Importação ok — SEFAZ: {resumo['totais']['em_sefaz']} notas, "
            f"Sistema: {resumo['totais']['em_sistema']}, "
            f"total no banco: {resumo['totais']['total']}.",
            "ok"
        )
        return redirect(url_for("dashboard"))

    # GET: tela
    historico = query("SELECT * FROM importacao ORDER BY id DESC LIMIT 5")
    hist_rows = ""
    for h in historico:
        hist_rows += f"""
        <tr>
          <td>{h['executado_em']}</td>
          <td class="mono" style="font-size:11px">{os.path.basename(h['arquivo_sefaz'] or '')}</td>
          <td class="mono" style="font-size:11px">{os.path.basename(h['arquivo_sistema'] or '')}</td>
          <td class="num">{h['notas_sefaz']}</td>
          <td class="num">{h['notas_sistema']}</td>
          <td class="num">{h['notas_total']}</td>
        </tr>"""
    if not hist_rows:
        hist_rows = '<tr><td colspan="6" class="empty">Nenhuma importação registrada ainda.</td></tr>'

    corpo = f"""
    <div class="page">
      <div class="page-header">
        <h1 class="page-title">Importar planilhas</h1>
        <a class="btn btn-secondary" href="{url_for('dashboard')}">← Dashboard</a>
      </div>
      <div class="card">
        <div class="card-title">Subir as 2 planilhas</div>
        <p style="margin-bottom:16px;color:#555;font-size:13px">
          Selecione o <b>.xlsx</b> da SEFAZ (FSist) e o <b>.csv</b> do sistema interno (Notas de Entrada).
          As marcações manuais de cartão e observações são <b>preservadas</b> entre importações.
        </p>
        <form method="post" enctype="multipart/form-data">
          <div class="form-group" style="margin-bottom:14px">
            <label>Planilha SEFAZ (.xlsx)</label>
            <input type="file" name="sefaz" accept=".xlsx" required>
          </div>
          <div class="form-group" style="margin-bottom:14px">
            <label>Planilha do Sistema (.csv)</label>
            <input type="file" name="sistema" accept=".csv" required>
          </div>
          <button class="btn btn-primary" type="submit">Importar agora</button>
        </form>
      </div>
      <div class="card">
        <div class="card-title">Últimas importações</div>
        <div class="tbl-wrap">
          <table>
            <tr><th>Data/hora</th><th>Arquivo SEFAZ</th><th>Arquivo Sistema</th>
                <th class="right">SEFAZ</th><th class="right">Sistema</th><th class="right">Total</th></tr>
            {hist_rows}
          </table>
        </div>
      </div>
    </div>"""
    return render_pagina("Importar", corpo)


# ── main ─────────────────────────────────────────────────────────────────────

def _ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"! Banco {DB_PATH} não encontrado. Rode primeiro:  python init_db.py")
        sys.exit(1)
    ip = _ip_local()
    print(f"\nConciliador NF-e")
    print(f"  Local:        http://localhost:5001")
    print(f"  Outros PCs:   http://{ip}:5001")
    print(f"  Logs:         {LOG_PATH}\n")
    app.run(host="0.0.0.0", port=5001, debug=False)
