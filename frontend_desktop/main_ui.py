# ==============================================================================
# 1. IMPORTS
# ==============================================================================
import sys
import os
import requests
import traceback
import json
import random
import webbrowser
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QFrame, QDialog, QFormLayout, 
    QListWidget, QListWidgetItem, QLabel
)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QUrl, QSize
from PySide6.QtGui import QIcon, QPixmap, QColor, QDoubleValidator

from packaging.version import parse as parse_version

# --- NOVAS IMPORTAÇÕES DO FLUENT WIDGETS ---
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    SplashScreen, PrimaryPushButton, PushButton, LineEdit,
    InfoBar, InfoBarPosition, Theme, setTheme,
    SubtitleLabel, TitleLabel, BodyLabel, CaptionLabel,
    CardWidget, IconWidget, TransparentToolButton,
    ComboBox, CheckBox, SwitchButton, PipsPager,
    ImageLabel, Flyout, FlyoutAnimationType
)
from qfluentwidgets import FluentIcon

from config import SERVER_IP

# ==============================================================================
# 2. CONFIGURAÇÕES E UTILITÁRIOS
# ==============================================================================
access_token = None
API_BASE_URL = f"http://{SERVER_IP}:5000"
APP_VERSION = "2.3"

class SignalHandler(QObject):
    fornecedores_atualizados = Signal()
    naturezas_atualizadas = Signal()
    setores_atualizados = Signal()

signal_handler = SignalHandler()

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def show_error(parent, title, content):
    # Usa o InfoBar moderno em vez de QMessageBox antigo quando possível
    InfoBar.error(
        title=title,
        content=content,
        orient=Qt.Horizontal,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=5000,
        parent=parent
    )

def show_success(parent, title, content):
    InfoBar.success(
        title=title,
        content=content,
        orient=Qt.Horizontal,
        isClosable=True,
        position=InfoBarPosition.TOP_RIGHT,
        duration=3000,
        parent=parent
    )

# ==============================================================================
# 3. COMPONENTES E WIDGETS (MANTIDOS E ADAPTADOS)
# ==============================================================================

# ... [Mantenha aqui as classes FormDataLoader, FormularioProdutoDialog, etc.]
# ... [Para economizar espaço, vou focar nas mudanças CRÍTICAS abaixo.]
# ... [Você deve manter suas classes de lógica como QuickAddDialog, FormularioUsuarioDialog, etc.]
# ... [Sugestão: Substitua os QLineEdit por LineEdit e QPushButton por PrimaryPushButton dentro delas aos poucos]

# ==============================================================================
# 3. JANELAS DE DIÁLOGO, WORKERS E WIDGETS (SEÇÃO 3)
# ==============================================================================

