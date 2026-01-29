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
import barcode
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib import colors
from reportlab.graphics.barcode import code128
import os
import json
import pandas as pd
from flask import send_file

# ==============================================================================
# CONFIGURAÇÃO INICIAL
# ==============================================================================

app = Flask(__name__)

# --- CONFIGURAÇÃO DO JWT ---
app.config["JWT_SECRET_KEY"] = "minha-chave-super-secreta-para-o-projeto-de-estoque"
jwt = JWTManager(app)

# --- CONFIGURAÇÃO DO BANCO DE DADOS (ATUALIZADO PARA O SERVIDOR 192.168.17.200) ---
# Verifique se o usuário 'root' e a senha 'senha123' estão corretos nesse servidor.
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:senha123@192.168.17.200/estoque_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

class Setor(db.Model):
    __tablename__ = 'setor'
    id_setor = db.Column(db.Integer, primary_key=True)
    nome = db.Column('nome', db.String(100), unique=True, nullable=False)
    produtos = db.relationship('Produto', back_populates='setor')

class Produto(db.Model):
    __tablename__ = 'produto'
    id_produto = db.Column('Id_produto', db.Integer, primary_key=True)
    nome = db.Column('Nome', db.String(100), nullable=False)
    codigo = db.Column('Codigo', db.String(20), unique=True, nullable=False)
    descricao = db.Column('Descricao', db.String(200))
    preco = db.Column('Preco', db.Numeric(10, 2), nullable=True, default=0.00)
    codigoB = db.Column('CodigoB', db.String(20))
    codigoC = db.Column('CodigoC', db.String(20))
    
    # Novos Campos de Setor
    id_setor = db.Column(db.Integer, db.ForeignKey('setor.id_setor'), nullable=True)
    setor = db.relationship('Setor', back_populates='produtos')

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
    try:
        termo_busca = request.args.get('search')
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
        
        # Otimização: carregar setor junto
        produtos_db = query.options(joinedload(Produto.setor)).all()
        
        if not produtos_db:
            return jsonify([]), 200

        # Montagem Manual para Performance
        product_ids = [p.id_produto for p in produtos_db]
        
        fornecedores_map = {f.id_fornecedor: f.nome for f in Fornecedor.query.all()}
        naturezas_map = {n.id_natureza: n.nome for n in Natureza.query.all()}
        
        prod_forn_assoc = db.session.query(produto_fornecedor).filter(produto_fornecedor.c.FK_PRODUTO_Id_produto.in_(product_ids)).all()
        prod_nat_assoc = db.session.query(produto_natureza).filter(produto_natureza.c.fk_PRODUTO_Id_produto.in_(product_ids)).all()

        produto_fornecedores = {}
        for p_id, f_id in prod_forn_assoc:
            if p_id not in produto_fornecedores: produto_fornecedores[p_id] = []
            produto_fornecedores[p_id].append(fornecedores_map.get(f_id, ''))

        produto_naturezas = {}
        for p_id, n_id in prod_nat_assoc:
            if p_id not in produto_naturezas: produto_naturezas[p_id] = []
            produto_naturezas[p_id].append(naturezas_map.get(n_id, ''))

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
                'naturezas': ", ".join(sorted(naturezas_list)),
                'setor_nome': produto.setor.nome if produto.setor else '',
                'id_setor': produto.id_setor
            })
            
        return jsonify(produtos_json), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/produtos', methods=['POST'])
