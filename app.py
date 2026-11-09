import os
import sqlite3
import hashlib
import hmac
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, g

BASE = Path(__file__).resolve().parent
DB = Path(os.getenv('ESTOQUE_DB', str(BASE / 'estoque.db')))
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-only-change-this-secret-before-deploy')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('COOKIE_SECURE') == '1'


def db():
    if 'db' not in g:
        DB.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


@app.teardown_appcontext
def close_db(exc):
    conn = g.pop('db', None)
    if conn:
        conn.close()


def init_db():
    db().executescript('''
    CREATE TABLE IF NOT EXISTS usuarios (
      id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
      login TEXT NOT NULL UNIQUE, salt TEXT NOT NULL, senha_hash TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS produtos (
      id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
      categoria TEXT NOT NULL, preco_centavos INTEGER NOT NULL CHECK(preco_centavos >= 0),
      quantidade INTEGER NOT NULL CHECK(quantidade >= 0),
      estoque_minimo INTEGER NOT NULL CHECK(estoque_minimo >= 0),
      criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS movimentacoes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
      tipo TEXT NOT NULL CHECK(tipo IN ('entrada','saida')),
      quantidade INTEGER NOT NULL CHECK(quantidade > 0),
      data_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX IF NOT EXISTS idx_mov_produto ON movimentacoes(produto_id);
    ''')
    db().commit()