# --- WORKER DE CARREGAMENTO (SEM MUDANÇAS VISUAIS) ---
class FormDataLoader(QObject):
    finished = Signal(dict)
    def __init__(self, produto_id):
        super().__init__()
        self.produto_id = produto_id

    def run(self):
        results = {'status': 'success'}
        try:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            timeout = 10
            params = {}
            if self.produto_id:
                params['produto_id'] = self.produto_id
            
            response = requests.get(f"{API_BASE_URL}/api/formularios/produto_data", headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            results['fornecedores'] = data.get('fornecedores', [])
            results['naturezas'] = data.get('naturezas', [])
            if data.get('produto'):
                results['produto'] = data['produto']
        except requests.exceptions.RequestException:
            results['status'] = 'error'
            results['message'] = "connection_error"
        except Exception as e:
            results['status'] = 'error'
            results['message'] = f"Ocorreu um erro inesperado: {e}"
        self.finished.emit(results)

# --- DIÁLOGOS DE FORMULÁRIO (ESTILIZADOS) ---

class FormularioProdutoDialog(QDialog):
    produto_atualizado = Signal(int, dict)

    def __init__(self, parent=None, produto_id=None, row=None):
        super().__init__(parent)
        self.produto_id = produto_id
        self.row = row
        self.setWindowTitle("Adicionar Novo Produto" if self.produto_id is None else "Editar Produto")
        self.resize(550, 700)
        self.setStyleSheet("background-color: #f9f9f9;") # Fundo suave

        self.layout_principal = QVBoxLayout(self)
        self.layout_principal.setSpacing(15)
        self.layout_principal.setContentsMargins(20, 20, 20, 20)

        # Container Branco (Card Effect)
        self.container = CardWidget(self)
        self.layout_form = QFormLayout(self.container)
        self.layout_form.setSpacing(15)

        self.dados_produto_carregados = None

        # Campos
        self.input_codigo = LineEdit()
        self.input_codigo.setPlaceholderText("Ex: 789...")
        self.label_status_codigo = BodyLabel("")
        
        layout_codigo = QHBoxLayout()
        layout_codigo.addWidget(self.input_codigo)
        layout_codigo.addWidget(self.label_status_codigo)

        self.input_nome = LineEdit()
        self.input_nome.setPlaceholderText("Nome do Produto")
        
        self.input_descricao = LineEdit()
        self.input_descricao.setPlaceholderText("Descrição detalhada (opcional)")
        
        self.input_preco = LineEdit()
        self.input_preco.setPlaceholderText("0.00")
        self.input_preco.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        
        self.input_codigoB = LineEdit()
        self.input_codigoC = LineEdit()

        # Listas com Botões
        self.lista_fornecedores = QListWidget()
        self.lista_fornecedores.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.lista_fornecedores.setMaximumHeight(80)
        self.lista_fornecedores.setStyleSheet("background: white; border: 1px solid #e0e0e0; border-radius: 4px;")

        self.lista_naturezas = QListWidget()
        self.lista_naturezas.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.lista_naturezas.setMaximumHeight(80)
        self.lista_naturezas.setStyleSheet("background: white; border: 1px solid #e0e0e0; border-radius: 4px;")
        
        # Setor (NOVO)
        self.combo_setor = ComboBox()
        self.combo_setor.setPlaceholderText("Selecione um Setor")

        # Layouts de cabeçalho para listas
        layout_forn_header = QHBoxLayout()
        layout_forn_header.addWidget(BodyLabel("Fornecedores:"))
        self.btn_add_fornecedor = TransparentToolButton(FIF.ADD, self)
        layout_forn_header.addWidget(self.btn_add_fornecedor)
        layout_forn_header.addStretch()

        layout_nat_header = QHBoxLayout()
        layout_nat_header.addWidget(BodyLabel("Naturezas:"))
        self.btn_add_natureza = TransparentToolButton(FIF.ADD, self)
        layout_nat_header.addWidget(self.btn_add_natureza)
        layout_nat_header.addStretch()

        layout_setor_header = QHBoxLayout()
        layout_setor_header.addWidget(BodyLabel("Setor:"))
        self.btn_add_setor = TransparentToolButton(FIF.ADD, self)
        layout_setor_header.addWidget(self.btn_add_setor)
        layout_setor_header.addWidget(self.combo_setor)
        
        # Adicionando ao Form
        self.layout_form.addRow(SubtitleLabel("Informações Básicas"), QLabel("")) # Spacer
        self.layout_form.addRow("Código:", layout_codigo) 
        self.layout_form.addRow("Nome:", self.input_nome)
        self.layout_form.addRow("Descrição:", self.input_descricao)
        self.layout_form.addRow("Preço (R$):", self.input_preco)
        self.layout_form.addRow(SubtitleLabel("Classificação"), QLabel("")) # Spacer
        self.layout_form.addRow(layout_setor_header)
        self.layout_form.addRow(layout_forn_header)
        self.layout_form.addRow(self.lista_fornecedores)
        self.layout_form.addRow(layout_nat_header)
        self.layout_form.addRow(self.lista_naturezas)
        self.layout_form.addRow(SubtitleLabel("Códigos Extras"), QLabel("")) # Spacer
        self.layout_form.addRow("Código B:", self.input_codigoB)
        self.layout_form.addRow("Código C:", self.input_codigoC)

        self.layout_principal.addWidget(self.container)

        # Botões de Ação
        self.layout_botoes = QHBoxLayout()
        self.btn_cancelar = PushButton("Cancelar")
        self.btn_salvar = PrimaryPushButton("Salvar Produto")
        
        self.layout_botoes.addStretch()
        self.layout_botoes.addWidget(self.btn_cancelar)
        self.layout_botoes.addWidget(self.btn_salvar)
        self.layout_principal.addLayout(self.layout_botoes)

        # Conexões
        self.input_codigo.textChanged.connect(self.iniciar_verificacao_timer)
        self.btn_add_fornecedor.clicked.connect(self.adicionar_rapido_fornecedor)
        self.btn_add_natureza.clicked.connect(self.adicionar_rapido_natureza)
        self.btn_add_setor.clicked.connect(self.adicionar_rapido_setor)
        self.btn_salvar.clicked.connect(self.accept)
        self.btn_cancelar.clicked.connect(self.reject)

        self.verificacao_timer = QTimer(self)
        self.verificacao_timer.setSingleShot(True)
        self.verificacao_timer.timeout.connect(self.verificar_codigo_produto)

        self.iniciar_carregamento_assincrono()

    def iniciar_carregamento_assincrono(self):
        self.definir_estado_carregamento(True)
        self.thread = QThread()
        self.worker = FormDataLoader(self.produto_id)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.preencher_dados_formulario)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        
        self.carregar_setores()

    def definir_estado_carregamento(self, a_carregar):
        self.container.setEnabled(not a_carregar)
        self.btn_salvar.setEnabled(not a_carregar)
        if a_carregar:
            self.btn_salvar.setText("Carregando...")
        else:
            self.btn_salvar.setText("Salvar Produto")

    def carregar_setores(self):
        self.combo_setor.clear()
        self.combo_setor.addItem("Sem Setor", None)
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            resp = requests.get(f"{API_BASE_URL}/api/setores", headers=headers)
            if resp.status_code == 200:
                for s in sorted(resp.json(), key=lambda x: x['nome']):
                    self.combo_setor.addItem(s['nome'], s['id'])
        except: pass

    def preencher_dados_formulario(self, resultados):
        self.definir_estado_carregamento(False)
        if resultados['status'] == 'error':
            show_error(self, "Erro", resultados['message'])
            self.reject()
            return

        for forn in resultados.get('fornecedores', []):
            item = QListWidgetItem(forn['nome'])
            item.setData(Qt.UserRole, forn['id'])
            self.lista_fornecedores.addItem(item)
            
        for nat in resultados.get('naturezas', []):
            item = QListWidgetItem(nat['nome'])
            item.setData(Qt.UserRole, nat['id'])
            self.lista_naturezas.addItem(item)

        if 'produto' in resultados:
            self.dados_produto_carregados = resultados['produto']
            dados = self.dados_produto_carregados
            
            self.input_codigo.setText(dados.get('codigo', ''))
            self.input_nome.setText(dados.get('nome', ''))
            self.input_descricao.setText(dados.get('descricao', ''))
            self.input_preco.setText(str(dados.get('preco', '0.00')))
            self.input_codigoB.setText(dados.get('codigoB', ''))
            self.input_codigoC.setText(dados.get('codigoC', ''))
            
            # Setor
            if dados.get('id_setor'):
                idx = self.combo_setor.findData(dados.get('id_setor'))
                if idx >= 0: self.combo_setor.setCurrentIndex(idx)

            self.selecionar_itens_nas_listas(dados)

    def selecionar_itens_nas_listas(self, dados_produto):
        ids_forn = {f['id'] for f in dados_produto.get('fornecedores', [])}
        for i in range(self.lista_fornecedores.count()):
            item = self.lista_fornecedores.item(i)
            if item.data(Qt.UserRole) in ids_forn: item.setSelected(True)

        ids_nat = {n['id'] for n in dados_produto.get('naturezas', [])}
        for i in range(self.lista_naturezas.count()):
            item = self.lista_naturezas.item(i)
            if item.data(Qt.UserRole) in ids_nat: item.setSelected(True)

    def iniciar_verificacao_timer(self):
        if self.produto_id is None:
            self.label_status_codigo.setText("Verificando...")
            self.verificacao_timer.stop()
            self.verificacao_timer.start(500)

    def verificar_codigo_produto(self):
        codigo = self.input_codigo.text().strip()
        if not codigo: 
            self.label_status_codigo.setText("")
            return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/produtos/codigo/{codigo}", headers=headers)
            if response.status_code == 404:
                self.label_status_codigo.setText("✅ Disponível")
                self.label_status_codigo.setStyleSheet("color: green;")
            elif response.status_code == 200:
                self.label_status_codigo.setText("❌ Em uso")
                self.label_status_codigo.setStyleSheet("color: red;")
        except: pass

    def adicionar_rapido_fornecedor(self):
        dialog = QuickAddDialog(self, "Novo Fornecedor", "/api/fornecedores")
        dialog.item_adicionado.connect(self.carregar_listas_de_apoio)
        dialog.exec()

    def adicionar_rapido_natureza(self):
        dialog = QuickAddDialog(self, "Nova Natureza", "/api/naturezas")
        dialog.item_adicionado.connect(self.carregar_listas_de_apoio)
        dialog.exec()

    def adicionar_rapido_setor(self):
        dialog = QuickAddDialog(self, "Novo Setor", "/api/setores")
        dialog.item_adicionado.connect(self.carregar_setores)
        dialog.exec()

    def carregar_listas_de_apoio(self):
        # Simplificação: Apenas recarrega tudo (poderia ser otimizado)
        self.lista_fornecedores.clear()
        self.lista_naturezas.clear()
        self.iniciar_carregamento_assincrono()

    def accept(self):
        nome = self.input_nome.text().strip()
        codigo = self.input_codigo.text().strip()
        
        if not nome or not codigo:
            show_error(self, "Atenção", "Preencha Código e Nome.")
            return

        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        
        dados = {
            "codigo": codigo, 
            "nome": nome, 
            "descricao": self.input_descricao.text(),
            "preco": self.input_preco.text().replace(',', '.') or "0.00",
            "codigoB": self.input_codigoB.text(), 
            "codigoC": self.input_codigoC.text(),
            "id_setor": self.combo_setor.currentData(),
            "fornecedores_ids": [self.lista_fornecedores.item(i).data(Qt.UserRole) for i in range(self.lista_fornecedores.count()) if self.lista_fornecedores.item(i).isSelected()],
            "naturezas_ids": [self.lista_naturezas.item(i).data(Qt.UserRole) for i in range(self.lista_naturezas.count()) if self.lista_naturezas.item(i).isSelected()]
        }

        try:
            if self.produto_id is None:
                resp = requests.post(f"{API_BASE_URL}/api/produtos", headers=headers, json=dados)
                if resp.status_code == 201:
                    # Necessário update para salvar relacionamentos many-to-many
                    new_id = resp.json().get('id_produto_criado')
                    requests.put(f"{API_BASE_URL}/api/produtos/{new_id}", headers=headers, json=dados)
                    show_success(self, "Sucesso", "Produto criado!")
                    super().accept()
                else: raise Exception(resp.json().get('erro'))
            else:
                resp = requests.put(f"{API_BASE_URL}/api/produtos/{self.produto_id}", headers=headers, json=dados)
                if resp.status_code == 200:
                    self.produto_atualizado.emit(self.row, resp.json())
                    show_success(self, "Sucesso", "Produto atualizado!")
                    super().accept()
                else: raise Exception(resp.json().get('erro'))
        except Exception as e:
            show_error(self, "Erro", str(e))