@jwt_required()
def add_novo_produto():
    try:
        dados = request.get_json()
        required_fields = ['nome', 'codigo']
        if not all(field in dados and dados[field] for field in required_fields):
            return jsonify({'erro': 'Campos obrigatórios (nome, codigo) não podem estar vazios.'}), 400

        novo_produto = Produto(
            nome=dados['nome'],
            codigo=dados['codigo'],
            descricao=dados.get('descricao'),
            preco=dados.get('preco', '0.00').replace(',', '.'), 
            codigoB=dados.get('codigoB'),
            codigoC=dados.get('codigoC'),
            id_setor=dados.get('id_setor')
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

@app.route('/api/produtos/<int:id_produto>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def produto_por_id_endpoint(id_produto):
    try:
        produto = Produto.query.get_or_404(id_produto)

        if request.method == 'GET':
            produto_json = {
                'id': produto.id_produto, 
                'nome': produto.nome,
                'codigo': produto.codigo.strip() if produto.codigo else '',
                'descricao': produto.descricao, 
                'preco': str(produto.preco),
                'codigoB': produto.codigoB, 
                'codigoC': produto.codigoC,
                'id_setor': produto.id_setor,
                'setor_nome': produto.setor.nome if produto.setor else '',
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
            produto.id_setor = dados.get('id_setor')

            if 'fornecedores_ids' in dados:
                produto.fornecedores.clear()
                if dados['fornecedores_ids']:
                    produto.fornecedores = Fornecedor.query.filter(Fornecedor.id_fornecedor.in_(dados['fornecedores_ids'])).all()

            if 'naturezas_ids' in dados:
                produto.naturezas.clear()
                if dados['naturezas_ids']:
                    produto.naturezas = Natureza.query.filter(Natureza.id_natureza.in_(dados['naturezas_ids'])).all()

            db.session.commit()

            updated_product = Produto.query.options(
                joinedload(Produto.fornecedores),
                joinedload(Produto.naturezas),
                joinedload(Produto.setor)
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
                'naturezas': naturezas_str,
                'setor_nome': updated_product.setor.nome if updated_product.setor else '',
                'id_setor': updated_product.id_setor
            }
            return jsonify(response_data), 200
        
        elif request.method == 'DELETE':
            movimentacao_existente = MovimentacaoEstoque.query.filter_by(id_produto=id_produto).first()
            if movimentacao_existente:
                return jsonify({'erro': 'Produto possui histórico de movimentações e não pode ser excluído.'}), 400

            db.session.delete(produto)
            db.session.commit()
            return jsonify({'mensagem': 'Produto excluído com sucesso!'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/formularios/produto_data', methods=['GET'])
@jwt_required()
def get_form_produto_data():
    try:
        produto_id = request.args.get('produto_id', type=int)
        
        fornecedores_data = db.session.query(Fornecedor.id_fornecedor, Fornecedor.nome).order_by(Fornecedor.nome).all()
        naturezas_data = db.session.query(Natureza.id_natureza, Natureza.nome).order_by(Natureza.nome).all()
        
        dados_produto = None
        if produto_id:
            produto = Produto.query.options(
                joinedload(Produto.fornecedores),
                joinedload(Produto.naturezas),
                joinedload(Produto.setor)
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
                    'id_setor': produto.id_setor,
                    'fornecedores': [{'id': f.id_fornecedor} for f in produto.fornecedores],
                    'naturezas': [{'id': n.id_natureza} for n in produto.naturezas]
                }

        response_data = {
            'fornecedores': [{'id': id, 'nome': nome} for id, nome in fornecedores_data],
            'naturezas': [{'id': id, 'nome': nome} for id, nome in naturezas_data],
            'produto': dados_produto
        }
        return jsonify(response_data), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/produtos/codigo/<string:codigo>', methods=['GET'])
@jwt_required()
def get_produto_por_codigo(codigo):
    try:
        produto = Produto.query.filter_by(codigo=codigo.strip()).first()
        if produto:
            produto_json = {
                'id': produto.id_produto,
                'nome': produto.nome,
                'codigo': produto.codigo.strip(),
                'descricao': produto.descricao,
                'preco': str(produto.preco)
            }
            return jsonify(produto_json), 200
        else:
            return jsonify({'erro': 'Produto não encontrado.'}), 404
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/produtos/importar', methods=['POST'])
@jwt_required()
def importar_produtos_csv():
    if 'file' not in request.files:
        return jsonify({'erro': 'Nenhum ficheiro enviado.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'erro': 'Nome de ficheiro vazio.'}), 400

    sucesso_count = 0
    erros = []
    
    try:
        file_bytes = file.stream.read()
        try:
            stream_content = file_bytes.decode("UTF-8")
        except UnicodeDecodeError:
            stream_content = file_bytes.decode("latin-1")
        
        stream = io.StringIO(stream_content, newline=None)
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
                    erros.append(f"Linha {linha_num}: Campos codigo/nome vazios.")
                    continue

                if Produto.query.filter_by(codigo=codigo).first():
                    erros.append(f"Linha {linha_num}: Código '{codigo}' já existe.")
                    continue

                novo_produto = Produto(
                    codigo=codigo,
                    nome=nome,
                    preco=preco_str.replace(',', '.') if preco_str else '0.00',
                    descricao=linha.get('descricao', '').strip()
                )

                fornecedores_nomes = [fn.strip() for fn in linha.get('fornecedores_nomes', '').split(',') if fn.strip()]
                if fornecedores_nomes:
                    novo_produto.fornecedores.extend(Fornecedor.query.filter(Fornecedor.nome.in_(fornecedores_nomes)).all())

                naturezas_nomes = [nn.strip() for nn in linha.get('naturezas_nomes', '').split(',') if nn.strip()]
                if naturezas_nomes:
                    novo_produto.naturezas.extend(Natureza.query.filter(Natureza.nome.in_(naturezas_nomes)).all())

                db.session.add(novo_produto)
                db.session.flush()

                qtd = linha.get('quantidade', '0').strip()
                if qtd and int(qtd) > 0:
                    mov = MovimentacaoEstoque(
                        id_produto=novo_produto.id_produto,
                        id_usuario=id_usuario_logado,
                        quantidade=int(qtd),
                        tipo='Entrada',
                        motivo_saida='Importação Inicial'
                    )
                    db.session.add(mov)
                
                sucesso_count += 1

            except Exception as e_interno:
                erros.append(f"Linha {linha_num}: Erro - {e_interno}")
                continue

        db.session.commit()
        return jsonify({'mensagem': 'Importação concluída!', 'produtos_importados': sucesso_count, 'erros': erros}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

# --- ROTAS DE SETORES (NOVO) ---

@app.route('/api/setores', methods=['GET'])
@jwt_required()
def get_todos_setores():
    try:
        setores = Setor.query.order_by(Setor.nome).all()
        return jsonify([{'id': s.id_setor, 'nome': s.nome} for s in setores]), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/setores', methods=['POST'])
@jwt_required()
def add_novo_setor():
    try:
        dados = request.get_json()
        if 'nome' not in dados or not dados['nome'].strip():
            return jsonify({'erro': 'Nome do setor obrigatório.'}), 400
        novo = Setor(nome=dados['nome'])
        db.session.add(novo)
        db.session.commit()
        return jsonify({'mensagem': 'Setor criado!'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/setores/<int:id_setor>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def gerenciar_setor(id_setor):
    try:
        setor = Setor.query.get_or_404(id_setor)
        
        if request.method == 'GET':
            return jsonify({'id': setor.id_setor, 'nome': setor.nome}), 200
            
        if request.method == 'PUT':
            dados = request.get_json()
            setor.nome = dados['nome']
            db.session.commit()
            return jsonify({'mensagem': 'Atualizado!'}), 200
            
        if request.method == 'DELETE':
            if setor.produtos:
                return jsonify({'erro': 'Setor em uso por produtos.'}), 400
            db.session.delete(setor)
            db.session.commit()
            return jsonify({'mensagem': 'Removido!'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

# --- ROTAS DE FORNECEDORES E NATUREZAS ---

@app.route('/api/fornecedores', methods=['GET'])
@jwt_required()
def get_todos_fornecedores():
    f = Fornecedor.query.order_by(Fornecedor.nome).all()
    return jsonify([{'id': i.id_fornecedor, 'nome': i.nome} for i in f]), 200

@app.route('/api/fornecedores', methods=['POST'])
@jwt_required()
def add_novo_fornecedor():
    d = request.get_json()
    db.session.add(Fornecedor(nome=d['nome']))
    db.session.commit()
    return jsonify({'mensagem': 'Criado!'}), 201

@app.route('/api/fornecedores/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def gerenciar_fornecedor(id):
    obj = Fornecedor.query.get_or_404(id)
    if request.method == 'GET': return jsonify({'id': obj.id_fornecedor, 'nome': obj.nome})
    if request.method == 'PUT':
        obj.nome = request.get_json()['nome']
        db.session.commit()
        return jsonify({'mensagem': 'Atualizado'})
    if request.method == 'DELETE':
        if obj.produtos: return jsonify({'erro': 'Em uso'}), 400
        db.session.delete(obj)
        db.session.commit()
        return jsonify({'mensagem': 'Deletado'})

@app.route('/api/naturezas', methods=['GET'])
@jwt_required()
def get_todas_naturezas():
    n = Natureza.query.order_by(Natureza.nome).all()
    return jsonify([{'id': i.id_natureza, 'nome': i.nome} for i in n]), 200

@app.route('/api/naturezas', methods=['POST'])
@jwt_required()
def add_nova_natureza():
    d = request.get_json()
    db.session.add(Natureza(nome=d['nome']))
    db.session.commit()
    return jsonify({'mensagem': 'Criado!'}), 201

@app.route('/api/naturezas/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def gerenciar_natureza(id):
    obj = Natureza.query.get_or_404(id)
    if request.method == 'GET': return jsonify({'id': obj.id_natureza, 'nome': obj.nome})
    if request.method == 'PUT':
        obj.nome = request.get_json()['nome']
        db.session.commit()
        return jsonify({'mensagem': 'Atualizado'})
    if request.method == 'DELETE':
        if obj.produtos: return jsonify({'erro': 'Em uso'}), 400
        db.session.delete(obj)
        db.session.commit()
        return jsonify({'mensagem': 'Deletado'})

# --- ROTAS DE ESTOQUE ---

@app.route('/api/estoque/entrada', methods=['POST'])
@jwt_required()
def registrar_entrada():
    try:
        dados = request.get_json()
        saldo_atual = calcular_saldo_produto(dados['id_produto'])
        novo = MovimentacaoEstoque(
            id_produto=dados['id_produto'],
            quantidade=dados['quantidade'],
            id_usuario=get_jwt_identity(),
            tipo='Entrada'
        )
        db.session.add(novo)
        db.session.commit()
        return jsonify({'mensagem': 'Sucesso', 'novo_saldo': saldo_atual + dados['quantidade']}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estoque/saida', methods=['POST'])
@jwt_required()
def registrar_saida():
    try:
        dados = request.get_json()
        saldo = calcular_saldo_produto(dados['id_produto'])
        if saldo < dados['quantidade']:
            return jsonify({'erro': 'Saldo insuficiente'}), 400
        
        novo = MovimentacaoEstoque(
            id_produto=dados['id_produto'],
            quantidade=dados['quantidade'],
            id_usuario=get_jwt_identity(),
            tipo='Saida',
            motivo_saida=dados.get('motivo_saida')
        )
        db.session.add(novo)
        db.session.commit()
        return jsonify({'mensagem': 'Sucesso', 'novo_saldo': saldo - dados['quantidade']}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estoque/saldos', methods=['GET'])
@jwt_required()
def get_saldos_estoque():
    try:
        termo = request.args.get('search')
        setor_id = request.args.get('setor_id')
        
        query = Produto.query
        if termo:
            query = query.filter(or_(
                Produto.nome.ilike(f"%{termo}%"),
                Produto.codigo.ilike(f"%{termo}%"),
                Produto.codigoB.ilike(f"%{termo}%"),
                Produto.codigoC.ilike(f"%{termo}%")
            ))
        if setor_id:
            query = query.filter(Produto.id_setor == setor_id)
            
        produtos = query.options(joinedload(Produto.setor)).all()
        
        saldos = []
        for p in produtos:
            saldos.append({
                'id_produto': p.id_produto,
                'codigo': p.codigo.strip(),
                'nome': p.nome,
                'saldo_atual': calcular_saldo_produto(p.id_produto),
                'preco': str(p.preco),
                'codigoB': p.codigoB,
                'codigoC': p.codigoC,
                'setor_nome': p.setor.nome if p.setor else 'Sem Setor'
            })
        return jsonify(saldos), 200
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/movimentacoes', methods=['GET'])
@jwt_required()
def get_todas_movimentacoes():
    try:
        tipo = request.args.get('tipo')
        q = MovimentacaoEstoque.query.options(joinedload(MovimentacaoEstoque.produto), joinedload(MovimentacaoEstoque.usuario)).order_by(MovimentacaoEstoque.data_hora.desc())
        if tipo in ['Entrada', 'Saida']: q = q.filter(MovimentacaoEstoque.tipo == tipo)
        
        res = []
        for m in q.all():
            res.append({
                'id': m.id_movimentacao,
                'data_hora': m.data_hora.strftime('%d/%m/%Y %H:%M:%S'),
                'tipo': m.tipo,
                'quantidade': m.quantidade,
                'motivo_saida': m.motivo_saida,
                'produto_codigo': m.produto.codigo if m.produto else '',
                'produto_nome': m.produto.nome if m.produto else 'Excluído',
                'usuario_nome': m.usuario.nome if m.usuario else 'Excluído'
            })
        return jsonify(res), 200
    except Exception as e: return jsonify({'erro': str(e)}), 500

# --- ROTAS DE USUARIOS E LOGIN ---

@app.route('/api/login', methods=['POST'])
def login_endpoint():
    try:
        d = request.get_json()
        u = Usuario.query.filter_by(login=d.get('login'), ativo=True).first()
        if u and u.check_password(d.get('senha')):
            token = create_access_token(identity=str(u.id_usuario), additional_claims={'permissao': u.permissao}, expires_delta=timedelta(hours=8))
            return jsonify(access_token=token), 200
        return jsonify({"erro": "Credenciais inválidas"}), 401
    except Exception as e: return jsonify({'erro': str(e)}), 500

@app.route('/api/usuario/me', methods=['GET'])
@jwt_required()
def get_usuario_logado():
    u = Usuario.query.get(get_jwt_identity())
    if not u: return jsonify({"erro": "Não encontrado"}), 404
    return jsonify({'id': u.id_usuario, 'nome': u.nome, 'login': u.login, 'permissao': u.permissao}), 200

@app.route('/api/usuario/mudar-senha', methods=['POST'])
@jwt_required()
def mudar_senha_usuario():
    try:
        u = Usuario.query.get(get_jwt_identity())
        d = request.get_json()
        if not u.check_password(d['senha_atual']): return jsonify({'erro': 'Senha atual incorreta'}), 401
        if d['nova_senha'] != d['confirmacao_nova_senha']: return jsonify({'erro': 'Confirmação incorreta'}), 400
        u.set_password(d['nova_senha'])
        db.session.commit()
        return jsonify({'mensagem': 'Sucesso'}), 200
    except Exception as e: return jsonify({'erro': str(e)}), 500

@app.route('/api/usuarios', methods=['GET'])
@jwt_required()
def get_todos_usuarios():
    if get_jwt().get('permissao') != 'Administrador': return jsonify({"erro": "Acesso negado"}), 403
    return jsonify([{'id': u.id_usuario, 'nome': u.nome, 'login': u.login, 'permissao': u.permissao, 'ativo': u.ativo} for u in Usuario.query.all()]), 200

@app.route('/api/usuarios', methods=['POST'])
@jwt_required()
def add_usuario():
    if get_jwt().get('permissao') != 'Administrador': return jsonify({"erro": "Acesso negado"}), 403
    d = request.get_json()
    u = Usuario(nome=d['nome'], login=d['login'], permissao=d['permissao'])
    u.set_password(d['senha'])
    db.session.add(u)
    db.session.commit()
    return jsonify({'mensagem': 'Criado'}), 201

@app.route('/api/usuarios/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@jwt_required()
def gerenciar_usuario(id):
    if get_jwt().get('permissao') != 'Administrador': return jsonify({"erro": "Acesso negado"}), 403
    u = Usuario.query.get_or_404(id)
    if request.method == 'GET':
        return jsonify({'id': u.id_usuario, 'nome': u.nome, 'login': u.login, 'permissao': u.permissao, 'ativo': u.ativo})
    if request.method == 'PUT':
        d = request.get_json()
        u.nome = d['nome']
        u.login = d['login']
        u.permissao = d['permissao']
        if d.get('senha'): u.set_password(d['senha'])
        db.session.commit()
        return jsonify({'mensagem': 'Atualizado'})
    if request.method == 'DELETE':
        u.ativo = not u.ativo
        db.session.commit()
        return jsonify({'mensagem': 'Status alterado'})

# --- DASHBOARD E RELATORIOS ---

@app.route('/api/dashboard/kpis', methods=['GET'])
@jwt_required()
def get_dashboard_kpis():
    try:
        total_prod = db.session.query(func.count(Produto.id_produto)).scalar()
        total_forn = db.session.query(func.count(Fornecedor.id_fornecedor)).scalar()
        
        # Valor total estoque
        subquery = db.session.query(
            MovimentacaoEstoque.id_produto,
            func.sum(case((MovimentacaoEstoque.tipo == 'Entrada', MovimentacaoEstoque.quantidade), (MovimentacaoEstoque.tipo == 'Saida', -MovimentacaoEstoque.quantidade))).label('saldo')
        ).group_by(MovimentacaoEstoque.id_produto).subquery()
        
        valor_total = db.session.query(func.sum(Produto.preco * subquery.c.saldo)).join(subquery, Produto.id_produto == subquery.c.id_produto).scalar() or 0
        
        return jsonify({'total_produtos': total_prod, 'total_fornecedores': total_forn, 'valor_total_estoque': float(valor_total)}), 200
    except Exception as e: return jsonify({'erro': str(e)}), 500

@app.route('/api/relatorios/inventario', methods=['GET'])
@jwt_required()
def relatorio_inventario():
    # Simplificado para PDF/XLSX
    formato = request.args.get('formato', 'pdf')
    produtos = Produto.query.all()
    dados = []
    for p in produtos:
        dados.append({'codigo': p.codigo, 'nome': p.nome, 'saldo_atual': calcular_saldo_produto(p.id_produto), 'preco': p.preco})
    
    if formato == 'xlsx':
        df = pd.DataFrame(dados)
        df['total'] = df['saldo_atual'] * df['preco']
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        buffer.seek(0)
        return send_file(buffer, download_name='inventario.xlsx', as_attachment=True)
    
    # PDF simples (stub)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    doc.build([Paragraph("Inventário", getSampleStyleSheet()['h1'])])
    buffer.seek(0)
    return send_file(buffer, download_name='inventario.pdf', as_attachment=True)

@app.route('/api/relatorios/movimentacoes', methods=['GET'])
@jwt_required()
def relatorio_movimentacoes():
    formato = request.args.get('formato', 'json')
    q = MovimentacaoEstoque.query.order_by(MovimentacaoEstoque.data_hora.desc())
    res = []
    for m in q.all():
        res.append({
            'data_hora': m.data_hora.strftime('%d/%m/%Y'),
            'produto_codigo': m.produto.codigo if m.produto else '',
            'produto_nome': m.produto.nome if m.produto else '',
            'tipo': m.tipo,
            'quantidade': m.quantidade,
            'usuario_nome': m.usuario.nome if m.usuario else ''
        })
    if formato == 'json': return jsonify(res)
    # Excel/PDF stub
    return jsonify(res)

@app.route('/api/produtos/etiquetas', methods=['POST'])
@jwt_required()
def gerar_etiquetas():
    ids = request.get_json()['product_ids']
    # Stub de PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(62*mm, 100*mm))
    doc.build([Paragraph("Etiquetas", getSampleStyleSheet()['Normal'])])
    buffer.seek(0)
    return send_file(buffer, download_name='etiquetas.pdf', as_attachment=True)

@app.route('/api/versao', methods=['GET'])
def get_versao():
    try:
        with open('versao.json', 'r') as f: return jsonify(json.load(f))
    except: return jsonify({'versao': '1.0'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)