# ==============================================================================
# IMPORTS DAS BIBLIOTECAS
# ==============================================================================
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
    JWTManager
)
from datetime import datetime
from datetime import timedelta
from sqlalchemy import case, or_
from sqlalchemy.orm import joinedload
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from sqlalchemy.sql import func
import csv
import io
from sqlalchemy.orm import joinedload
import barcode
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.graphics.barcode import code128
import os
import json
# ==============================================================================
# CONFIGURAÇÃO INICIAL
# ==============================================================================

# Cria a aplicação Flask
app = Flask(__name__)

# --- CONFIGURAÇÃO DO JWT (JSON Web Token) ---
# Em produção, esta chave deve ser guardada de forma segura (ex: variável de ambiente)
app.config["JWT_SECRET_KEY"] = "minha-chave-super-secreta-para-o-projeto-de-estoque"
jwt = JWTManager(app)

# --- CONFIGURAÇÃO DO BANCO DE DADOS ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:senha123@localhost/estoque_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cria a instância do SQLAlchemy
db = SQLAlchemy(app)


# ==============================================================================
# TABELAS DE ASSOCIAÇÃO (Muitos-para-Muitos)
# ==============================================================================

produto_fornecedor = db.Table('produto_fornecedor',
    db.Column('FK_PRODUTO_Id_produto', db.Integer, db.ForeignKey('produto.Id_produto'), primary_key=True),
    db.Column('FK_FORNECEDOR_id_fornecedor', db.Integer, db.ForeignKey('fornecedor.id_fornecedor'), primary_key=True)
)

produto_natureza = db.Table('produto_natureza',
    db.Column('fk_PRODUTO_Id_produto', db.Integer, db.ForeignKey('produto.Id_produto'), primary_key=True),
    db.Column('fk_NATUREZA_id_natureza', db.Integer, db.ForeignKey('natureza.id_natureza'), primary_key=True)
)


# ==============================================================================
# MODELOS DO BANCO DE DADOS (ENTITIES)
# ==============================================================================

class Produto(db.Model):
    __tablename__ = 'produto'
    id_produto = db.Column('Id_produto', db.Integer, primary_key=True)
    nome = db.Column('Nome', db.String(100), nullable=False)
    codigo = db.Column('Codigo', db.String(20), unique=True, nullable=False)
    descricao = db.Column('Descricao', db.String(200))
    # --- ALTERAÇÃO AQUI ---
    # Permite que o preço seja nulo e define um padrão de 0.00
    preco = db.Column('Preco', db.Numeric(10, 2), nullable=True, default=0.00)
    codigoB = db.Column('CodigoB', db.String(20))
    codigoC = db.Column('CodigoC', db.String(20))
    
    fornecedores = db.relationship('Fornecedor', secondary=produto_fornecedor, back_populates='produtos')
    naturezas = db.relationship('Natureza', secondary=produto_natureza, back_populates='produtos')

class Fornecedor(db.Model):
    __tablename__ = 'fornecedor'
    id_fornecedor = db.Column(db.Integer, primary_key=True)
    nome = db.Column('Nome', db.String(50), unique=True, nullable=False)
    produtos = db.relationship('Produto', secondary=produto_fornecedor, back_populates='fornecedores')

class Natureza(db.Model):
    __tablename__ = 'natureza'
    id_natureza = db.Column(db.Integer, primary_key=True)
    nome = db.Column('nome', db.String(100), unique=True, nullable=False)
    produtos = db.relationship('Produto', secondary=produto_natureza, back_populates='naturezas')

class MovimentacaoEstoque(db.Model):
    __tablename__ = 'mov_estoque'
    id_movimentacao = db.Column(db.Integer, primary_key=True)
    id_produto = db.Column(db.Integer, db.ForeignKey('produto.Id_produto'), nullable=False)
    id_usuario = db.Column(db.Integer, db.ForeignKey('usuario.id_usuario'), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False, default=datetime.now)
    quantidade = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.Enum("Entrada", "Saida"), nullable=False)
    motivo_saida = db.Column(db.String(200))
    
    produto = db.relationship('Produto')
    usuario = db.relationship('Usuario')

class Usuario(db.Model):
    __tablename__ = 'usuario'
    id_usuario = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(100), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    permissao = db.Column(db.String(100), nullable=False)
    ativo = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.senha_hash, senha)


# ==============================================================================
# FUNÇÕES AUXILIARES (HELPERS)
# ==============================================================================

def calcular_saldo_produto(id_produto):
    """Calcula o saldo de estoque de um produto somando as entradas e subtraindo as saídas."""
    saldo = db.session.query(
        db.func.sum(
            case(
                (MovimentacaoEstoque.tipo == 'Entrada', MovimentacaoEstoque.quantidade),
                (MovimentacaoEstoque.tipo == 'Saida', -MovimentacaoEstoque.quantidade)
            )
        )
    ).filter(MovimentacaoEstoque.id_produto == id_produto).scalar() or 0
    return saldo


# ==============================================================================
# ROTAS DA API (ENDPOINTS)
# ==============================================================================

# --- ROTAS DE PRODUTOS ---

@app.route('/api/produtos', methods=['GET'])
@jwt_required()
def get_todos_produtos():
    """Retorna uma lista de produtos de forma otimizada, fazendo queries simples e juntando os dados em Python."""
    try:
        termo_busca = request.args.get('search')
        
        # --- CORREÇÃO DE PERFORMANCE FINAL ---
        # 1. Busca principal de produtos (muito rápido)
        query = Produto.query
        if termo_busca:
            query = query.filter(
                or_(
                    Produto.nome.ilike(f"%{termo_busca}%"),
                    Produto.codigo.ilike(f"%{termo_busca}%"),
                    Produto.codigoB.ilike(f"%{termo_busca}%"),
                    Produto.codigoC.ilike(f"%{termo_busca}%")
                )
            )
        produtos_db = query.all()
        
        if not produtos_db:
            return jsonify([]), 200

        product_ids = [p.id_produto for p in produtos_db]

        # 2. Busca de todos os dados de apoio em queries simples e rápidas
        fornecedores_map = {f.id_fornecedor: f.nome for f in Fornecedor.query.all()}
        naturezas_map = {n.id_natureza: n.nome for n in Natureza.query.all()}
        
        prod_forn_assoc = db.session.query(produto_fornecedor).filter(produto_fornecedor.c.FK_PRODUTO_Id_produto.in_(product_ids)).all()
        prod_nat_assoc = db.session.query(produto_natureza).filter(produto_natureza.c.fk_PRODUTO_Id_produto.in_(product_ids)).all()

        # 3. Organiza as associações em dicionários para acesso instantâneo
        produto_fornecedores = {}
        for p_id, f_id in prod_forn_assoc:
            if p_id not in produto_fornecedores:
                produto_fornecedores[p_id] = []
            produto_fornecedores[p_id].append(fornecedores_map.get(f_id, ''))

        produto_naturezas = {}
        for p_id, n_id in prod_nat_assoc:
            if p_id not in produto_naturezas:
                produto_naturezas[p_id] = []
            produto_naturezas[p_id].append(naturezas_map.get(n_id, ''))

        # 4. Monta o JSON final, juntando os dados em Python (ultra-rápido)
        produtos_json = []
        for produto in produtos_db:
            fornecedores_list = produto_fornecedores.get(produto.id_produto, [])
            naturezas_list = produto_naturezas.get(produto.id_produto, [])
            
            produtos_json.append({
                'id': produto.id_produto,
                'nome': produto.nome,
                'codigo': produto.codigo.strip() if produto.codigo else '',
                'descricao': produto.descricao,
                'preco': str(produto.preco),
                'codigoB': produto.codigoB,
                'codigoC': produto.codigoC,
                'fornecedores': ", ".join(sorted(fornecedores_list)),
                'naturezas': ", ".join(sorted(naturezas_list))
            })
            
        return jsonify(produtos_json), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500