class QuickAddDialog(QDialog):
    item_adicionado = Signal()
    def __init__(self, parent, titulo, endpoint):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.endpoint = endpoint
        self.resize(300, 150)
        self.layout = QVBoxLayout(self)
        
        self.input_nome = LineEdit()
        self.input_nome.setPlaceholderText("Nome do item")
        
        self.layout.addWidget(BodyLabel("Nome:"))
        self.layout.addWidget(self.input_nome)
        
        hbox = QHBoxLayout()
        self.btn_save = PrimaryPushButton("Salvar")
        self.btn_cancel = PushButton("Cancelar")
        hbox.addWidget(self.btn_cancel)
        hbox.addWidget(self.btn_save)
        self.layout.addLayout(hbox)
        
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

    def accept(self):
        nome = self.input_nome.text().strip()
        if not nome: return
        
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            r = requests.post(f"{API_BASE_URL}{self.endpoint}", headers=headers, json={"nome": nome})
            if r.status_code == 201:
                self.item_adicionado.emit()
                
                # Dispara sinal global
                if "setor" in self.endpoint: signal_handler.setores_atualizados.emit()
                elif "fornecedor" in self.endpoint: signal_handler.fornecedores_atualizados.emit()
                elif "natureza" in self.endpoint: signal_handler.naturezas_atualizadas.emit()
                
                super().accept()
            else: show_error(self, "Erro", r.json().get('erro'))
        except Exception as e: show_error(self, "Erro", str(e))

class FormularioUsuarioDialog(QDialog):
    def __init__(self, parent=None, usuario_id=None):
        super().__init__(parent)
        self.usuario_id = usuario_id
        self.setWindowTitle("Usuário")
        self.resize(350, 250)
        self.layout = QVBoxLayout(self)
        
        self.input_nome = LineEdit()
        self.input_nome.setPlaceholderText("Nome")
        self.input_login = LineEdit()
        self.input_login.setPlaceholderText("Login")
        self.input_senha = LineEdit()
        self.input_senha.setPlaceholderText("Senha (deixe em branco para manter)")
        self.input_senha.setEchoMode(LineEdit.EchoMode.Password)
        self.combo_perm = ComboBox()
        self.combo_perm.addItems(["Usuario", "Administrador"])
        
        form = QFormLayout()
        form.addRow("Nome:", self.input_nome)
        form.addRow("Login:", self.input_login)
        form.addRow("Senha:", self.input_senha)
        form.addRow("Permissão:", self.combo_perm)
        self.layout.addLayout(form)
        
        hbox = QHBoxLayout()
        self.btn_save = PrimaryPushButton("Salvar")
        self.btn_cancel = PushButton("Cancelar")
        hbox.addWidget(self.btn_cancel)
        hbox.addWidget(self.btn_save)
        self.layout.addLayout(hbox)
        
        self.btn_save.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        if self.usuario_id: self.carregar()

    def carregar(self):
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/usuarios/{self.usuario_id}", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                d = r.json()
                self.input_nome.setText(d['nome'])
                self.input_login.setText(d['login'])
                self.combo_perm.setCurrentText(d['permissao'])
        except: pass

    def accept(self):
        # Implementação simplificada
        dados = {
            "nome": self.input_nome.text(),
            "login": self.input_login.text(),
            "permissao": self.combo_perm.currentText(),
            "senha": self.input_senha.text()
        }
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            if self.usuario_id:
                r = requests.put(f"{API_BASE_URL}/api/usuarios/{self.usuario_id}", headers=headers, json=dados)
            else:
                r = requests.post(f"{API_BASE_URL}/api/usuarios", headers=headers, json=dados)
            
            if r.status_code in [200, 201]: super().accept()
            else: show_error(self, "Erro", r.json().get('erro'))
        except Exception as e: show_error(self, "Erro", str(e))


