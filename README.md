# Supermercado FGM — Gestão de Estoque

Site com **Python 3.12, Flask, HTML, CSS, Bootstrap 5 e SQLite**, inspirado nas telas do projeto acadêmico.

## Requisitos
- Python 3.12 (ou Python 3.10+)
- Internet para carregar o Bootstrap pela CDN (o CSS principal funciona localmente)

## Executar no Windows (PowerShell do VS Code)
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
flask --app app init-db
flask --app app criar-admin
flask --app app run
Crie um login e senha para conseguir acessar!
```
Acesse http://127.0.0.1:5000 e entre com o usuário e a senha cadastrados.

Se a ativação do PowerShell for bloqueada, execute os comandos sem ativar:
```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m flask --app app init-db
.\venv\Scripts\python.exe -m flask --app app criar-admin
.\venv\Scripts\python.exe -m flask --app app run
```

## Teste rápido
1. Faça login.
2. Abra **Cadastrar Produto** e cadastre Arroz 5 kg, categoria Alimentos, preço 25,00, quantidade 30 e mínimo 10.
3. Abra **Movimentações**, selecione Arroz 5 kg, operação **Saída** e quantidade **22**.
4. A tela **Consultar Estoque** mostrará **8 unidades** e **⚠ Estoque baixo**.

## Funcionalidades
- Login com senhas derivadas por scrypt e sessões Flask.
- Menu inicial com quatro ações.
- Cadastro de produtos, entradas e saídas, validação de saldo.
- Consulta, pesquisa por nome, filtro de categoria e paginação de 20 itens.
- Alertas textuais e histórico recente de movimentações.
- Layout responsivo, rótulos claros, foco de teclado e mensagens de erro.
- Persistência local no arquivo `estoque.db` (não incluso no ZIP).

## Estrutura
- `app.py`: rotas, validações, autenticação e SQLite.
- `templates/`: HTML com Jinja2.
- `static/style.css`: estilo visual das imagens.
- `requirements.txt`: Flask.

## Atenção
Este é um MVP acadêmico para uso local. Antes de publicar na internet, configure `SECRET_KEY` por variável de ambiente, HTTPS, cookies seguros, limitação de tentativas de login e servidor de produção. Faça cópias de segurança de `estoque.db`.