@app.route('/api/produtos', methods=['POST'])
@jwt_required()
def add_novo_produto():
    """Cria um novo produto no sistema."""
    try:
        dados = request.get_json()
        
        # --- ALTERAÇÃO AQUI: 'preco' foi removido dos campos obrigatórios ---
        required_fields = ['nome', 'codigo']
        if not all(field in dados and dados[field] for field in required_fields):
            return jsonify({'erro': 'Campos obrigatórios (nome, codigo) não podem estar vazios.'}), 400

        novo_produto = Produto(
            nome=dados['nome'],
            codigo=dados['codigo'],
            descricao=dados.get('descricao'),
            # Usa o preço fornecido, ou 0 se não for enviado
            preco=dados.get('preco', '0.00').replace(',', '.'), 
            codigoB=dados.get('codigoB'),
            codigoC=dados.get('codigoC')
        )
        db.session.add(novo_produto)
        db.session.commit()
        
        return jsonify({
            'mensagem': 'Produto adicionado com sucesso!',
            'id_produto_criado': novo_produto.id_produto
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500



@app.route('/api/produtos/importar', methods=['POST'])
@jwt_required()
def importar_produtos_csv():
    """
    Processa um ficheiro CSV para cadastrar produtos em massa, lidando com
    diferentes codificações de ficheiro (UTF-8 e Latin-1/cp1252).
    """
    if 'file' not in request.files:
        return jsonify({'erro': 'Nenhum ficheiro enviado.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'erro': 'Nome de ficheiro vazio.'}), 400

    sucesso_count = 0
    erros = []
    
    try:
        # --- LÓGICA DE DECODIFICAÇÃO ROBUSTA ---
        file_bytes = file.stream.read()
        try:
            # 1. Tenta descodificar como UTF-8 (o padrão)
            stream_content = file_bytes.decode("UTF-8")
        except UnicodeDecodeError:
            # 2. Se o UTF-8 falhar, tenta como Latin-1 (comum em CSVs do Excel no Windows)
            print("Descodificação UTF-8 falhou. A tentar Latin-1 como alternativa.")
            stream_content = file_bytes.decode("latin-1")
        
        stream = io.StringIO(stream_content, newline=None)
        # --- FIM DA LÓGICA DE DECODIFICAÇÃO ---

        header = stream.readline()
        stream.seek(0)
        delimiter = ';' if ';' in header else ','
        csv_reader = csv.DictReader(stream, delimiter=delimiter)

        id_usuario_logado = get_jwt_identity()

        for linha_num, linha in enumerate(csv_reader, start=2):
            try:
                codigo = linha.get('codigo', '').strip()
                nome = linha.get('nome', '').strip()
                preco_str = linha.get('preco', '0').strip()

                if not codigo or not nome:
                    erros.append(f"Linha {linha_num}: Campos obrigatórios (codigo, nome) em falta.")
                    continue

                produto_existente = Produto.query.filter_by(codigo=codigo).first()
                if produto_existente:
                    erros.append(f"Linha {linha_num}: Código '{codigo}' já existe no sistema.")
                    continue

                novo_produto = Produto(
                    codigo=codigo,
                    nome=nome,
                    preco=preco_str.replace(',', '.') if preco_str else '0.00',
                    descricao=linha.get('descricao', '').strip()
                )

                fornecedores_nomes = [fn.strip() for fn in linha.get('fornecedores_nomes', '').split(',') if fn.strip()]
                if fornecedores_nomes:
                    fornecedores_db = Fornecedor.query.filter(Fornecedor.nome.in_(fornecedores_nomes)).all()
                    novo_produto.fornecedores.extend(fornecedores_db)

                naturezas_nomes = [nn.strip() for nn in linha.get('naturezas_nomes', '').split(',') if nn.strip()]
                if naturezas_nomes:
                    naturezas_db = Natureza.query.filter(Natureza.nome.in_(naturezas_nomes)).all()
                    novo_produto.naturezas.extend(naturezas_db)

                db.session.add(novo_produto)
                db.session.flush()

                quantidade_inicial_str = linha.get('quantidade', '0').strip()
                if quantidade_inicial_str and int(quantidade_inicial_str) > 0:
                    movimentacao_inicial = MovimentacaoEstoque(
                        id_produto=novo_produto.id_produto,
                        id_usuario=id_usuario_logado,
                        quantidade=int(quantidade_inicial_str),
                        tipo='Entrada',
                        motivo_saida='Balanço Inicial via Importação'
                    )
                    db.session.add(movimentacao_inicial)
                
                sucesso_count += 1

            except Exception as e_interno:
                erros.append(f"Linha {linha_num}: Erro ao processar - {e_interno}. Verifique os nomes das colunas.")
                continue

        db.session.commit()
        
        return jsonify({
            'mensagem': 'Importação concluída!',
            'produtos_importados': sucesso_count,
            'erros': erros
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': f'Ocorreu um erro geral ao processar o ficheiro: {str(e)}'}), 500




@app.route('/api/formularios/produto_data', methods=['GET'])
@jwt_required()
def get_form_produto_data():
    """Retorna todos os dados necessários para o formulário de produto de uma só vez, de forma otimizada."""
    try:
        produto_id = request.args.get('produto_id', type=int)
        
        # --- OTIMIZAÇÃO 1: Usar 'with_entities' para buscar apenas os dados necessários ---
        # Em vez de carregar os objetos SQLAlchemy completos, buscamos apenas os IDs e nomes.
        # Isto é muito mais rápido e leve.
        fornecedores_data = db.session.query(Fornecedor.id_fornecedor, Fornecedor.nome).order_by(Fornecedor.nome).all()
        naturezas_data = db.session.query(Natureza.id_natureza, Natureza.nome).order_by(Natureza.nome).all()
        
        dados_produto = None
        if produto_id:
            # A correção de performance com joinedload continua a ser a melhor abordagem aqui.
            produto = Produto.query.options(
                joinedload(Produto.fornecedores),
                joinedload(Produto.naturezas)
            ).get(produto_id)
            
            if produto:
                dados_produto = {
                    'id': produto.id_produto,
                    'nome': produto.nome,
                    'codigo': produto.codigo.strip() if produto.codigo else '',
                    'descricao': produto.descricao,
                    'preco': str(produto.preco),
                    'codigoB': produto.codigoB,
                    'codigoC': produto.codigoC,
                    'fornecedores': [{'id': f.id_fornecedor} for f in produto.fornecedores],
                    'naturezas': [{'id': n.id_natureza} for n in produto.naturezas]
                }

        # --- OTIMIZAÇÃO 2: Construir os dicionários a partir dos dados mais leves ---
        response_data = {
            'fornecedores': [{'id': id, 'nome': nome} for id, nome in fornecedores_data],
            'naturezas': [{'id': id, 'nome': nome} for id, nome in naturezas_data],
            'produto': dados_produto
        }
        
        return jsonify(response_data), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/produtos/<int:id_produto>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def produto_por_id_endpoint(id_produto):
    """Lida com operações para um produto específico (ler, editar, apagar)."""
    try:
        produto = Produto.query.get_or_404(id_produto)

        if request.method == 'GET':
            # ... (a lógica do GET continua igual)
            produto_json = {
                'id': produto.id_produto, 'nome': produto.nome,
                'codigo': produto.codigo.strip() if produto.codigo else '',
                'descricao': produto.descricao, 'preco': str(produto.preco),
                'codigoB': produto.codigoB, 'codigoC': produto.codigoC,
                'fornecedores': [{'id': f.id_fornecedor, 'nome': f.nome} for f in produto.fornecedores],
                'naturezas': [{'id': n.id_natureza, 'nome': n.nome} for n in produto.naturezas]
            }
            return jsonify(produto_json), 200
        
        elif request.method == 'PUT':
            dados = request.get_json()
            
            produto.nome = dados['nome']
            produto.codigo = dados['codigo']
            produto.descricao = dados.get('descricao')
            produto.preco = dados['preco']
            produto.codigoB = dados.get('codigoB')
            produto.codigoC = dados.get('codigoC')

            if 'fornecedores_ids' in dados:
                produto.fornecedores.clear()
                ids_fornecedores = dados['fornecedores_ids']
                if ids_fornecedores:
                    novos_fornecedores = Fornecedor.query.filter(Fornecedor.id_fornecedor.in_(ids_fornecedores)).all()
                    produto.fornecedores = novos_fornecedores

            if 'naturezas_ids' in dados:
                produto.naturezas.clear()
                ids_naturezas = dados['naturezas_ids']
                if ids_naturezas:
                    novas_naturezas = Natureza.query.filter(Natureza.id_natureza.in_(ids_naturezas)).all()
                    produto.naturezas = novas_naturezas

            db.session.commit()

            # --- A MUDANÇA CRUCIAL ESTÁ AQUI ---
            # Após salvar, buscamos os dados atualizados e os devolvemos para o front-end.
            updated_product = Produto.query.options(
                joinedload(Produto.fornecedores),
                joinedload(Produto.naturezas)
            ).get(id_produto)

            fornecedores_str = ", ".join(sorted([f.nome for f in updated_product.fornecedores]))
            naturezas_str = ", ".join(sorted([n.nome for n in updated_product.naturezas]))

            response_data = {
                'id': updated_product.id_produto,
                'nome': updated_product.nome,
                'codigo': updated_product.codigo.strip() if updated_product.codigo else '',
                'descricao': updated_product.descricao,
                'preco': str(updated_product.preco),
                'codigoB': updated_product.codigoB,
                'codigoC': updated_product.codigoC,
                'fornecedores': fornecedores_str,
                'naturezas': naturezas_str
            }
            return jsonify(response_data), 200 # Devolve os dados atualizados
        
        elif request.method == 'DELETE':
            # ... (a lógica do DELETE continua igual)
            movimentacao_existente = MovimentacaoEstoque.query.filter_by(id_produto=id_produto).first()
            if movimentacao_existente:
                return jsonify({'erro': 'Este produto não pode ser excluído, pois possui um histórico de movimentações no estoque.'}), 400

            db.session.delete(produto)
            db.session.commit()
            return jsonify({'mensagem': 'Produto excluído com sucesso!'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500
    
    
# --- ROTA PARA BUSCAR UM PRODUTO PELO CÓDIGO ---
@app.route('/api/produtos/codigo/<string:codigo>', methods=['GET'])
@jwt_required()
def get_produto_por_codigo(codigo):
    """Busca um produto específico pelo seu campo 'Codigo'."""
    try:
        # O .strip() é importante caso o campo no banco seja CHAR, para remover espaços
        produto = Produto.query.filter_by(codigo=codigo.strip()).first()
        
        if produto:
            # Se encontrou o produto, retorna os seus dados
            produto_json = {
                'id': produto.id_produto,
                'nome': produto.nome,
                'codigo': produto.codigo.strip(),
                'descricao': produto.descricao,
                'preco': str(produto.preco)
            }
            return jsonify(produto_json), 200
        else:
            # Se não encontrou, retorna um erro 404 (Not Found)
            return jsonify({'erro': 'Produto com este código não encontrado.'}), 404
            
    except Exception as e:
        return jsonify({'erro': str(e)}), 500
    
    
 
 
@app.route('/api/produtos/<int:id_produto>/estoque', methods=['GET'])
@jwt_required()
def get_saldo_estoque_produto(id_produto):
    """Calcula e retorna o saldo atual de um produto específico."""
    try:
        # Garante que o produto existe antes de calcular
        Produto.query.get_or_404(id_produto)
        
        saldo_calculado = calcular_saldo_produto(id_produto)
        return jsonify({'id_produto': id_produto, 'saldo_atual': saldo_calculado}), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500 
 
 
    
# Dentro do app.py

@app.route('/api/produtos/<int:id_produto>/fornecedores', methods=['POST'])
@jwt_required()
def adicionar_fornecedor_ao_produto(id_produto):
    """Associa um fornecedor existente a um produto existente."""
    try:
        # Pega no ID do fornecedor enviado no corpo do pedido
        dados = request.get_json()
        if 'id_fornecedor' not in dados:
            return jsonify({'erro': 'O ID do fornecedor é obrigatório.'}), 400

        id_fornecedor = dados['id_fornecedor']

        # Encontra o produto e o fornecedor na base de dados
        produto = Produto.query.get_or_404(id_produto)
        fornecedor = Fornecedor.query.get_or_404(id_fornecedor)

        # A "mágica" do SQLAlchemy: basta adicionar o objeto à lista.
        # Ele irá encarregar-se de criar a linha na tabela de junção.
        if fornecedor not in produto.fornecedores:
            produto.fornecedores.append(fornecedor)
            db.session.commit()
            return jsonify({'mensagem': 'Fornecedor associado ao produto com sucesso!'}), 200
        else:
            return jsonify({'mensagem': 'Fornecedor já está associado a este produto.'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500



# Dentro do app.py

@app.route('/api/produtos/<int:id_produto>/naturezas', methods=['POST'])
@jwt_required()
def adicionar_natureza_ao_produto(id_produto):
    """Associa uma natureza existente a um produto existente."""
    try:
        dados = request.get_json()
        if 'id_natureza' not in dados:
            return jsonify({'erro': 'O ID da natureza é obrigatório.'}), 400

        id_natureza = dados['id_natureza']

        produto = Produto.query.get_or_404(id_produto)
        natureza = Natureza.query.get_or_404(id_natureza)

        if natureza not in produto.naturezas:
            produto.naturezas.append(natureza)
            db.session.commit()
            return jsonify({'mensagem': 'Natureza associada ao produto com sucesso!'}), 200
        else:
            return jsonify({'mensagem': 'Natureza já está associada a este produto.'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500
    
    
    
    
# Dentro do app.py

@app.route('/api/produtos/<int:id_produto>/fornecedores/<int:id_fornecedor>', methods=['DELETE'])
@jwt_required()
def remover_fornecedor_do_produto(id_produto, id_fornecedor):
    """Remove a associação entre um fornecedor e um produto."""
    try:
        produto = Produto.query.get_or_404(id_produto)
        fornecedor = Fornecedor.query.get_or_404(id_fornecedor)

        if fornecedor in produto.fornecedores:
            produto.fornecedores.remove(fornecedor)
            db.session.commit()
            return jsonify({'mensagem': 'Associação com fornecedor removida com sucesso!'}), 200
        else:
            return jsonify({'erro': 'Fornecedor não está associado a este produto.'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/produtos/<int:id_produto>/naturezas/<int:id_natureza>', methods=['DELETE'])
@jwt_required()
def remover_natureza_do_produto(id_produto, id_natureza):
    """Remove a associação entre uma natureza e um produto."""
    try:
        produto = Produto.query.get_or_404(id_produto)
        natureza = Natureza.query.get_or_404(id_natureza)

        if natureza in produto.naturezas:
            produto.naturezas.remove(natureza)
            db.session.commit()
            return jsonify({'mensagem': 'Associação com natureza removida com sucesso!'}), 200
        else:
            return jsonify({'erro': 'Natureza não está associada a este produto.'}), 404

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500
# ... (resto do ficheiro)
# --- ROTAS DE ESTOQUE ---


@app.route('/api/estoque/entrada', methods=['POST'])
@jwt_required()
def registrar_entrada():
    """Regista uma nova entrada de estoque e retorna o novo saldo de forma fiável."""
    try:
        dados = request.get_json()
        if 'id_produto' not in dados or 'quantidade' not in dados:
            return jsonify({'erro': 'Campos obrigatórios em falta: id_produto, quantidade'}), 400

        id_produto = dados['id_produto']
        quantidade_entrada = dados['quantidade']
        
        # 1. Busca o saldo atual ANTES da operação
        saldo_atual = calcular_saldo_produto(id_produto)

        id_usuario_logado = get_jwt_identity()
        nova_entrada = MovimentacaoEstoque(
            id_produto=id_produto,
            quantidade=quantidade_entrada,
            id_usuario=id_usuario_logado,
            tipo='Entrada'
        )
        db.session.add(nova_entrada)
        db.session.commit()
        
        # 2. Calcula o novo saldo em Python para garantir a precisão
        novo_saldo = saldo_atual + quantidade_entrada
        return jsonify({
            'mensagem': 'Entrada de estoque registada com sucesso!',
            'novo_saldo': novo_saldo
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500



@app.route('/api/estoque/saida', methods=['POST'])
@jwt_required()
def registrar_saida():
    """Regista uma nova saída de estoque e retorna o novo saldo de forma fiável."""
    try:
        dados = request.get_json()
        required_fields = ['id_produto', 'quantidade', 'motivo_saida']
        if not all(field in dados and dados[field] for field in required_fields):
            return jsonify({'erro': 'Campos obrigatórios em falta: id_produto, quantidade, motivo_saida'}), 400

        id_produto = dados['id_produto']
        quantidade_saida = dados['quantidade']
        
        # 1. Busca o saldo atual ANTES da operação
        saldo_atual = calcular_saldo_produto(id_produto)
        if saldo_atual < quantidade_saida:
            return jsonify({'erro': f'Estoque insuficiente. Saldo atual: {saldo_atual}'}), 400

        id_usuario_logado = get_jwt_identity()
        nova_saida = MovimentacaoEstoque(
            id_produto=id_produto,
            quantidade=quantidade_saida,
            id_usuario=id_usuario_logado,
            tipo='Saida',
            motivo_saida=dados.get('motivo_saida')
        )
        db.session.add(nova_saida)
        db.session.commit()
        
        # 2. Calcula o novo saldo em Python para garantir a precisão
        novo_saldo = saldo_atual - quantidade_saida
        return jsonify({
            'mensagem': 'Saída de estoque registada com sucesso!',
            'novo_saldo': novo_saldo
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


@app.route('/api/estoque/saldos', methods=['GET'])
@jwt_required()
def get_saldos_estoque():
    """
    Calcula e retorna o saldo de estoque para os produtos,
    permitindo a busca por nome e códigos.
    """
    try:
        termo_busca = request.args.get('search')
        
        # Começa a query base de produtos
        query = Produto.query

        # Aplica o filtro de busca se um termo for fornecido
        if termo_busca:
            query = query.filter(
                or_(
                    Produto.nome.ilike(f"%{termo_busca}%"),
                    Produto.codigo.ilike(f"%{termo_busca}%"),
                    Produto.codigoB.ilike(f"%{termo_busca}%"),
                    Produto.codigoC.ilike(f"%{termo_busca}%")
                )
            )

        produtos_filtrados = query.all()
        
        saldos_json = []
        for produto in produtos_filtrados:
            saldo_atual = calcular_saldo_produto(produto.id_produto)
            saldos_json.append({
                'id_produto': produto.id_produto,
                'codigo': produto.codigo.strip() if produto.codigo else '',
                'nome': produto.nome if produto.nome else 'Produto sem nome',
                'saldo_atual': saldo_atual,
                # --- NOVOS CAMPOS ADICIONADOS ---
                'preco': str(produto.preco),
                'codigoB': produto.codigoB.strip() if produto.codigoB else '',
                'codigoC': produto.codigoC.strip() if produto.codigoC else ''
            })
            
        return jsonify(saldos_json), 200
        
    except Exception as e:
        print(f"!!! ERRO em /api/estoque/saldos: {e}")
        return jsonify({'erro': 'Ocorreu um erro interno no servidor ao calcular os saldos.'}), 500

@app.route('/api/movimentacoes', methods=['GET'])
@jwt_required()
def get_todas_movimentacoes():
    """
    Retorna uma lista de todas as movimentações de estoque (entradas e saídas),
    incluindo dados do produto e do usuário associados.
    Suporta filtragem por tipo de movimentação.
    """
    try:
        # Pega o parâmetro de filtro da URL, ex: /api/movimentacoes?tipo=Entrada
        filtro_tipo = request.args.get('tipo')

        # Começa a consulta base, usando joinedload para otimizar a busca dos
        # dados relacionados de Produto e Usuario em uma única viagem ao banco.
        query = MovimentacaoEstoque.query.options(
            joinedload(MovimentacaoEstoque.produto),
            joinedload(MovimentacaoEstoque.usuario)
        ).order_by(MovimentacaoEstoque.data_hora.desc()) # Ordena pelas mais recentes

        # Aplica o filtro se ele foi fornecido na URL
        if filtro_tipo and filtro_tipo in ["Entrada", "Saida"]:
            query = query.filter(MovimentacaoEstoque.tipo == filtro_tipo)

        movimentacoes = query.all()

        resultado_json = []
        for mov in movimentacoes:
            resultado_json.append({
                'id': mov.id_movimentacao,
                'data_hora': mov.data_hora.strftime('%d/%m/%Y %H:%M:%S'),
                'tipo': mov.tipo,
                'quantidade': mov.quantidade,
                'motivo_saida': mov.motivo_saida,
                # Adiciona os dados relacionados para facilitar a exibição no front-end
                'produto_codigo': mov.produto.codigo.strip() if mov.produto else 'N/A',
                'produto_nome': mov.produto.nome if mov.produto else 'Produto Excluído',
                'usuario_nome': mov.usuario.nome if mov.usuario else 'Usuário Excluído'
            })
        
        return jsonify(resultado_json), 200

    except Exception as e:
        return jsonify({'erro': str(e)}), 500

# --- ROTAS DE LOGIN E USUÁRIOS ---


@app.route('/api/login', methods=['POST'])
def login_endpoint():
    """Autentica um utilizador e retorna um token de acesso com duração prolongada."""
    try:
        dados = request.get_json()
        if not dados or 'login' not in dados or 'senha' not in dados:
            return jsonify({'erro': 'Campos de login e senha são obrigatórios'}), 400

        login = dados.get('login')
        senha = dados.get('senha')

        usuario = Usuario.query.filter_by(login=login, ativo=True).first()

        if usuario and usuario.check_password(senha):
            # --- A CORREÇÃO ESTÁ AQUI ---
            # Criamos um token que agora é válido por 8 horas.
            access_token = create_access_token(
                identity=str(usuario.id_usuario),
                additional_claims={'permissao': usuario.permissao},
                expires_delta=timedelta(hours=8) # Define a duração do token
            )
            return jsonify(access_token=access_token), 200
        else:
            return jsonify({"erro": "Credenciais inválidas"}), 401
            
    except Exception as e:
        return jsonify({'erro': str(e)}), 500
# ==============================================================================
    
@app.route('/api/versao', methods=['GET'])
def get_versao_app():
    """Lê e retorna o conteúdo do ficheiro de versão."""
    try:
        # Garante que o ficheiro é procurado na mesma pasta que o app.py
        caminho_base = os.path.dirname(os.path.abspath(__file__))
        caminho_json = os.path.join(caminho_base, 'versao.json')
        
        with open(caminho_json, 'r', encoding="utf-8") as f:
            dados_versao = json.load(f)
        return jsonify(dados_versao), 200
    except FileNotFoundError:
        return jsonify({'erro': 'Ficheiro de versão não encontrado no servidor.'}), 404
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

    
    
    
# Dentro do app.py, na secção de rotas de Usuários

@app.route('/api/usuario/me', methods=['GET'])
@jwt_required()
def get_usuario_logado():
    """Retorna as informações do usuário logado (dono do token)."""
    # A função get_jwt_identity() devolve o que guardámos como 'identity' (o nosso id_usuario)
    id_usuario_logado = get_jwt_identity()
    
    # Buscamos o usuário na base de dados com esse ID
    usuario = Usuario.query.get(id_usuario_logado)
    
    if not usuario:
        return jsonify({"erro": "Usuário não encontrado"}), 404

    usuario_json = {
        'id': usuario.id_usuario,
        'nome': usuario.nome,
        'login': usuario.login,
        'permissao': usuario.permissao
    }
    return jsonify(usuario_json), 200

# (Por uma questão de brevidade, omiti as rotas de Fornecedores e Naturezas,
# mas elas seguiriam exatamente o mesmo padrão de refinamento.)




# Dentro do seu app.py

# ==============================================================================
# ROTAS DA API PARA FORNECEDORES
# ==============================================================================

@app.route('/api/fornecedores', methods=['GET'])
@jwt_required()
def get_todos_fornecedores():
    """Retorna uma lista de todos os fornecedores."""
    try:
        fornecedores = Fornecedor.query.order_by(Fornecedor.nome).all()
        fornecedores_json = [{'id': f.id_fornecedor, 'nome': f.nome} for f in fornecedores]
        return jsonify(fornecedores_json), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/fornecedores', methods=['POST'])
@jwt_required()
def add_novo_fornecedor():
    """Cria um novo fornecedor."""
    try:
        dados = request.get_json()
        if 'nome' not in dados or not dados['nome'].strip():
            return jsonify({'erro': 'O nome do fornecedor é obrigatório.'}), 400

        novo_fornecedor = Fornecedor(nome=dados['nome'])
        db.session.add(novo_fornecedor)
        db.session.commit()
        return jsonify({'mensagem': 'Fornecedor adicionado com sucesso!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/fornecedores/<int:id_fornecedor>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def fornecedor_por_id_endpoint(id_fornecedor):
    """Lida com operações para um fornecedor específico (ler, editar, apagar)."""
    try:
        fornecedor = Fornecedor.query.get_or_404(id_fornecedor)

        # --- NOVO BLOCO DE CÓDIGO ---
        # Lógica para o método GET (Ler um por ID)
        if request.method == 'GET':
            return jsonify({
                'id': fornecedor.id_fornecedor,
                'nome': fornecedor.nome
            }), 200
        # --- FIM DO NOVO BLOCO ---

        elif request.method == 'PUT':
            dados = request.get_json()
            if 'nome' not in dados or not dados['nome'].strip():
                return jsonify({'erro': 'O nome do fornecedor é obrigatório.'}), 400
            fornecedor.nome = dados['nome']
            db.session.commit()
            return jsonify({'mensagem': 'Fornecedor atualizado com sucesso!'}), 200

        elif request.method == 'DELETE':
            if fornecedor.produtos:
                return jsonify({'erro': 'Este fornecedor não pode ser excluído pois está associado a um ou mais produtos.'}), 400
            
            db.session.delete(fornecedor)
            db.session.commit()
            return jsonify({'mensagem': 'Fornecedor excluído com sucesso!'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500
    
    
    
    
# Dentro do seu app.py

# ==============================================================================
# ROTAS DA API PARA NATUREZAS
# ==============================================================================

@app.route('/api/naturezas', methods=['GET'])
@jwt_required()
def get_todas_naturezas():
    """Retorna uma lista de todas as naturezas."""
    try:
        naturezas = Natureza.query.order_by(Natureza.nome).all()
        naturezas_json = [{'id': n.id_natureza, 'nome': n.nome} for n in naturezas]
        return jsonify(naturezas_json), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/naturezas', methods=['POST'])
@jwt_required()
def add_nova_natureza():
    """Cria uma nova natureza."""
    try:
        dados = request.get_json()
        if 'nome' not in dados or not dados['nome'].strip():
            return jsonify({'erro': 'O nome da natureza é obrigatório.'}), 400

        nova_natureza = Natureza(nome=dados['nome'])
        db.session.add(nova_natureza)
        db.session.commit()
        return jsonify({'mensagem': 'Natureza adicionada com sucesso!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/naturezas/<int:id_natureza>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def natureza_por_id_endpoint(id_natureza):
    """Lida com operações para uma natureza específica (ler, editar, apagar)."""
    try:
        natureza = Natureza.query.get_or_404(id_natureza)

        # --- NOVO BLOCO DE CÓDIGO ---
        # Lógica para o método GET (Ler uma por ID)
        if request.method == 'GET':
            return jsonify({
                'id': natureza.id_natureza,
                'nome': natureza.nome
            }), 200
        # --- FIM DO NOVO BLOCO ---

        elif request.method == 'PUT':
            dados = request.get_json()
            if 'nome' not in dados or not dados['nome'].strip():
                return jsonify({'erro': 'O nome da natureza é obrigatório.'}), 400
            natureza.nome = dados['nome']
            db.session.commit()
            return jsonify({'mensagem': 'Natureza atualizada com sucesso!'}), 200

        elif request.method == 'DELETE':
            if natureza.produtos:
                return jsonify({'erro': 'Esta natureza não pode ser excluída pois está associada a um ou mais produtos.'}), 400
            
            db.session.delete(natureza)
            db.session.commit()
            return jsonify({'mensagem': 'Natureza excluída com sucesso!'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500


# TRECHO PARA SUBSTITUIR a função usuarios_endpoint em app.py

# ==============================================================================
# ROTAS DA API PARA USUÁRIOS
# ==============================================================================

@app.route('/api/usuarios', methods=['GET'])
@jwt_required() # Protege a rota, exigindo um token
def get_todos_usuarios():
    """Retorna uma lista de todos os usuários."""
    try:
        # Verifica se o usuário logado é um Administrador
        claims = get_jwt()
        if claims.get('permissao') != 'Administrador':
            return jsonify({"erro": "Acesso negado: permissão de Administrador necessária."}), 403

        usuarios = Usuario.query.all()
        usuarios_json = []
        for u in usuarios:
            usuarios_json.append({
                'id': u.id_usuario,
                'nome': u.nome,
                'login': u.login,
                'permissao': u.permissao,
                'ativo': u.ativo
            })
        return jsonify(usuarios_json), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios', methods=['POST'])
@jwt_required() # Protege a rota, exigindo um token
def add_novo_usuario():
    """Cria um novo usuário."""
    try:
        # Verifica se o usuário logado é um Administrador
        claims = get_jwt()
        if claims.get('permissao') != 'Administrador':
            return jsonify({"erro": "Acesso negado: permissão de Administrador necessária."}), 403

        dados = request.get_json()
        if 'login' not in dados or 'senha' not in dados or 'nome' not in dados or 'permissao' not in dados:
            return jsonify({'erro': 'Dados incompletos'}), 400

        novo_usuario = Usuario(
            nome=dados['nome'],
            login=dados['login'],
            permissao=dados['permissao']
        )
        novo_usuario.set_password(dados['senha'])
        
        db.session.add(novo_usuario)
        db.session.commit()
        
        return jsonify({'mensagem': 'Usuário criado com sucesso!'}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500
    
    
@app.route('/api/usuarios/<int:id_usuario>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def usuario_por_id_endpoint(id_usuario):
    """Lida com operações para um usuário específico (ler, editar, desativar)."""
    # Garante que apenas administradores podem mexer nos usuários
    claims = get_jwt()
    if claims.get('permissao') != 'Administrador':
        return jsonify({"erro": "Acesso negado: permissão de Administrador necessária."}), 403
    
    try:
        usuario = Usuario.query.get_or_404(id_usuario)

        # ---- LER UM USUÁRIO (GET) ----
        if request.method == 'GET':
            return jsonify({
                'id': usuario.id_usuario,
                'nome': usuario.nome,
                'login': usuario.login,
                'permissao': usuario.permissao,
                'ativo': usuario.ativo
            }), 200

        # ---- EDITAR UM USUÁRIO (PUT) ----
        elif request.method == 'PUT':
            dados = request.get_json()
            if not dados or 'nome' not in dados or 'login' not in dados or 'permissao' not in dados:
                return jsonify({'erro': 'Dados incompletos para atualização'}), 400

            # Atualiza os dados básicos
            usuario.nome = dados['nome']
            usuario.login = dados['login']
            usuario.permissao = dados['permissao']
            
            # Atualiza a senha APENAS se uma nova for fornecida
            if 'senha' in dados and dados['senha']:
                usuario.set_password(dados['senha'])
            
            db.session.commit()
            return jsonify({'mensagem': 'Usuário atualizado com sucesso!'}), 200

        # ---- DESATIVAR/REATIVAR UM USUÁRIO (DELETE) ----
        elif request.method == 'DELETE':
            # Implementação de Soft Delete
            # Em vez de apagar, apenas mudamos o status 'ativo'
            usuario.ativo = not usuario.ativo # Inverte o status atual
            db.session.commit()
            
            status = "desativado" if not usuario.ativo else "reativado"
            return jsonify({'mensagem': f'Usuário {status} com sucesso!'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500
    



@app.route('/api/usuario/mudar-senha', methods=['POST'])
@jwt_required()
def mudar_senha_usuario():
    """Permite que o utilizador logado altere a sua própria senha."""
    try:
        # 1. Identifica o utilizador a partir do token
        id_usuario_logado = get_jwt_identity()
        usuario = Usuario.query.get(id_usuario_logado)
        if not usuario:
            return jsonify({"erro": "Utilizador não encontrado"}), 404

        dados = request.get_json()
        senha_atual = dados.get('senha_atual')
        nova_senha = dados.get('nova_senha')
        confirmacao_nova_senha = dados.get('confirmacao_nova_senha')

        # 2. Validações de segurança
        if not senha_atual or not nova_senha or not confirmacao_nova_senha:
            return jsonify({'erro': 'Todos os campos são obrigatórios.'}), 400

        if not usuario.check_password(senha_atual):
            return jsonify({'erro': 'A senha atual está incorreta.'}), 401 # 401 Unauthorized

        if nova_senha != confirmacao_nova_senha:
            return jsonify({'erro': 'A nova senha e a confirmação não correspondem.'}), 400
            
        if len(nova_senha) < 6: # Exemplo de uma regra de complexidade mínima
            return jsonify({'erro': 'A nova senha deve ter pelo menos 6 caracteres.'}), 400

        # 3. Se tudo estiver correto, altera a senha
        usuario.set_password(nova_senha)
        db.session.commit()

        return jsonify({'mensagem': 'Senha alterada com sucesso!'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500    
    
# ==============================================================================
#          ROTAS DA API PARA DASHBOARD E OUTRAS FUNÇÕES
# ==============================================================================



@app.route('/api/dashboard/kpis', methods=['GET'])
@jwt_required()
def get_dashboard_kpis():
    """Calcula e retorna os principais indicadores (KPIs) para o dashboard."""
    try:
        # 1. Total de produtos cadastrados
        total_produtos = db.session.query(func.count(Produto.id_produto)).scalar()

        # 2. Total de fornecedores
        total_fornecedores = db.session.query(func.count(Fornecedor.id_fornecedor)).scalar()

        # 3. Valor total do estoque (mais complexo)
        # Subquery para calcular o saldo de cada produto
        subquery_saldos = db.session.query(
            MovimentacaoEstoque.id_produto,
            func.sum(
                case(
                    (MovimentacaoEstoque.tipo == 'Entrada', MovimentacaoEstoque.quantidade),
                    (MovimentacaoEstoque.tipo == 'Saida', -MovimentacaoEstoque.quantidade)
                )
            ).label('saldo')
        ).group_by(MovimentacaoEstoque.id_produto).subquery()

        # Query principal que multiplica o saldo de cada produto pelo seu preço
        query_valor_total = db.session.query(
            func.sum(Produto.preco * subquery_saldos.c.saldo)
        ).join(
            subquery_saldos, Produto.id_produto == subquery_saldos.c.id_produto
        )
        
        valor_total_estoque = query_valor_total.scalar() or 0

        # Monta o JSON de resposta
        kpis = {
            'total_produtos': total_produtos,
            'total_fornecedores': total_fornecedores,
            'valor_total_estoque': float(valor_total_estoque) # Converte de Decimal para float
        }
        
        return jsonify(kpis), 200

    except Exception as e:
        return jsonify({'erro': str(e)}), 500
    
# ==============================================================================
# Bloco de Execução Principal
# ==============================================================================

import io
import pandas as pd
from flask import send_file
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from datetime import datetime

# --- FUNÇÕES AUXILIARES PARA GERAR ARQUIVOS ---

# Substitua a sua função gerar_inventario_pdf por esta versão corrigida


def gerar_pdf_etiquetas(produtos):
    """
    Gera um PDF onde cada página é uma etiqueta de 62mm x 100mm,
    preenchida com os dados de um único produto.
    """
    buffer = io.BytesIO()
    
    # --- CORREÇÃO DEFINITIVA: O tamanho da página é o tamanho da etiqueta ---
    largura_pagina, altura_pagina = 62 * mm, 100 * mm
    doc = SimpleDocTemplate(buffer, pagesize=(largura_pagina, altura_pagina),
                            leftMargin=5*mm, rightMargin=5*mm, topMargin=5*mm, bottomMargin=5*mm)
    
    elementos = []
    styles = getSampleStyleSheet()
    styles['Normal'].fontSize = 12
    styles['Normal'].leading = 14 # Espaçamento entre linhas
    
    style_codigo = ParagraphStyle(name='CodigoStyle', parent=styles['Normal'], alignment=TA_CENTER)
    
    # Itera através de cada produto para criar uma página para cada um
    for produto in produtos:
        # Informações do Produto
        nome_produto = Paragraph(f"<b>{produto.nome}</b>", styles['Normal'])
        
        # Geração do Código de Barras
        codigo_de_barras = code128.Code128(produto.codigo, barHeight=20*mm, barWidth=0.4*mm)
        
        # Cria um parágrafo com o código do produto por extenso
        codigo_texto = Paragraph(produto.codigo, style_codigo)
        
        # Adiciona os elementos à página/etiqueta
        elementos.append(nome_produto)
        elementos.append(Spacer(1, 8 * mm))
        elementos.append(codigo_de_barras)
        elementos.append(Spacer(1, 2 * mm))
        elementos.append(codigo_texto)
        
        # Adiciona uma quebra de página para começar a próxima etiqueta
        elementos.append(PageBreak())

    # Remove a última quebra de página desnecessária
    if elementos:
        elementos.pop()

    doc.build(elementos)
    buffer.seek(0)
    return buffer



def gerar_inventario_pdf(dados):
    """Gera um PDF do relatório de inventário atual."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elementos = []
    styles = getSampleStyleSheet()

    # Título
    titulo = Paragraph("Relatório de Inventário Atual", styles['h1'])
    elementos.append(titulo)
    elementos.append(Spacer(1, 12))

    # Cabeçalhos da tabela
    dados_tabela = [["Código", "Nome", "Saldo", "Preço Unit. (R$)", "Valor Total (R$)"]]
    # Dados
    valor_total_geral = 0
    for item in dados:
        # --- A CORREÇÃO ESTÁ AQUI ---
        # Multiplicamos diretamente, sem converter para float.
        # O objeto Decimal sabe como se multiplicar por um inteiro (saldo).
        valor_total_item = item['saldo_atual'] * item['preco']
        valor_total_geral += valor_total_item
        
        # O resto da formatação para exibição continua igual
        dados_tabela.append([
            item['codigo'],
            item['nome'],
            str(item['saldo_atual']),
            f"{float(item['preco']):.2f}", # Usamos float() aqui apenas para formatar o texto
            f"{float(valor_total_item):.2f}"
        ])
    
    tabela = Table(dados_tabela)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elementos.append(tabela)
    elementos.append(Spacer(1, 12))

    # Sumário
    sumario = Paragraph(f"<b>Valor Total do Estoque:</b> R$ {float(valor_total_geral):.2f}", styles['h3'])
    elementos.append(sumario)

    doc.build(elementos)
    buffer.seek(0)
    return buffer

def gerar_historico_pdf(dados):
    """Gera um PDF do relatório de histórico de movimentações."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elementos = []
    styles = getSampleStyleSheet()

    titulo = Paragraph("Relatório de Histórico de Movimentações", styles['h1'])
    elementos.append(titulo)
    elementos.append(Spacer(1, 12))
    
    # --- ALTERAÇÃO AQUI ---
    dados_tabela = [["Data/Hora", "Produto", "Tipo", "Qtd.", "Saldo Após", "Usuário", "Motivo"]]
    for item in dados:
        dados_tabela.append([
            item['data_hora'],
            f"{item['produto_codigo']} - {item['produto_nome']}",
            item['tipo'],
            str(item['quantidade']),
            str(item['saldo_apos']), # <<< NOVA LINHA
            item['usuario_nome'],
            item.get('motivo_saida', '')
        ])
        
    # Ajuste nas larguras das colunas para a nova coluna
    tabela = Table(dados_tabela, colWidths=[110, 180, 50, 40, 60, 100, 130]) 
    # ... (o resto da função TableStyle continua igual)
    tabela.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elementos.append(tabela)
    doc.build(elementos)
    buffer.seek(0)
    return buffer

# --- ENDPOINTS DA API DE RELATÓRIOS ---

@app.route('/api/relatorios/inventario', methods=['GET'])
@jwt_required()
def relatorio_inventario():
    """Gera e retorna o relatório de inventário em PDF ou XLSX."""
    formato = request.args.get('formato', 'pdf').lower()

    # Lógica para buscar os dados (adaptada do endpoint de saldos)
    produtos = Produto.query.all()
    dados_relatorio = []
    for produto in produtos:
        saldo = calcular_saldo_produto(produto.id_produto)
        dados_relatorio.append({
            'codigo': produto.codigo.strip(),
            'nome': produto.nome,
            'saldo_atual': saldo,
            'preco': produto.preco
        })

    if formato == 'xlsx':
        df = pd.DataFrame(dados_relatorio)
        df['valor_total'] = df['saldo_atual'] * df['preco']
        df = df.rename(columns={'codigo': 'Código', 'nome': 'Nome', 'saldo_atual': 'Saldo', 'preco': 'Preço Unitário (R$)', 'valor_total': 'Valor Total (R$)'})
        
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        return send_file(buffer, download_name="relatorio_inventario.xlsx", as_attachment=True)

    else: # PDF como padrão
        pdf_buffer = gerar_inventario_pdf(dados_relatorio)
        return send_file(pdf_buffer, download_name="relatorio_inventario.pdf", as_attachment=True)


@app.route('/api/relatorios/movimentacoes', methods=['GET'])
@jwt_required()
def relatorio_movimentacoes():
    """
    Gera e retorna o relatório de movimentações em vários formatos (PDF, XLSX, JSON).
    """
    # --- ALTERAÇÃO AQUI: O formato padrão agora é 'json' se não for especificado ---
    formato = request.args.get('formato', 'json').lower()
    data_inicio_str = request.args.get('data_inicio')
    # ... (o resto da lógica de busca e cálculo do saldo continua igual) ...
    data_fim_str = request.args.get('data_fim')
    tipo = request.args.get('tipo')

    query = MovimentacaoEstoque.query.options(
        joinedload(MovimentacaoEstoque.produto),
        joinedload(MovimentacaoEstoque.usuario)
    ).order_by(MovimentacaoEstoque.id_produto, MovimentacaoEstoque.data_hora)

    if data_inicio_str:
        query = query.filter(MovimentacaoEstoque.data_hora >= datetime.strptime(data_inicio_str, '%Y-%m-%d'))
    if data_fim_str:
        data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        query = query.filter(MovimentacaoEstoque.data_hora <= data_fim)
    
    todas_movimentacoes = query.all()

    dados_relatorio = []
    saldos_atuais = {}

    for mov in todas_movimentacoes:
        id_produto = mov.id_produto
        
        if id_produto not in saldos_atuais:
            saldo_inicial_query = db.session.query(
                func.sum(case(
                    (MovimentacaoEstoque.tipo == 'Entrada', MovimentacaoEstoque.quantidade),
                    (MovimentacaoEstoque.tipo == 'Saida', -MovimentacaoEstoque.quantidade)
                ))
            ).filter(
                MovimentacaoEstoque.id_produto == id_produto,
                MovimentacaoEstoque.data_hora < datetime.strptime(data_inicio_str, '%Y-%m-%d') if data_inicio_str else True
            )
            saldo_inicial = saldo_inicial_query.scalar() or 0
            saldos_atuais[id_produto] = saldo_inicial

        if mov.tipo == 'Entrada':
            saldos_atuais[id_produto] += mov.quantidade
        else:
            saldos_atuais[id_produto] -= mov.quantidade
        
        dados_relatorio.append({
            'data_hora': mov.data_hora.strftime('%d/%m/%Y %H:%M:%S'),
            'produto_codigo': mov.produto.codigo.strip() if mov.produto else 'N/A',
            'produto_nome': mov.produto.nome if mov.produto else 'Produto Excluído',
            'tipo': mov.tipo,
            'quantidade': mov.quantidade,
            'saldo_apos': saldos_atuais[id_produto],
            'usuario_nome': mov.usuario.nome if mov.usuario else 'Usuário Excluído',
            'motivo_saida': mov.motivo_saida if mov.motivo_saida else ''
        })

    if tipo and tipo in ["Entrada", "Saida"]:
        dados_relatorio = [linha for linha in dados_relatorio if linha['tipo'] == tipo]

    dados_relatorio.sort(key=lambda x: datetime.strptime(x['data_hora'], '%d/%m/%Y %H:%M:%S'), reverse=True)

    # --- ALTERAÇÃO AQUI: Adicionamos uma nova condição para JSON ---
    if formato == 'json':
        return jsonify(dados_relatorio), 200
    
    elif formato == 'xlsx':
        df = pd.DataFrame(dados_relatorio)
        df = df.rename(columns={
            'data_hora': 'Data/Hora', 'produto_codigo': 'Cód. Produto', 'produto_nome': 'Nome Produto',
            'tipo': 'Tipo', 'quantidade': 'Qtd. Mov.', 'saldo_apos': 'Saldo Após', 'usuario_nome': 'Usuário', 'motivo_saida': 'Motivo da Saída'
        })
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        return send_file(buffer, download_name="relatorio_movimentacoes.xlsx", as_attachment=True)
        
    else: # PDF
        pdf_buffer = gerar_historico_pdf(dados_relatorio)
        return send_file(pdf_buffer, download_name="relatorio_movimentacoes.pdf", as_attachment=True)
    
    
@app.route('/api/produtos/etiquetas', methods=['POST'])
@jwt_required()
def gerar_etiquetas_produtos():
    """
    Recebe uma lista de IDs de produtos e gera um PDF com as etiquetas correspondentes.
    """
    try:
        dados = request.get_json()
        if not dados or 'product_ids' not in dados:
            return jsonify({'erro': 'Lista de IDs de produtos em falta.'}), 400

        product_ids = dados['product_ids']
        
        # Busca os produtos no banco de dados com base nos IDs recebidos
        produtos_para_etiqueta = Produto.query.filter(Produto.id_produto.in_(product_ids)).all()
        
        if not produtos_para_etiqueta:
            return jsonify({'erro': 'Nenhum produto encontrado com os IDs fornecidos.'}), 404

        # Chama a função auxiliar para gerar o PDF
        pdf_buffer = gerar_pdf_etiquetas(produtos_para_etiqueta)
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name="etiquetas.pdf",
            mimetype='application/pdf'
        )

    except Exception as e:
        return jsonify({'erro': str(e)}), 500
# ==============================================================================
# MÓDULO DE RELATÓRIOS (ADICIONE NO FINAL DO SEU app.py)
# ==============================================================================