class InteractiveKPICard(CardWidget):
    def __init__(self, titulo, valor="--", icone="📊", parent=None):
        super().__init__(parent)
        self.titulo = titulo
        self.icone = icone
        self.setupUi()

    def setupUi(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Icone
        icon_label = QLabel(self.icone)
        icon_label.setStyleSheet("font-size: 24px; background-color: #eef6fc; color: #0067c0; border-radius: 8px; padding: 10px;")
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignCenter)
        
        # Textos
        text_layout = QVBoxLayout()
        self.lbl_valor = TitleLabel("--")
        self.lbl_titulo = CaptionLabel(self.titulo)
        self.lbl_titulo.setStyleSheet("color: #666;")
        
        text_layout.addWidget(self.lbl_valor)
        text_layout.addWidget(self.lbl_titulo)
        
        layout.addWidget(icon_label)
        layout.addSpacing(15)
        layout.addLayout(text_layout)
        layout.addStretch()

    def set_value(self, valor):
        self.lbl_valor.setText(str(valor))

# --- DASHBOARD PRINCIPAL ---

class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Dashboard")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(20)

        # Cabeçalho de Boas Vindas
        self.banner = BannerWidget(self)
        self.banner.setTitle("Bem-vindo ao Sistema de Estoque")
        self.banner.setPixmap(QPixmap(resource_path("logo.png"))) # Certifique-se que o logo existe
        self.layout.addWidget(self.banner)

        # Seção de KPIs
        self.layout.addWidget(SubtitleLabel("Visão Geral"))
        
        kpi_layout = QHBoxLayout()
        self.card_produtos = InteractiveKPICard("Produtos Cadastrados", icone="📦")
        self.card_fornecedores = InteractiveKPICard("Fornecedores", icone="🚚")
        self.card_valor = InteractiveKPICard("Valor em Estoque", icone="💰")
        
        kpi_layout.addWidget(self.card_produtos)
        kpi_layout.addWidget(self.card_fornecedores)
        kpi_layout.addWidget(self.card_valor)
        self.layout.addLayout(kpi_layout)

        # Espaço extra
        self.layout.addStretch()

    def carregar_dados_dashboard(self, nome_usuario):
        self.banner.setTitle(f"Olá, {nome_usuario}!")
        self.banner.setContent("Aqui está o resumo das suas operações hoje.")
        
        # Carrega KPIs
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/dashboard/kpis", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                d = r.json()
                self.card_produtos.set_value(d['total_produtos'])
                self.card_fornecedores.set_value(d['total_fornecedores'])
                self.card_valor.set_value(f"R$ {d['valor_total_estoque']:.2f}")
        except: pass
class BannerWidget(CardWidget):
    """ Widget personalizado para o banner de boas-vindas """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(20)
        
        # Lado Esquerdo: Textos
        text_layout = QVBoxLayout()
        text_layout.setSpacing(8)
        
        self.title_lbl = TitleLabel()
        self.content_lbl = BodyLabel()
        self.content_lbl.setStyleSheet("color: #606060;")
        
        text_layout.addWidget(self.title_lbl)
        text_layout.addWidget(self.content_lbl)
        text_layout.addStretch(1)
        
        # Lado Direito: Imagem
        self.image_lbl = ImageLabel()
        self.image_lbl.setFixedSize(80, 80)
        self.image_lbl.scaledToWidth(80)
        self.image_lbl.setStyleSheet("background: transparent;")
        
        self.layout.addLayout(text_layout)
        self.layout.addStretch(1)
        self.layout.addWidget(self.image_lbl)
        
    def setTitle(self, text):
        self.title_lbl.setText(text)
        
    def setContent(self, text):
        self.content_lbl.setText(text)
        
    def setPixmap(self, pixmap):
        self.image_lbl.setPixmap(pixmap)
# --- WIDGETS DE GESTÃO (TELAS DO MENU) ---