def hash_password(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapped


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(24)
    return session['csrf']

app.jinja_env.globals['csrf_token'] = csrf_token

@app.before_request
def protect_post():
    if request.method == 'POST' and not hmac.compare_digest(request.form.get('csrf_token', ''), csrf_token()):
        return 'Solicitação inválida. Atualize a página e tente novamente.', 400


@app.template_filter('brl')
def brl(cents):
    value = f'{int(cents)/100:,.2f}'
    return 'R$ ' + value.replace(',', 'X').replace('.', ',').replace('X', '.')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('login', '').strip()
        password = request.form.get('senha', '')
        user = db().execute('SELECT * FROM usuarios WHERE login = ?', (username,)).fetchone()
        if user and hmac.compare_digest(hash_password(password, user['salt']), user['senha_hash']):
            session.clear()
            session['uid'] = user['id']
            session['nome'] = user['nome']
            flash('Bem-vindo ao Sistema de Estoque FGM!', 'success')
            return redirect(url_for('home'))
        flash('Usuário ou senha inválidos.', 'danger')
    return render_template('login.html')


@app.post('/sair')
@login_required
def sair():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def home():
    conn = db()
    totals = conn.execute('''SELECT COUNT(*) AS total,
      COALESCE(SUM(quantidade),0) AS unidades,
      COALESCE(SUM(CASE WHEN quantidade <= estoque_minimo THEN 1 ELSE 0 END),0) AS baixos
      FROM produtos''').fetchone()
    recentes = conn.execute('''SELECT m.*, p.nome FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id
      ORDER BY m.id DESC LIMIT 5''').fetchall()
    return render_template('home.html', totals=totals, recentes=recentes)


@app.route('/produtos', methods=['GET', 'POST'])
@login_required
def produtos():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        categoria = request.form.get('categoria', '').strip()
        preco = request.form.get('preco', '').strip().replace('.', '').replace(',', '.')
        quantidade = request.form.get('quantidade', '').strip()
        minimo = request.form.get('estoque_minimo', '').strip()
        try:
            from decimal import Decimal, InvalidOperation
            valor = Decimal(preco)
            if not nome or not categoria or len(nome) > 120 or len(categoria) > 60:
                raise ValueError()
            if valor < 0 or valor.as_tuple().exponent < -2:
                raise ValueError()
            centavos = int(valor * 100)
            if not quantidade.isdecimal() or not minimo.isdecimal():
                raise ValueError()
            qtd, min_qtd = int(quantidade), int(minimo)
            if max(qtd, min_qtd, centavos) > 1000000000:
                raise ValueError()
            db().execute('INSERT INTO produtos(nome,categoria,preco_centavos,quantidade,estoque_minimo) VALUES (?,?,?,?,?)',
                         (nome, categoria, centavos, qtd, min_qtd))
            db().commit()
            flash('Produto cadastrado com sucesso!', 'success')
            return redirect(url_for('consulta'))
        except (ValueError, ArithmeticError, InvalidOperation):
            flash('Confira os campos: nome e categoria obrigatórios, preço válido e quantidades inteiras não negativas.', 'danger')
    return render_template('produtos.html')


@app.route('/movimentacoes', methods=['GET', 'POST'])
@login_required
def movimentacoes():
    conn = db()
    if request.method == 'POST':
        produto_id = request.form.get('produto_id', '')
        tipo = request.form.get('tipo', '')
        quantidade = request.form.get('quantidade', '')
        if not produto_id.isdecimal() or tipo not in ('entrada', 'saida') or not quantidade.isdecimal() or int(quantidade) <= 0:
            flash('Selecione um produto, uma operação e uma quantidade inteira maior que zero.', 'danger')
        else:
            qtd = int(quantidade)
            produto = conn.execute('SELECT * FROM produtos WHERE id=?', (int(produto_id),)).fetchone()
            if not produto:
                flash('Produto não encontrado.', 'danger')
            elif tipo == 'saida' and qtd > produto['quantidade']:
                flash('Quantidade insuficiente em estoque.', 'danger')
            elif qtd > 1000000000 or (tipo == 'entrada' and produto['quantidade'] + qtd > 1000000000):
                flash('Quantidade acima do limite permitido.', 'danger')
            else:
                novo = produto['quantidade'] + qtd if tipo == 'entrada' else produto['quantidade'] - qtd
                with conn:
                    conn.execute('UPDATE produtos SET quantidade=? WHERE id=?', (novo, produto['id']))
                    conn.execute('INSERT INTO movimentacoes(produto_id,tipo,quantidade) VALUES(?,?,?)',
                                 (produto['id'], tipo, qtd))
                flash(f'Estoque atualizado com sucesso! {produto["nome"]}: {novo} unidades.', 'success')
                return redirect(url_for('consulta'))
    lista = conn.execute('SELECT * FROM produtos ORDER BY nome COLLATE NOCASE').fetchall()
    historico = conn.execute('''SELECT m.*,p.nome FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id
      ORDER BY m.id DESC LIMIT 15''').fetchall()
    return render_template('movimentacoes.html', produtos=lista, historico=historico,
                           selecionado=request.args.get('produto_id', ''))


@app.route('/consulta')
@login_required
def consulta():
    conn = db()
    busca = request.args.get('busca', '').strip()[:100]
    categoria = request.args.get('categoria', '').strip()[:60]
    somente_baixos = request.args.get('baixos') == '1'
    try:
        pagina = max(1, int(request.args.get('pagina', '1')))
    except ValueError:
        pagina = 1
    where, params = ['1=1'], []
    if busca:
        where.append('nome LIKE ?')
        params.append('%' + busca + '%')
    if categoria:
        where.append('categoria = ?')
        params.append(categoria)
    if somente_baixos:
        where.append('quantidade <= estoque_minimo')
    condition = ' AND '.join(where)
    total = conn.execute('SELECT COUNT(*) FROM produtos WHERE ' + condition, params).fetchone()[0]
    paginas = max(1, (total + 19) // 20)
    pagina = min(pagina, paginas)
    lista = conn.execute('SELECT * FROM produtos WHERE ' + condition +
                         ' ORDER BY nome COLLATE NOCASE LIMIT 20 OFFSET ?', params + [(pagina - 1) * 20]).fetchall()
    categorias = conn.execute('SELECT DISTINCT categoria FROM produtos ORDER BY categoria').fetchall()
    alertas = conn.execute('SELECT * FROM produtos WHERE quantidade <= estoque_minimo ORDER BY quantidade ASC LIMIT 5').fetchall()
    historico = conn.execute('''SELECT m.*,p.nome FROM movimentacoes m JOIN produtos p ON p.id=m.produto_id
      ORDER BY m.id DESC LIMIT 5''').fetchall()
    totals = conn.execute('''SELECT COUNT(*) AS total, COALESCE(SUM(quantidade),0) AS unidades,
      COALESCE(SUM(CASE WHEN quantidade <= estoque_minimo THEN 1 ELSE 0 END),0) AS baixos FROM produtos''').fetchone()
    hoje = conn.execute("SELECT COUNT(*) FROM movimentacoes WHERE date(data_hora)=date('now')").fetchone()[0]
    return render_template('consulta.html', produtos=lista, categorias=categorias, alertas=alertas,
                           historico=historico, totals=totals, hoje=hoje, busca=busca,
                           categoria=categoria, baixos=somente_baixos, pagina=pagina, paginas=paginas)


@app.cli.command('init-db')
def init_db_command():
    init_db()
    print('Banco de dados preparado.')


@app.cli.command('criar-admin')
def criar_admin_command():
    import getpass
    init_db()
    nome = input('Nome de exibição: ').strip()
    login = input('Login: ').strip()
    senha = getpass.getpass('Senha (mínimo 8 caracteres): ')
    if not nome or not login or len(senha) < 8:
        print('Dados inválidos. Informe nome, login e senha com pelo menos 8 caracteres.')
        return
    salt = secrets.token_hex(16)
    try:
        db().execute('INSERT INTO usuarios(nome,login,salt,senha_hash) VALUES (?,?,?,?)',
                     (nome, login, salt, hash_password(senha, salt)))
        db().commit()
        print('Usuário criado com sucesso.')
    except sqlite3.IntegrityError:
        print('Este login já está cadastrado.')


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=False)