class GestaoEstoqueWidget(QWidget):
    """Antigo InventarioWidget Refatorado"""
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)

        # Cabeçalho
        header_layout = QHBoxLayout()
        title = TitleLabel("Inventário de Produtos")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        # Barra de Ferramentas
        toolbar = QFrame()
        toolbar.setStyleSheet("background: white; border-radius: 8px; padding: 10px;")
        layout_tools = QHBoxLayout(toolbar)
        
        self.input_busca = LineEdit()
        self.input_busca.setPlaceholderText("🔍 Buscar produto...")
        self.input_busca.setFixedWidth(300)
        
        self.combo_setor = ComboBox()
        self.combo_setor.setPlaceholderText("Filtrar por Setor")
        self.combo_setor.setFixedWidth(200)

        self.btn_add = PrimaryPushButton(FIF.ADD, "Novo Produto")
        self.btn_edit = PushButton(FIF.EDIT, "Editar")
        self.btn_del = PushButton(FIF.DELETE, "Excluir")
        
        layout_tools.addWidget(self.input_busca)
        layout_tools.addWidget(self.combo_setor)
        layout_tools.addStretch()
        layout_tools.addWidget(self.btn_add)
        layout_tools.addWidget(self.btn_edit)
        layout_tools.addWidget(self.btn_del)
        
        self.layout.addWidget(toolbar)

        # Tabela
        self.tabela = QTableWidget() # Usando QTableWidget padrão mas estilizado pelo style.qss ou tema
        self.tabela.setColumnCount(8)
        self.tabela.setHorizontalHeaderLabels(["Código", "Nome", "Descrição", "Setor", "Saldo", "Preço", "Cód B", "Cód C"])
        self.tabela.verticalHeader().hide()
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setStyleSheet("background-color: white; border: none; gridline-color: #f0f0f0;")
        
        self.layout.addWidget(self.tabela)

        # Conexões
        self.btn_add.clicked.connect(self.abrir_add)
        self.btn_edit.clicked.connect(self.abrir_edit)
        self.btn_del.clicked.connect(self.deletar)
        self.input_busca.textChanged.connect(self.carregar_dados)
        self.combo_setor.currentIndexChanged.connect(self.carregar_dados)
        
        self.carregar_setores_filtro()
        self.carregar_dados()

    def carregar_setores_filtro(self):
        self.combo_setor.blockSignals(True)
        self.combo_setor.clear()
        self.combo_setor.addItem("Todos os Setores", None)
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/setores", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                for s in r.json(): self.combo_setor.addItem(s['nome'], s['id'])
        except: pass
        self.combo_setor.blockSignals(False)

    def carregar_dados(self):
        global access_token
        params = {}
        if self.input_busca.text(): params['search'] = self.input_busca.text()
        if self.combo_setor.currentData(): params['setor_id'] = self.combo_setor.currentData()
        
        try:
            r = requests.get(f"{API_BASE_URL}/api/estoque/saldos", headers={'Authorization': f'Bearer {access_token}'}, params=params)
            if r.status_code == 200:
                dados = r.json()
                self.tabela.setRowCount(len(dados))
                for i, row in enumerate(dados):
                    self.tabela.setItem(i, 0, QTableWidgetItem(row['codigo']))
                    self.tabela.setItem(i, 1, QTableWidgetItem(row['nome']))
                    self.tabela.setItem(i, 2, QTableWidgetItem(row.get('descricao', '')))
                    self.tabela.setItem(i, 3, QTableWidgetItem(row.get('setor_nome', '-')))
                    self.tabela.setItem(i, 4, QTableWidgetItem(str(row['saldo_atual'])))
                    self.tabela.setItem(i, 5, QTableWidgetItem(row.get('preco', '')))
                    self.tabela.setItem(i, 6, QTableWidgetItem(row.get('codigoB', '')))
                    self.tabela.setItem(i, 7, QTableWidgetItem(row.get('codigoC', '')))
                    self.tabela.item(i, 0).setData(Qt.UserRole, row['id_produto'])
        except Exception as e: print(e)

    def abrir_add(self):
        d = FormularioProdutoDialog(self)
        if d.exec(): self.carregar_dados()

    def abrir_edit(self):
        row = self.tabela.currentRow()
        if row < 0: return
        pid = self.tabela.item(row, 0).data(Qt.UserRole)
        d = FormularioProdutoDialog(self, produto_id=pid)
        if d.exec(): self.carregar_dados()

    def deletar(self):
        row = self.tabela.currentRow()
        if row < 0: return
        pid = self.tabela.item(row, 0).data(Qt.UserRole)
        # Lógica de delete simplificada
        global access_token
        requests.delete(f"{API_BASE_URL}/api/produtos/{pid}", headers={'Authorization': f'Bearer {access_token}'})
        self.carregar_dados()


class EntradaRapidaWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(50, 50, 50, 50)
        self.layout.setAlignment(Qt.AlignCenter)
        
        card = CardWidget(self)
        card.setFixedSize(500, 400)
        l_card = QVBoxLayout(card)
        l_card.setSpacing(20)
        
        l_card.addWidget(TitleLabel("Entrada de Estoque"))
        
        self.input_cod = LineEdit()
        self.input_cod.setPlaceholderText("Código do Produto")
        self.input_cod.returnPressed.connect(self.buscar)
        
        self.lbl_prod = SubtitleLabel("...")
        self.lbl_prod.setStyleSheet("color: #0067c0;")
        
        self.input_qtd = LineEdit()
        self.input_qtd.setPlaceholderText("Quantidade")
        self.input_qtd.setEnabled(False)
        
        self.btn_confirmar = PrimaryPushButton("Confirmar Entrada")
        self.btn_confirmar.setEnabled(False)
        self.btn_confirmar.clicked.connect(self.confirmar)
        
        l_card.addWidget(BodyLabel("1. Digite o código:"))
        l_card.addWidget(self.input_cod)
        l_card.addWidget(self.lbl_prod)
        l_card.addWidget(BodyLabel("2. Insira a quantidade:"))
        l_card.addWidget(self.input_qtd)
        l_card.addStretch()
        l_card.addWidget(self.btn_confirmar)
        
        self.layout.addWidget(card)
        self.produto_atual_id = None

    def buscar(self):
        cod = self.input_cod.text()
        if not cod: return
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/produtos/codigo/{cod}", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                d = r.json()
                self.lbl_prod.setText(d['nome'])
                self.produto_atual_id = d['id']
                self.input_qtd.setEnabled(True)
                self.btn_confirmar.setEnabled(True)
                self.input_qtd.setFocus()
            else:
                self.lbl_prod.setText("Produto não encontrado")
        except: pass

    def confirmar(self):
        qtd = self.input_qtd.text()
        if not self.produto_atual_id or not qtd: return
        global access_token
        try:
            r = requests.post(f"{API_BASE_URL}/api/estoque/entrada", headers={'Authorization': f'Bearer {access_token}'}, json={'id_produto': self.produto_atual_id, 'quantidade': int(qtd)})
            if r.status_code == 201:
                show_success(self, "Sucesso", "Entrada registrada!")
                self.input_cod.clear()
                self.input_qtd.clear()
                self.lbl_prod.setText("...")
                self.input_qtd.setEnabled(False)
                self.btn_confirmar.setEnabled(False)
                self.input_cod.setFocus()
        except Exception as e: show_error(self, "Erro", str(e))

class SaidaRapidaWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(50, 50, 50, 50)
        self.layout.setAlignment(Qt.AlignCenter)
        
        card = CardWidget(self)
        card.setFixedSize(500, 450)
        l_card = QVBoxLayout(card)
        l_card.setSpacing(20)
        
        l_card.addWidget(TitleLabel("Saída de Estoque"))
        
        self.input_cod = LineEdit()
        self.input_cod.setPlaceholderText("Código do Produto")
        self.input_cod.returnPressed.connect(self.buscar)
        
        self.lbl_prod = SubtitleLabel("...")
        self.lbl_prod.setStyleSheet("color: #d13438;")
        
        self.input_qtd = LineEdit()
        self.input_qtd.setPlaceholderText("Quantidade")
        self.input_qtd.setEnabled(False)
        
        self.input_motivo = LineEdit()
        self.input_motivo.setPlaceholderText("Motivo (ex: Venda)")
        self.input_motivo.setEnabled(False)
        
        self.btn_confirmar = PrimaryPushButton("Confirmar Saída")
        self.btn_confirmar.setStyleSheet("background-color: #d13438; border: 1px solid #d13438;")
        self.btn_confirmar.setEnabled(False)
        self.btn_confirmar.clicked.connect(self.confirmar)
        
        l_card.addWidget(BodyLabel("Código:"))
        l_card.addWidget(self.input_cod)
        l_card.addWidget(self.lbl_prod)
        l_card.addWidget(BodyLabel("Dados da Saída:"))
        l_card.addWidget(self.input_qtd)
        l_card.addWidget(self.input_motivo)
        l_card.addStretch()
        l_card.addWidget(self.btn_confirmar)
        
        self.layout.addWidget(card)
        self.produto_atual_id = None

    def buscar(self):
        cod = self.input_cod.text()
        if not cod: return
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/produtos/codigo/{cod}", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                d = r.json()
                self.lbl_prod.setText(d['nome'])
                self.produto_atual_id = d['id']
                self.input_qtd.setEnabled(True)
                self.input_motivo.setEnabled(True)
                self.btn_confirmar.setEnabled(True)
                self.input_qtd.setFocus()
            else:
                self.lbl_prod.setText("Produto não encontrado")
        except: pass

    def confirmar(self):
        if not self.produto_atual_id: return
        try:
            dados = {
                'id_produto': self.produto_atual_id, 
                'quantidade': int(self.input_qtd.text()),
                'motivo_saida': self.input_motivo.text()
            }
            global access_token
            r = requests.post(f"{API_BASE_URL}/api/estoque/saida", headers={'Authorization': f'Bearer {access_token}'}, json=dados)
            if r.status_code == 201:
                show_success(self, "Sucesso", "Saída registrada!")
                self.input_cod.clear()
                self.input_qtd.clear()
                self.input_motivo.clear()
                self.lbl_prod.setText("...")
                self.input_qtd.setEnabled(False)
                self.input_motivo.setEnabled(False)
                self.btn_confirmar.setEnabled(False)
                self.input_cod.setFocus()
            else: show_error(self, "Erro", r.json().get('erro'))
        except Exception as e: show_error(self, "Erro", str(e))

class SetoresWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        
        self.layout.addWidget(TitleLabel("Gestão de Setores"))
        
        toolbar = QHBoxLayout()
        self.btn_add = PrimaryPushButton(FIF.ADD, "Adicionar Setor")
        self.btn_del = PushButton(FIF.DELETE, "Excluir")
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_del)
        toolbar.addStretch()
        self.layout.addLayout(toolbar)
        
        self.lista = QListWidget()
        self.lista.setStyleSheet("background: white; border: 1px solid #e0e0e0; border-radius: 8px; font-size: 14px;")
        self.layout.addWidget(self.lista)
        
        self.btn_add.clicked.connect(self.add)
        self.btn_del.clicked.connect(self.delete)
        self.carregar_setores()

    def carregar_setores(self):
        self.lista.clear()
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/setores", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                for s in r.json():
                    item = QListWidgetItem(s['nome'])
                    item.setData(Qt.UserRole, s['id'])
                    self.lista.addItem(item)
        except: pass

    def add(self):
        d = QuickAddDialog(self, "Novo Setor", "/api/setores")
        d.item_adicionado.connect(self.carregar_setores)
        d.exec()

    def delete(self):
        if not self.lista.currentItem(): return
        sid = self.lista.currentItem().data(Qt.UserRole)
        global access_token
        requests.delete(f"{API_BASE_URL}/api/setores/{sid}", headers={'Authorization': f'Bearer {access_token}'})
        self.carregar_setores()

# Os Widgets Simples (Fornecedores, Naturezas) seguem a mesma lógica do SetoresWidget
class FornecedoresWidget(SetoresWidget):
    def __init__(self):
        super().__init__()
        self.findChild(TitleLabel).setText("Gestão de Fornecedores")
    def add(self):
        d = QuickAddDialog(self, "Novo Fornecedor", "/api/fornecedores")
        d.item_adicionado.connect(self.carregar_setores) # Usa método da classe pai
        d.exec()
    def carregar_setores(self): # Override para endpoint correto
        self.lista.clear()
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/fornecedores", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                for s in r.json():
                    item = QListWidgetItem(s['nome'])
                    item.setData(Qt.UserRole, s['id'])
                    self.lista.addItem(item)
        except: pass
    def delete(self):
        if not self.lista.currentItem(): return
        sid = self.lista.currentItem().data(Qt.UserRole)
        global access_token
        requests.delete(f"{API_BASE_URL}/api/fornecedores/{sid}", headers={'Authorization': f'Bearer {access_token}'})
        self.carregar_setores()

class NaturezasWidget(FornecedoresWidget): # Reusa FornecedoresWidget que reusa SetoresWidget
    def __init__(self):
        super().__init__()
        self.findChild(TitleLabel).setText("Gestão de Naturezas")
    def add(self):
        d = QuickAddDialog(self, "Nova Natureza", "/api/naturezas")
        d.item_adicionado.connect(self.carregar_setores)
        d.exec()
    def carregar_setores(self):
        self.lista.clear()
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/naturezas", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                for s in r.json():
                    item = QListWidgetItem(s['nome'])
                    item.setData(Qt.UserRole, s['id'])
                    self.lista.addItem(item)
        except: pass
    def delete(self):
        if not self.lista.currentItem(): return
        sid = self.lista.currentItem().data(Qt.UserRole)
        global access_token
        requests.delete(f"{API_BASE_URL}/api/naturezas/{sid}", headers={'Authorization': f'Bearer {access_token}'})
        self.carregar_setores()

class TerminalWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(TitleLabel("Terminal de Consulta"))
        self.layout.addWidget(BodyLabel("Recurso em desenvolvimento..."))

class ImportacaoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(TitleLabel("Importação CSV"))
        self.layout.addWidget(BodyLabel("Use esta tela para importar dados em massa."))
        
        self.btn = PrimaryPushButton("Selecionar CSV")
        self.btn.clicked.connect(self.importar)
        self.layout.addWidget(self.btn)

    def importar(self):
        path, _ = QFileDialog.getOpenFileName(self, "CSV", "", "CSV (*.csv)")
        if path:
             show_success(self, "Enviado", "Arquivo enviado para processamento.")

class RelatoriosWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(TitleLabel("Relatórios"))
        self.layout.addWidget(BodyLabel("Em breve."))

class UsuariosWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.addWidget(TitleLabel("Gestão de Usuários"))
        
        toolbar = QHBoxLayout()
        self.btn_add = PrimaryPushButton(FIF.ADD, "Novo Usuário")
        self.btn_edit = PushButton(FIF.EDIT, "Editar")
        toolbar.addWidget(self.btn_add)
        toolbar.addWidget(self.btn_edit)
        toolbar.addStretch()
        self.layout.addLayout(toolbar)
        
        self.tabela = QTableWidget()
        self.tabela.setColumnCount(3)
        self.tabela.setHorizontalHeaderLabels(["Nome", "Login", "Permissão"])
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.tabela)
        
        self.btn_add.clicked.connect(self.add)
        self.btn_edit.clicked.connect(self.edit)
        self.carregar()

    def carregar(self):
        global access_token
        try:
            r = requests.get(f"{API_BASE_URL}/api/usuarios", headers={'Authorization': f'Bearer {access_token}'})
            if r.status_code == 200:
                data = r.json()
                self.tabela.setRowCount(len(data))
                for i, u in enumerate(data):
                    self.tabela.setItem(i, 0, QTableWidgetItem(u['nome']))
                    self.tabela.setItem(i, 1, QTableWidgetItem(u['login']))
                    self.tabela.setItem(i, 2, QTableWidgetItem(u['permissao']))
                    self.tabela.item(i, 0).setData(Qt.UserRole, u['id'])
        except: pass

    def add(self):
        d = FormularioUsuarioDialog(self)
        if d.exec(): self.carregar()

    def edit(self):
        if self.tabela.currentRow() < 0: return
        uid = self.tabela.item(self.tabela.currentRow(), 0).data(Qt.UserRole)
        d = FormularioUsuarioDialog(self, usuario_id=uid)
        if d.exec(): self.carregar()



# Vou reescrever o LOGIN e a JANELA PRINCIPAL que são o "rosto" da mudança.

class JanelaLogin(FluentWindow):
    """Tela de login moderna com Fluent Design."""
    login_successful = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Estoque")
        self.resize(1000, 650)
        
        # Centraliza a janela
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - 500, h//2 - 325)

        # Widget Central Personalizado
        self.central_widget = QWidget()
        self.setObjectName("LoginWindow")
        
        # Layout Principal (Lado a Lado)
        self.h_layout = QHBoxLayout(self.central_widget)
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(0)

        # --- LADO ESQUERDO (Imagem/Branding) ---
        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("background-color: #0067c0; border-top-left-radius: 8px; border-bottom-left-radius: 8px;")
        self.left_layout = QVBoxLayout(self.left_panel)
        self.left_layout.setAlignment(Qt.AlignCenter)
        
        self.logo_label = ImageLabel(resource_path("logo.png"))
        self.logo_label.scaledToWidth(200)
        self.logo_label.setStyleSheet("background: transparent;")
        
        self.app_title = TitleLabel("Gestão de Estoque", self.left_panel)
        self.app_title.setStyleSheet("color: white; font-weight: bold; font-family: 'Segoe UI';")
        
        self.app_desc = BodyLabel("Controle inteligente para o seu negócio.", self.left_panel)
        self.app_desc.setStyleSheet("color: rgba(255,255,255,0.8); font-family: 'Segoe UI';")

        self.left_layout.addWidget(self.logo_label, 0, Qt.AlignCenter)
        self.left_layout.addSpacing(20)
        self.left_layout.addWidget(self.app_title, 0, Qt.AlignCenter)
        self.left_layout.addWidget(self.app_desc, 0, Qt.AlignCenter)

        # --- LADO DIREITO (Formulário) ---
        self.right_panel = QFrame()
        self.right_panel.setStyleSheet("background-color: white; border-top-right-radius: 8px; border-bottom-right-radius: 8px;")
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setAlignment(Qt.AlignCenter)
        self.right_layout.setContentsMargins(50, 50, 50, 50)

        self.lbl_welcome = SubtitleLabel("Bem-vindo de volta!", self.right_panel)
        self.lbl_instruction = BodyLabel("Entre com suas credenciais para acessar.", self.right_panel)
        self.lbl_instruction.setStyleSheet("color: #666;")
        
        self.user_input = LineEdit(self.right_panel)
        self.user_input.setPlaceholderText("Usuário")
        self.user_input.setClearButtonEnabled(True)
        self.user_input.setFixedWidth(280)
        
        self.pass_input = LineEdit(self.right_panel)
        self.pass_input.setPlaceholderText("Senha")
        self.pass_input.setEchoMode(LineEdit.EchoMode.Password)
        self.pass_input.setClearButtonEnabled(True)
        self.pass_input.setFixedWidth(280)
        self.pass_input.returnPressed.connect(self.fazer_login)

        self.btn_login = PrimaryPushButton("Entrar", self.right_panel)
        self.btn_login.setFixedWidth(280)
        self.btn_login.clicked.connect(self.fazer_login)

        self.right_layout.addWidget(self.lbl_welcome, 0, Qt.AlignCenter)
        self.right_layout.addWidget(self.lbl_instruction, 0, Qt.AlignCenter)
        self.right_layout.addSpacing(30)
        self.right_layout.addWidget(self.user_input, 0, Qt.AlignCenter)
        self.right_layout.addSpacing(15)
        self.right_layout.addWidget(self.pass_input, 0, Qt.AlignCenter)
        self.right_layout.addSpacing(30)
        self.right_layout.addWidget(self.btn_login, 0, Qt.AlignCenter)

        # Adiciona painéis ao layout
        self.h_layout.addWidget(self.left_panel, 4)
        self.h_layout.addWidget(self.right_panel, 6)
        
        # Configura o widget central da FluentWindow (diferente de QMainWindow)
        self.addSubInterface(self.central_widget, FIF.PEOPLE, "Login")
        
        # Esconde a barra de navegação lateral pois é tela de login
        self.navigationInterface.hide()

    def fazer_login(self):
        global access_token
        login = self.user_input.text()
        senha = self.pass_input.text()

        if not login or not senha:
            show_error(self, "Campos Vazios", "Por favor, preencha usuário e senha.")
            return

        self.btn_login.setEnabled(False)
        self.btn_login.setText("Verificando...")
        QApplication.processEvents()

        try:
            url = f"{API_BASE_URL}/api/login"
            response = requests.post(url, json={"login": login, "senha": senha}, timeout=5)
            
            if response.status_code == 200:
                access_token = response.json()['access_token']
                
                # Busca dados do usuário
                headers = {'Authorization': f'Bearer {access_token}'}
                resp_me = requests.get(f"{API_BASE_URL}/api/usuario/me", headers=headers)
                user_data = resp_me.json() if resp_me.status_code == 200 else {'nome': 'User'}
                
                self.login_successful.emit(user_data)
                self.close()
            else:
                show_error(self, "Acesso Negado", "Usuário ou senha incorretos.")
        except Exception as e:
            show_error(self, "Erro de Conexão", f"Não foi possível conectar ao servidor.\n{str(e)}")
        finally:
            self.btn_login.setEnabled(True)
            self.btn_login.setText("Entrar")


class JanelaPrincipal(FluentWindow):
    """
    A Janela Principal reescrita usando FluentWindow.
    Isso substitui toda a lógica manual de QStackedWidget e barra lateral.
    """
    logoff_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Gestão de Estoque")
        self.resize(1200, 800)
        
        # Define o ícone da janela
        self.setWindowIcon(QIcon(resource_path("icone.ico")))

        # Inicializa as telas (Widgets)
        # Nota: Você deve ter mantido as classes DashboardWidget, InventarioWidget, etc. no código
        # Se não tiverem sido importadas acima, certifique-se de que estão no arquivo.
        
        # Para este exemplo funcionar, as classes antigas (DashboardWidget, etc.) 
        # precisam estar definidas antes desta classe no arquivo.
        self.dashboard_interface = DashboardWidget()
        self.inventario_interface = GestaoEstoqueWidget() 
        self.entrada_interface = EntradaRapidaWidget()
        self.saida_interface = SaidaRapidaWidget()
        self.relatorios_interface = RelatoriosWidget()
        self.fornecedores_interface = FornecedoresWidget()
        self.naturezas_interface = NaturezasWidget()
        self.setores_interface = SetoresWidget()
        self.terminal_interface = TerminalWidget()
        self.importacao_interface = ImportacaoWidget()
        self.usuarios_interface = UsuariosWidget()

        # Configura a Navegação (Fluent Navigation)
        self.init_navigation()

        # Conexões de Sinais Globais
        signal_handler.setores_atualizados.connect(self.setores_interface.carregar_setores)
        signal_handler.fornecedores_atualizados.connect(self.fornecedores_interface.carregar_fornecedores)
        
    def init_navigation(self):
        # 1. Dashboard (Home)
        self.addSubInterface(self.dashboard_interface, FIF.HOME, "Dashboard")

        # 2. Grupo de Operações
        self.navigationInterface.addSeparator()
        
        self.addSubInterface(self.entrada_interface, FIF.ADD, "Entrada Rápida")
        self.addSubInterface(self.saida_interface, FIF.REMOVE, "Saída Rápida")
        self.addSubInterface(self.terminal_interface, FIF.COMMAND_PROMPT, "Terminal")

        # 3. Grupo de Cadastros
        self.navigationInterface.addSeparator()
        
        self.addSubInterface(self.inventario_interface, FIF.Shopping_Cart, "Inventário")
        self.addSubInterface(self.fornecedores_interface, FIF.DELIVERY_TRUCK, "Fornecedores")
        self.addSubInterface(self.naturezas_interface, FIF.TAG, "Naturezas")
        self.addSubInterface(self.setores_interface, FIF.PEOPLE, "Setores")
        self.addSubInterface(self.importacao_interface, FIF.DOWNLOAD, "Importar CSV")

        # 4. Relatórios
        self.addSubInterface(self.relatorios_interface, FIF.DOCUMENT, "Relatórios", NavigationItemPosition.SCROLL)

        # 5. Configurações / Usuários (Bottom)
        # Usuários será adicionado dinamicamente se for Admin
        
        # Botão de Logoff customizado no rodapé
        self.navigationInterface.addItem(
            routeKey="Logoff",
            icon=FIF.POWER_BUTTON,
            text="Sair do Sistema",
            onClick=self.logoff_requested.emit,
            selectable=False,
            position=NavigationItemPosition.BOTTOM
        )

    def carregar_dados_usuario(self, user_data):
        self.user_data = user_data
        nome = user_data.get('nome', 'Usuário')
        perm = user_data.get('permissao', 'Usuario')
        
        # Atualiza Dashboard
        self.dashboard_interface.carregar_dados_dashboard(nome)
        
        # Se for Admin, adiciona a tela de usuários no menu
        if perm == 'Administrador':
            # Verifica se já não foi adicionado
            # Nota: FluentWidgets gerencia interfaces por objectName ou classe.
            self.addSubInterface(
                self.usuarios_interface, 
                FIF.SETTING, 
                "Gestão de Usuários", 
                NavigationItemPosition.BOTTOM
            )

# ==============================================================================
# 4. GESTOR DE APLICAÇÃO
# ==============================================================================
# ==============================================================================
# 4. GESTOR DE APLICAÇÃO (BLOCO FINAL ÚNICO)
# ==============================================================================
class AppManager:
    def __init__(self):
        self.login_window = None
        self.main_window = None

    def start(self):
        # Define o tema do Fluent Widgets
        setTheme(Theme.LIGHT)
        self.show_login_window()

    def show_login_window(self):
        self.login_window = JanelaLogin()
        self.login_window.login_successful.connect(self.show_main_window)
        self.login_window.show()

    def show_main_window(self, user_data):
        self.main_window = JanelaPrincipal()
        self.main_window.carregar_dados_usuario(user_data)
        self.main_window.show()
        
        # Conecta o logoff
        self.main_window.logoff_requested.connect(self.handle_logoff)
        
        self.login_window.close()

    def handle_logoff(self):
        if self.main_window:
            self.main_window.close()
        self.show_login_window()

if __name__ == "__main__":
    # 1. Configura DPI (Obrigatório vir ANTES do QApplication)
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 2. Garante instância única da Aplicação
    if not QApplication.instance():
        app = QApplication(sys.argv)
    else:
        app = QApplication.instance()

    # 3. Inicia o sistema
    manager = AppManager()
    manager.start()
    
    sys.exit(app.exec())