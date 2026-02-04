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
import winsound
import threading

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QMessageBox, QMainWindow, QHBoxLayout, QStackedWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy, QDialog, QFormLayout,
    QDialogButtonBox, QListWidget, QListWidgetItem, QAbstractItemView,
    QComboBox, QFileDialog, QFrame, QDateEdit, QCalendarWidget, QMenu,
    QTextEdit, QGraphicsDropShadowEffect
)
from PySide6.QtGui import (
    QPixmap, QAction, QDoubleValidator, QKeySequence, QIcon, QColor
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QDate, QEvent, QObject, QThread, QUrl
)
from PySide6.QtMultimedia import QSoundEffect
from packaging.version import parse as parse_version

from config import SERVER_IP

# ==============================================================================
# 2. FUNÇÕES AUXILIARES E VARIÁVEIS GLOBAIS
# ==============================================================================
access_token = None
API_BASE_URL = f"http://{SERVER_IP}:5000"
APP_VERSION = "2.5.0"

class SignalHandler(QObject):
    """Um gestor central para sinais globais da aplicação."""
    fornecedores_atualizados = Signal()
    naturezas_atualizadas = Signal()
    setores_atualizados = Signal() # NOVO

signal_handler = SignalHandler()

def resource_path(relative_path):
    """ Retorna o caminho absoluto para o recurso, funcionando tanto no desenvolvimento quanto no .exe do PyInstaller. """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def show_connection_error_message(parent):
    """Exibe uma mensagem de erro de conexão padronizada e amigável."""
    QMessageBox.critical(parent,
        "Erro de Conexão",
        "Impossível conectar ao servidor.\n\n"
        "Por favor, verifique os seguintes pontos:\n"
        "1. O computador servidor está ligado e a aplicação está a ser executada.\n"
        "2. O seu computador tem uma ligação à rede (internet ou local).\n"
        "3. O endereço IP no ficheiro 'config.py' está correto."
    )

def check_for_updates():
    """Contacta a API para verificar se existe uma nova versão da aplicação."""
    print("A verificar atualizações...")
    try:
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(f"{API_BASE_URL}/api/versao", headers=headers, timeout=5)

        if response.status_code == 200:
            dados_versao = response.json()
            versao_servidor = dados_versao.get("versao")
            url_download = dados_versao.get("url_download")

            if versao_servidor and parse_version(versao_servidor) > parse_version(APP_VERSION):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Icon.Information)
                msg_box.setWindowTitle("Nova Versão Disponível!")
                msg_box.setText(f"Uma nova versão ({versao_servidor}) do sistema está disponível.")
                msg_box.setInformativeText("Deseja ir para a página de download agora?")
                msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
                
                ret = msg_box.exec()
                if ret == QMessageBox.StandardButton.Yes:
                    webbrowser.open(url_download)
            else:
                print("A sua aplicação está atualizada.")
        else:
            print(f"Não foi possível verificar a versão. Erro da API: {response.status_code}")
            QMessageBox.warning(None, "Verificação de Versão", f"Não foi possível contactar o servidor de atualizações (Erro: {response.status_code}).")

    except requests.exceptions.RequestException:
        show_connection_error_message(None)
    except Exception as e:
        print(f"Ocorreu um erro ao verificar atualizações: {e}")
        QMessageBox.critical(None, "Erro na Verificação de Versão", f"Ocorreu um erro inesperado ao tentar verificar por novas versões:\n\n{e}")

# ==============================================================================
# 3. JANELAS DE DIÁLOGO E WORKERS
# ==============================================================================

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

class FormularioProdutoDialog(QDialog):
    produto_atualizado = Signal(int, dict)

    def __init__(self, parent=None, produto_id=None, row=None):
        super().__init__(parent)
        self.produto_id = produto_id
        self.row = row
        self.dados_produto_carregados = None
        
        # Configuração da Janela
        self.setWindowTitle("Editar Produto" if self.produto_id else "Adicionar Novo Produto")
        self.setMinimumSize(500, 650)
        
        # Inicialização
        self.setup_ui()
        self.connect_signals()
        self.iniciar_carregamento_assincrono()

    def setup_ui(self):
        """Constrói toda a interface gráfica do diálogo."""
        self.layout_principal = QVBoxLayout(self)

        # --- Grupo 1: Identificação Básica ---
        group_identificacao = QFrame()
        layout_ident = QFormLayout(group_identificacao)
        
        self.input_codigo = QLineEdit()
        self.input_codigo.setPlaceholderText("Ex: 789...")
        self.label_status_codigo = QLabel("")
        self.label_status_codigo.setFixedWidth(100)
        
        layout_codigo = QHBoxLayout()
        layout_codigo.addWidget(self.input_codigo)
        layout_codigo.addWidget(self.label_status_codigo)
        
        self.input_nome = QLineEdit()
        self.input_nome.setPlaceholderText("Nome do Produto")
        
        self.input_descricao = QLineEdit()
        self.input_descricao.setPlaceholderText("Descrição detalhada (opcional)")

        layout_ident.addRow("Código:*", layout_codigo)
        layout_ident.addRow("Nome:*", self.input_nome)
        layout_ident.addRow("Descrição:", self.input_descricao)
        
        self.layout_principal.addWidget(group_identificacao)

        # --- Grupo 2: Valores e Códigos Auxiliares ---
        group_detalhes = QFrame()
        layout_detalhes = QFormLayout(group_detalhes)

        self.input_preco = QLineEdit()
        self.input_preco.setValidator(QDoubleValidator(0.00, 999999.99, 2))
        self.input_preco.setPlaceholderText("0.00")
        
        self.input_codigoB = QLineEdit()
        self.input_codigoC = QLineEdit()

        layout_detalhes.addRow("Preço (R$):", self.input_preco)
        layout_detalhes.addRow("Código B:", self.input_codigoB)
        layout_detalhes.addRow("Código C:", self.input_codigoC)
        
        self.layout_principal.addWidget(group_detalhes)

        # --- Grupo 3: Classificação e Associações ---
        # Aqui entra a NOVIDADE: Setor
        group_classificacao = QFrame()
        layout_class = QVBoxLayout(group_classificacao)
        layout_class.setContentsMargins(0, 10, 0, 0)

        # Setor (ComboBox com botão adicionar)
        lbl_setor = QLabel("Setor:")
        layout_setor_combo = QHBoxLayout()
        self.combo_setor = QComboBox()
        self.btn_add_setor = QPushButton("+")
        self.btn_add_setor.setFixedSize(30, 25)
        self.btn_add_setor.setToolTip("Criar novo setor")
        layout_setor_combo.addWidget(self.combo_setor)
        layout_setor_combo.addWidget(self.btn_add_setor)

        # Fornecedores (Lista Multi-seleção)
        lbl_fornecedor = QLabel("Fornecedores:")
        layout_forn_header = QHBoxLayout()
        layout_forn_header.addWidget(lbl_fornecedor)
        self.btn_add_fornecedor = QPushButton("+")
        self.btn_add_fornecedor.setFixedSize(30, 25)
        self.btn_add_fornecedor.setToolTip("Criar novo fornecedor")
        layout_forn_header.addWidget(self.btn_add_fornecedor)
        layout_forn_header.addStretch()
        
        self.lista_fornecedores = QListWidget()
        self.lista_fornecedores.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.lista_fornecedores.setMaximumHeight(80)

        # Naturezas (Lista Multi-seleção)
        lbl_natureza = QLabel("Naturezas:")
        layout_nat_header = QHBoxLayout()
        layout_nat_header.addWidget(lbl_natureza)
        self.btn_add_natureza = QPushButton("+")
        self.btn_add_natureza.setFixedSize(30, 25)
        self.btn_add_natureza.setToolTip("Criar nova natureza")
        layout_nat_header.addWidget(self.btn_add_natureza)
        layout_nat_header.addStretch()

        self.lista_naturezas = QListWidget()
        self.lista_naturezas.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.lista_naturezas.setMaximumHeight(80)

        # Adicionando ao layout de classificação
        layout_class.addWidget(lbl_setor)
        layout_class.addLayout(layout_setor_combo)
        layout_class.addLayout(layout_forn_header)
        layout_class.addWidget(self.lista_fornecedores)
        layout_class.addLayout(layout_nat_header)
        layout_class.addWidget(self.lista_naturezas)
        
        self.layout_principal.addWidget(group_classificacao)

        # --- Botões de Ação ---
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.layout_principal.addWidget(self.botoes)

        # Timer para verificação de código
        self.verificacao_timer = QTimer(self)
        self.verificacao_timer.setSingleShot(True)

    def connect_signals(self):
        """Conecta todos os sinais e eventos dos widgets."""
        self.botoes.accepted.connect(self.save_product)
        self.botoes.rejected.connect(self.reject)
        
        # Atalhos de criação rápida
        self.btn_add_setor.clicked.connect(self.adicionar_rapido_setor)
        self.btn_add_fornecedor.clicked.connect(self.adicionar_rapido_fornecedor)
        self.btn_add_natureza.clicked.connect(self.adicionar_rapido_natureza)
        
        # Verificação de código
        self.input_codigo.textChanged.connect(self.iniciar_verificacao_timer)
        self.verificacao_timer.timeout.connect(self.verificar_codigo_produto)
        
        # Navegação com Enter
        self.input_codigo.returnPressed.connect(self.input_nome.setFocus)
        self.input_nome.returnPressed.connect(self.input_preco.setFocus)

    # --- Lógica de Carregamento de Dados ---

    def iniciar_carregamento_assincrono(self):
        self.definir_estado_carregamento(True)
        
        # Carrega dados básicos (Fornecedores/Naturezas) + Produto (se for edição)
        self.thread = QThread()
        self.worker = FormDataLoader(self.produto_id)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.preencher_dados_formulario)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        # Carrega Setores separadamente (pois é uma feature nova)
        self.carregar_setores()

    def definir_estado_carregamento(self, a_carregar):
        self.setEnabled(not a_carregar)
        if a_carregar:
            self.setWindowTitle("Carregando...")
        else:
            self.setWindowTitle("Editar Produto" if self.produto_id else "Adicionar Novo Produto")

    def carregar_setores(self):
        """Carrega a lista de setores da API."""
        self.combo_setor.clear()
        self.combo_setor.addItem("Selecione um Setor (Opcional)", None)
        
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            # Assume que a rota /api/setores já existe conforme instrução anterior
            response = requests.get(f"{API_BASE_URL}/api/setores", headers=headers)
            if response.status_code == 200:
                setores = sorted(response.json(), key=lambda x: x['nome'])
                for s in setores:
                    self.combo_setor.addItem(s['nome'], s['id'])
        except Exception as e:
            print(f"Erro ao carregar setores: {e}")

    def preencher_dados_formulario(self, resultados):
        """Distribui os dados recebidos da API nos campos."""
        self.definir_estado_carregamento(False)
        
        if resultados['status'] == 'error':
            QMessageBox.critical(self, "Erro", resultados['message'])
            self.reject()
            return

        # Popula Listas de Apoio
        for forn in resultados.get('fornecedores', []):
            item = QListWidgetItem(forn['nome'])
            item.setData(Qt.UserRole, forn['id'])
            self.lista_fornecedores.addItem(item)
            
        for nat in resultados.get('naturezas', []):
            item = QListWidgetItem(nat['nome'])
            item.setData(Qt.UserRole, nat['id'])
            self.lista_naturezas.addItem(item)

        # Se for edição, preenche os campos do produto
        if 'produto' in resultados:
            self.dados_produto_carregados = resultados['produto']
            dados = self.dados_produto_carregados
            
            self.input_codigo.setText(dados.get('codigo', ''))
            self.input_nome.setText(dados.get('nome', ''))
            self.input_descricao.setText(dados.get('descricao', ''))
            self.input_preco.setText(str(dados.get('preco', '0.00')))
            self.input_codigoB.setText(dados.get('codigoB', ''))
            self.input_codigoC.setText(dados.get('codigoC', ''))
            
            # Seleciona Setor
            id_setor = dados.get('id_setor')
            if id_setor:
                idx = self.combo_setor.findData(id_setor)
                if idx >= 0: self.combo_setor.setCurrentIndex(idx)

            # Seleciona Fornecedores e Naturezas
            self.selecionar_itens_lista(self.lista_fornecedores, dados.get('fornecedores', []))
            self.selecionar_itens_lista(self.lista_naturezas, dados.get('naturezas', []))

    def selecionar_itens_lista(self, lista_widget, itens_associados):
        """Helper para marcar itens como selecionados nas listas."""
        ids_associados = {item['id'] for item in itens_associados}
        for i in range(lista_widget.count()):
            item = lista_widget.item(i)
            if item.data(Qt.UserRole) in ids_associados:
                item.setSelected(True)

    # --- Lógica de Criação Rápida (Quick Add) ---

    def adicionar_rapido_setor(self):
        self._quick_add("Adicionar Novo Setor", "/api/setores", self.carregar_setores)

    def adicionar_rapido_fornecedor(self):
        self._quick_add("Adicionar Fornecedor", "/api/fornecedores", self.recargar_listas_apoio)

    def adicionar_rapido_natureza(self):
        self._quick_add("Adicionar Natureza", "/api/naturezas", self.recargar_listas_apoio)

    def _quick_add(self, titulo, endpoint, callback_sucesso):
        dialog = QuickAddDialog(self, titulo, endpoint)
        # Conecta o sinal apenas se o diálogo for aceito e emitir o evento
        dialog.item_adicionado.connect(callback_sucesso) 
        dialog.exec()

    def recargar_listas_apoio(self):
        """Recarrega as listas mantendo as seleções atuais se possível."""
        # Nota: Uma implementação ideal salvaria os IDs selecionados e restauraria.
        # Por simplicidade, estamos limpando e recarregando via worker ou requisição direta.
        self.lista_fornecedores.clear()
        self.lista_naturezas.clear()
        self.iniciar_carregamento_assincrono() # Reutiliza a lógica principal

    # --- Lógica de Validação e Salvamento ---

    def iniciar_verificacao_timer(self):
        if self.produto_id is None:
            self.label_status_codigo.setText("Verificando...")
            self.label_status_codigo.setStyleSheet("color: grey;")
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
        except:
            self.label_status_codigo.setText("⚠️ Erro")

    def save_product(self):
        nome = self.input_nome.text().strip()
        codigo = self.input_codigo.text().strip()
        
        if not nome or not codigo:
            QMessageBox.warning(self, "Atenção", "Os campos Código e Nome são obrigatórios.")
            return

        # Coleta de Dados
        dados_produto = {
            "codigo": codigo,
            "nome": nome,
            "descricao": self.input_descricao.text(),
            "preco": self.input_preco.text().replace(',', '.') or "0.00",
            "codigoB": self.input_codigoB.text(),
            "codigoC": self.input_codigoC.text(),
            "id_setor": self.combo_setor.currentData(), # Campo NOVO
            "fornecedores_ids": [item.data(Qt.UserRole) for item in self.lista_fornecedores.selectedItems()],
            "naturezas_ids": [item.data(Qt.UserRole) for item in self.lista_naturezas.selectedItems()]
        }

        # Envio para API
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            if self.produto_id is None:
                # Criar (POST)
                resp = requests.post(f"{API_BASE_URL}/api/produtos", headers=headers, json=dados_produto)
                if resp.status_code == 201:
                    # Se criou, precisamos atualizar as associações (para garantir many-to-many)
                    new_id = resp.json().get('id_produto_criado')
                    requests.put(f"{API_BASE_URL}/api/produtos/{new_id}", headers=headers, json=dados_produto)
                    QMessageBox.information(self, "Sucesso", "Produto criado com sucesso!")
                    super().accept()
                else:
                    raise Exception(resp.json().get('erro', 'Erro ao criar'))
            else:
                # Atualizar (PUT)
                resp = requests.put(f"{API_BASE_URL}/api/produtos/{self.produto_id}", headers=headers, json=dados_produto)
                if resp.status_code == 200:
                    self.produto_atualizado.emit(self.row, resp.json())
                    QMessageBox.information(self, "Sucesso", "Produto atualizado com sucesso!")
                    super().accept()
                else:
                    raise Exception(resp.json().get('erro', 'Erro ao atualizar'))
                    
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha na operação: {str(e)}")

class FormularioFornecedorDialog(QDialog):
    def __init__(self, parent=None, fornecedor_id=None):
        super().__init__(parent)
        self.fornecedor_id = fornecedor_id
        self.setWindowTitle("Adicionar Novo Fornecedor" if self.fornecedor_id is None else "Editar Fornecedor")
        self.layout = QFormLayout(self)
        self.input_nome = QLineEdit()
        self.layout.addRow("Nome:", self.input_nome)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.layout.addWidget(self.botoes)
        if self.fornecedor_id:
            self.carregar_dados_fornecedor()
    def carregar_dados_fornecedor(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/fornecedores/{self.fornecedor_id}", headers=headers)
            if response.status_code == 200:
                self.input_nome.setText(response.json().get('nome'))
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar dados do fornecedor.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def accept(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"nome": self.input_nome.text()}
        try:
            if self.fornecedor_id is None:
                response = requests.post(f"{API_BASE_URL}/api/fornecedores", headers=headers, json=dados)
                if response.status_code == 201:
                    QMessageBox.information(self, "Sucesso", "Fornecedor adicionado com sucesso!")
                    super().accept()
                else: raise Exception(response.json().get('erro', 'Erro desconhecido'))
            else:
                response = requests.put(f"{API_BASE_URL}/api/fornecedores/{self.fornecedor_id}", headers=headers, json=dados)
                if response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", "Fornecedor atualizado com sucesso!")
                    super().accept()
                else: raise Exception(response.json().get('erro', 'Erro desconhecido'))
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar o fornecedor: {e}")

class FormularioNaturezaDialog(QDialog):
    def __init__(self, parent=None, natureza_id=None):
        super().__init__(parent)
        self.natureza_id = natureza_id
        self.setWindowTitle("Adicionar Nova Natureza" if self.natureza_id is None else "Editar Natureza")
        self.layout = QFormLayout(self)
        self.input_nome = QLineEdit()
        self.layout.addRow("Nome:", self.input_nome)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.layout.addWidget(self.botoes)
        if self.natureza_id:
            self.carregar_dados_natureza()
    def carregar_dados_natureza(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/naturezas/{self.natureza_id}", headers=headers)
            if response.status_code == 200:
                self.input_nome.setText(response.json().get('nome'))
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar dados da natureza.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def accept(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"nome": self.input_nome.text()}
        try:
            if self.natureza_id is None:
                response = requests.post(f"{API_BASE_URL}/api/naturezas", headers=headers, json=dados)
                if response.status_code == 201:
                    QMessageBox.information(self, "Sucesso", "Natureza adicionada com sucesso!")
                    super().accept()
                else: raise Exception(response.json().get('erro', 'Erro desconhecido'))
            else:
                response = requests.put(f"{API_BASE_URL}/api/naturezas/{self.natureza_id}", headers=headers, json=dados)
                if response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", "Natureza atualizada com sucesso!")
                    super().accept()
                else: raise Exception(response.json().get('erro', 'Erro desconhecido'))
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar a natureza: {e}")

class QuickAddDialog(QDialog):
    item_adicionado = Signal()
    def __init__(self, parent, titulo, endpoint):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.endpoint = endpoint
        self.setMinimumWidth(300)
        self.layout = QVBoxLayout(self)
        self.form_layout = QFormLayout()
        self.input_nome = QLineEdit()
        self.form_layout.addRow("Nome:", self.input_nome)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.layout.addLayout(self.form_layout)
        self.layout.addWidget(self.botoes)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
    def accept(self):
        nome = self.input_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Erro", "O campo de nome não pode estar vazio.")
            return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"nome": nome}
        try:
            response = requests.post(f"{API_BASE_URL}{self.endpoint}", headers=headers, json=dados)
            if response.status_code == 201:
                QMessageBox.information(self, "Sucesso", "Item adicionado com sucesso!")
                self.item_adicionado.emit()
                if self.endpoint == "/api/fornecedores":
                    signal_handler.fornecedores_atualizados.emit()
                elif self.endpoint == "/api/naturezas":
                    signal_handler.naturezas_atualizadas.emit()
                elif self.endpoint == "/api/setores":  # <--- Adicione isto
                    signal_handler.setores_atualizados.emit()    
                super().accept()
            else:
                raise Exception(response.json().get('erro', 'Erro desconhecido'))
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar o item: {e}")

class FormularioUsuarioDialog(QDialog):
    def __init__(self, parent=None, usuario_id=None):
        super().__init__(parent)
        self.usuario_id = usuario_id
        self.setWindowTitle("Adicionar Novo Usuário" if self.usuario_id is None else "Editar Usuário")
        self.setMinimumWidth(350)
        self.layout = QFormLayout(self)
        self.input_nome = QLineEdit()
        self.input_login = QLineEdit()
        self.input_senha = QLineEdit()
        self.input_senha.setPlaceholderText("Deixe em branco para não alterar")
        self.input_permissao = QComboBox()
        self.input_permissao.addItems(["Usuario", "Administrador"])
        self.layout.addRow("Nome:", self.input_nome)
        self.layout.addRow("Login:", self.input_login)
        self.layout.addRow("Nova Senha:", self.input_senha)
        self.layout.addRow("Permissão:", self.input_permissao)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.layout.addWidget(self.botoes)
        if self.usuario_id:
            self.carregar_dados_usuario()
    def carregar_dados_usuario(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/usuarios/{self.usuario_id}", headers=headers)
            if response.status_code == 200:
                dados = response.json()
                self.input_nome.setText(dados.get('nome', ''))
                self.input_login.setText(dados.get('login', ''))
                self.input_permissao.setCurrentText(dados.get('permissao', 'Usuario'))
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar os dados do usuário.")
                self.reject()
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
            self.reject()
    def accept(self):
        global access_token
        if not self.input_nome.text().strip() or not self.input_login.text().strip():
            QMessageBox.warning(self, "Campos Obrigatórios", "Os campos Nome e Login são obrigatórios.")
            return
        dados = {"nome": self.input_nome.text(), "login": self.input_login.text(), "permissao": self.input_permissao.currentText()}
        if self.input_senha.text():
            dados['senha'] = self.input_senha.text()
        elif self.usuario_id is None:
            QMessageBox.warning(self, "Campo Obrigatório", "A senha é obrigatória para novos usuários.")
            return
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            if self.usuario_id is None:
                response = requests.post(f"{API_BASE_URL}/api/usuarios", headers=headers, json=dados)
                mensagem_sucesso = "Usuário adicionado com sucesso!"
                status_esperado = 201
            else:
                response = requests.put(f"{API_BASE_URL}/api/usuarios/{self.usuario_id}", headers=headers, json=dados)
                mensagem_sucesso = "Usuário atualizado com sucesso!"
                status_esperado = 200
            if response.status_code == status_esperado:
                QMessageBox.information(self, "Sucesso", mensagem_sucesso)
                super().accept()
            else:
                raise Exception(response.json().get('erro', 'Erro desconhecido'))
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Não foi possível salvar o usuário: {e}")

class FormularioSetorDialog(QDialog):
    def __init__(self, parent=None, setor_id=None):
        super().__init__(parent)
        self.setor_id = setor_id
        self.setWindowTitle("Adicionar Novo Setor" if self.setor_id is None else "Editar Setor")
        self.setMinimumWidth(300)
        
        self.layout = QFormLayout(self)
        
        self.input_nome = QLineEdit()
        self.layout.addRow("Nome do Setor:", self.input_nome)
        
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.layout.addWidget(self.botoes)
        
        if self.setor_id:
            self.carregar_dados_setor()

    def carregar_dados_setor(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/setores/{self.setor_id}", headers=headers)
            if response.status_code == 200:
                self.input_nome.setText(response.json().get('nome'))
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar dados do setor.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)

    def accept(self):
        nome = self.input_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Campo Obrigatório", "Por favor, preencha o nome do setor.")
            return

        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"nome": nome}
        
        try:
            if self.setor_id is None:
                response = requests.post(f"{API_BASE_URL}/api/setores", headers=headers, json=dados)
                status_esperado = 201
                msg_sucesso = "Setor adicionado com sucesso!"
            else:
                response = requests.put(f"{API_BASE_URL}/api/setores/{self.setor_id}", headers=headers, json=dados)
                status_esperado = 200
                msg_sucesso = "Setor atualizado com sucesso!"

            if response.status_code == status_esperado:
                QMessageBox.information(self, "Sucesso", msg_sucesso)
                signal_handler.setores_atualizados.emit()
                super().accept()
            else:
                erro_msg = response.json().get('erro', 'Erro desconhecido')
                # Tratamento amigável para erro de tabela inexistente
                if "doesn't exist" in str(erro_msg) or "no such table" in str(erro_msg):
                    QMessageBox.warning(self, "Atualização Necessária", 
                        "O sistema precisa de uma atualização no banco de dados para usar Setores.\nContate o suporte.")
                else:
                    QMessageBox.warning(self, "Erro", f"Não foi possível salvar: {erro_msg}")
                    
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
        except Exception as e:
             QMessageBox.critical(self, "Erro Crítico", f"Ocorreu um erro: {str(e)}")


class SetoresWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        
        self.titulo = QLabel("Gestão de Setores")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold;")
        
        layout_botoes = QHBoxLayout()
        self.btn_adicionar = QPushButton("➕ Adicionar Novo")
        self.btn_adicionar.setObjectName("btnPositive")
        self.btn_editar = QPushButton("✏️ Editar Selecionado")
        self.btn_editar.setObjectName("btnNeutral")
        self.btn_excluir = QPushButton("🗑️ Excluir Selecionado")
        self.btn_excluir.setObjectName("btnNegative")
        
        layout_botoes.addWidget(self.btn_adicionar)
        layout_botoes.addWidget(self.btn_editar)
        layout_botoes.addWidget(self.btn_excluir)
        layout_botoes.addStretch(1)
        
        self.tabela_setores = QTableWidget()
        self.tabela_setores.setColumnCount(1)
        self.tabela_setores.setHorizontalHeaderLabels(["Nome do Setor"])
        self.tabela_setores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_setores.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela_setores.setAlternatingRowColors(True)
        self.tabela_setores.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.layout.addWidget(self.titulo)
        self.layout.addLayout(layout_botoes)
        self.layout.addWidget(self.tabela_setores)
        
        self.btn_adicionar.clicked.connect(self.abrir_formulario_adicionar)
        self.btn_editar.clicked.connect(self.abrir_formulario_editar)
        self.btn_excluir.clicked.connect(self.excluir_setor_selecionado)
        
        self.carregar_setores()

    def carregar_setores(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/setores", headers=headers)
            if response.status_code == 200:
                setores = response.json()
                self.tabela_setores.setRowCount(len(setores))
                for linha, setor in enumerate(setores):
                    item_nome = QTableWidgetItem(setor['nome'])
                    item_nome.setData(Qt.UserRole, setor['id'])
                    self.tabela_setores.setItem(linha, 0, item_nome)
            else:
                # Silencioso ou log leve, para não spammar erro ao abrir
                print("Não foi possível carregar setores.")
        except requests.exceptions.RequestException:
            pass # Evita travar a UI se cair a net

    def abrir_formulario_adicionar(self):
        dialog = FormularioSetorDialog(self)
        if dialog.exec():
            self.carregar_setores()

    def abrir_formulario_editar(self):
        linha_selecionada = self.tabela_setores.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um setor para editar.")
            return
        
        item = self.tabela_setores.item(linha_selecionada, 0)
        setor_id = item.data(Qt.UserRole)
        
        dialog = FormularioSetorDialog(self, setor_id=setor_id)
        if dialog.exec():
            self.carregar_setores()

    def excluir_setor_selecionado(self):
        linha_selecionada = self.tabela_setores.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um setor para excluir.")
            return
        
        item = self.tabela_setores.item(linha_selecionada, 0)
        setor_id = item.data(Qt.UserRole)
        nome_setor = item.text()
        
        resposta = QMessageBox.question(self, "Confirmar Exclusão", 
                                      f"Tem certeza que deseja excluir o setor '{nome_setor}'?", 
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if resposta == QMessageBox.StandardButton.Yes:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            try:
                response = requests.delete(f"{API_BASE_URL}/api/setores/{setor_id}", headers=headers)
                if response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", "Setor excluído com sucesso!")
                    self.carregar_setores()
                else:
                    erro_msg = response.json().get('erro', 'Erro desconhecido')
                    QMessageBox.warning(self, "Erro", f"Não foi possível excluir: {erro_msg}")
            except requests.exceptions.RequestException:
                show_connection_error_message(self)

class MudarSenhaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alterar Minha Senha")
        self.setMinimumWidth(350)
        self.layout = QFormLayout(self)
        self.layout.setSpacing(15)
        self.input_senha_atual = QLineEdit()
        self.input_senha_atual.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_nova_senha = QLineEdit()
        self.input_nova_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_confirmacao = QLineEdit()
        self.input_confirmacao.setEchoMode(QLineEdit.EchoMode.Password)
        self.layout.addRow("Senha Atual:", self.input_senha_atual)
        self.layout.addRow("Nova Senha:", self.input_nova_senha)
        self.layout.addRow("Confirmar Nova Senha:", self.input_confirmacao)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.layout.addWidget(self.botoes)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.input_confirmacao.returnPressed.connect(self.accept)
    def accept(self):
        senha_atual = self.input_senha_atual.text()
        nova_senha = self.input_nova_senha.text()
        confirmacao = self.input_confirmacao.text()
        if not senha_atual or not nova_senha or not confirmacao:
            QMessageBox.warning(self, "Campos Vazios", "Todos os campos são obrigatórios.")
            return
        if nova_senha != confirmacao:
            QMessageBox.warning(self, "Erro", "A nova senha e a confirmação não correspondem.")
            return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"senha_atual": senha_atual, "nova_senha": nova_senha, "confirmacao_nova_senha": confirmacao}
        try:
            response = requests.post(f"{API_BASE_URL}/api/usuario/mudar-senha", headers=headers, json=dados)
            if response and response.status_code == 200:
                QMessageBox.information(self, "Sucesso", "Senha alterada com sucesso!")
                super().accept()
            else:
                erro = response.json().get('erro', 'Ocorreu um erro desconhecido.')
                QMessageBox.warning(self, "Falha na Alteração", erro)
        except requests.exceptions.RequestException:
            show_connection_error_message(self)

class QuantidadeDialog(QDialog):
    estoque_modificado = Signal(str)
    def __init__(self, parent, produto_id, produto_nome, produto_codigo, operacao):
        super().__init__(parent)
        self.produto_id = produto_id
        self.produto_codigo = produto_codigo
        self.operacao = operacao
        acao_texto = "Adicionar" if operacao == "Entrada" else "Remover"
        self.setWindowTitle(f"{acao_texto} Estoque")
        self.setMinimumWidth(350)
        self.layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.label_produto = QLabel(f"<b>Produto:</b> {produto_nome}")
        self.input_quantidade = QLineEdit()
        self.input_quantidade.setValidator(QDoubleValidator(0, 99999, 0))
        self.input_motivo = QLineEdit()
        form_layout.addRow(self.label_produto)
        form_layout.addRow("Quantidade:", self.input_quantidade)
        if self.operacao == "Saida":
            form_layout.addRow("Motivo da Saída:", self.input_motivo)
        self.botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.layout.addLayout(form_layout)
        self.layout.addWidget(self.botoes)
        self.botoes.accepted.connect(self.accept)
        self.botoes.rejected.connect(self.reject)
        self.input_quantidade.setFocus()
    def accept(self):
        quantidade_str = self.input_quantidade.text()
        if not quantidade_str or int(quantidade_str) <= 0:
            QMessageBox.warning(self, "Erro", "Por favor, insira uma quantidade válida maior que zero.")
            return
        dados = { "id_produto": self.produto_id, "quantidade": int(quantidade_str) }
        endpoint = "/api/estoque/entrada"
        if self.operacao == "Saida":
            motivo = self.input_motivo.text().strip()
            if not motivo:
                QMessageBox.warning(self, "Erro", "O motivo é obrigatório para saídas de estoque.")
                return
            dados["motivo_saida"] = motivo
            endpoint = "/api/estoque/saida"
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.post(f"{API_BASE_URL}{endpoint}", headers=headers, json=dados)
            if response and response.status_code == 201:
                self.estoque_modificado.emit(self.produto_codigo)
                super().accept()
            else:
                QMessageBox.warning(self, "Erro na API", response.json().get('erro', 'Ocorreu um erro.'))
        except requests.exceptions.RequestException:
            show_connection_error_message(self)

# ==============================================================================
# 4. WIDGETS DE CONTEÚDO (AS "TELAS" PRINCIPAIS)
# ==============================================================================

class ImportacaoWidget(QWidget):
    produtos_importados_sucesso = Signal()
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.caminho_ficheiro = None
        titulo = QLabel("Importação de Produtos em Massa")
        titulo.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        instrucoes = QLabel(
            "<b>Instruções:</b><br>"
            "1. Prepare uma planilha com as seguintes colunas obrigatórias: <b>codigo, nome</b>.<br>"
            "2. Colunas opcionais: <b>preco, quantidade</b>, <b>descricao</b>, <b>fornecedores_nomes</b>, <b>naturezas_nomes</b>.<br>"
            "3. Para múltiplos fornecedores ou naturezas, separe os nomes por vírgula (ex: 'Fornecedor A, Fornecedor B').<br>"
            "4. Salve a planilha no formato <b>CSV (Valores separados por vírgulas)</b>.<br>"
        )
        instrucoes.setWordWrap(True)
        layout_selecao = QHBoxLayout()
        self.btn_selecionar = QPushButton("📂 Selecionar Ficheiro CSV...")
        self.label_ficheiro = QLabel("Nenhum ficheiro selecionado.")
        layout_selecao.addWidget(self.btn_selecionar)
        layout_selecao.addWidget(self.label_ficheiro)
        layout_selecao.addStretch(1)
        self.btn_importar = QPushButton("🚀 Iniciar Importação")
        self.btn_importar.setObjectName("btnPositive")
        self.btn_importar.setEnabled(False)
        label_resultados = QLabel("Resultados da Importação:")
        self.text_resultados = QTextEdit()
        self.text_resultados.setReadOnly(True)
        self.layout.addWidget(titulo)
        self.layout.addWidget(instrucoes)
        self.layout.addLayout(layout_selecao)
        self.layout.addWidget(self.btn_importar)
        self.layout.addWidget(label_resultados)
        self.layout.addWidget(self.text_resultados)
        self.btn_selecionar.clicked.connect(self.selecionar_ficheiro)
        self.btn_importar.clicked.connect(self.iniciar_importacao)
    def selecionar_ficheiro(self):
        caminho, _ = QFileDialog.getOpenFileName(self, "Selecionar Ficheiro CSV", "", "Ficheiros CSV (*.csv)")
        if caminho:
            self.caminho_ficheiro = caminho
            self.label_ficheiro.setText(os.path.basename(caminho))
            self.btn_importar.setEnabled(True)
            self.text_resultados.clear()
    def iniciar_importacao(self):
        if not self.caminho_ficheiro:
            return
        self.text_resultados.setText("A importar... Por favor, aguarde.")
        QApplication.processEvents()
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            with open(self.caminho_ficheiro, 'rb') as f:
                files = {'file': (os.path.basename(self.caminho_ficheiro), f, 'text/csv')}
                response = requests.post(f"{API_BASE_URL}/api/produtos/importar", headers=headers, files=files)
            if response.status_code == 200:
                dados = response.json()
                resultado_texto = f"{dados.get('mensagem', '')}\n"
                resultado_texto += f"Produtos importados com sucesso: {dados.get('produtos_importados', 0)}\n\n"
                erros = dados.get('erros', [])
                if erros:
                    resultado_texto += "Erros encontrados:\n"
                    resultado_texto += "\n".join(erros)
                self.text_resultados.setText(resultado_texto)
                if dados.get('produtos_importados', 0) > 0:
                    self.produtos_importados_sucesso.emit()
            else:
                self.text_resultados.setText(f"Erro na API: {response.text}")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
        except Exception as e:
            self.text_resultados.setText(f"Ocorreu um erro crítico: {e}")
        self.btn_importar.setEnabled(False)

class InventarioWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.dados_exibidos = []
        self.sort_qtd_desc = True
        
        # Inicialização da Interface e Conexões
        self.setup_ui()
        self.connect_signals()
        
        # Carregamento Inicial
        self.carregar_setores_filtro()
        self.carregar_dados_inventario()

    def setup_ui(self):
        """Constrói a interface gráfica do widget."""
        self.layout = QVBoxLayout(self)
        
        # 1. Título
        self.titulo = QLabel("Inventário Completo")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.layout.addWidget(self.titulo)

        # 2. Barra de Busca e Filtros
        layout_filtros = QHBoxLayout()
        
        self.input_pesquisa = QLineEdit()
        self.input_pesquisa.setPlaceholderText("Buscar por Nome ou Códigos (A, B ou C)...")
        
        self.combo_filtro_setor = QComboBox()
        self.combo_filtro_setor.setPlaceholderText("Todos os Setores")
        self.combo_filtro_setor.addItem("Todos os Setores", None)
        self.combo_filtro_setor.setMinimumWidth(180)
        
        layout_filtros.addWidget(self.input_pesquisa)
        layout_filtros.addWidget(self.combo_filtro_setor)
        self.layout.addLayout(layout_filtros)

        # 3. Barra de Ferramentas (Botões)
        layout_acoes = QHBoxLayout()
        
        self.btn_adicionar = QPushButton("➕ Adicionar Novo")
        self.btn_adicionar.setObjectName("btnPositive")
        
        self.btn_editar = QPushButton("✏️ Editar Selecionado")
        self.btn_editar.setObjectName("btnNeutral")
        
        self.btn_excluir = QPushButton("🗑️ Excluir Selecionado")
        self.btn_excluir.setObjectName("btnNegative")
        
        self.btn_gerar_etiquetas = QPushButton("🖨️ Gerar Etiquetas")
        self.btn_gerar_etiquetas.setObjectName("btnPrint")

        layout_acoes.addWidget(self.btn_adicionar)
        layout_acoes.addWidget(self.btn_editar)
        layout_acoes.addWidget(self.btn_excluir)
        layout_acoes.addWidget(self.btn_gerar_etiquetas)
        layout_acoes.addStretch(1) # Espaço vazio no meio

        # Botões de Ordenação
        self.btn_ordenar_nome = QPushButton("🔤 A-Z")
        self.btn_ordenar_nome.setToolTip("Ordenar por Nome do Produto")
        self.btn_ordenar_nome.setObjectName("btnIcon")
        
        self.btn_ordenar_qtd = QPushButton("📦 Qtd.")
        self.btn_ordenar_qtd.setToolTip("Ordenar por Saldo em Estoque")
        self.btn_ordenar_qtd.setObjectName("btnIcon")

        layout_acoes.addWidget(self.btn_ordenar_nome)
        layout_acoes.addWidget(self.btn_ordenar_qtd)
        self.layout.addLayout(layout_acoes)

        # 4. Tabela de Dados
        self.tabela_inventario = QTableWidget()
        self.tabela_inventario.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabela_inventario.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_inventario.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_inventario.setAlternatingRowColors(True)
        self.tabela_inventario.setWordWrap(True)
        
        # Configuração das Colunas (Adicionado Setor)
        colunas = ["Código", "Nome do Produto", "Descrição", "Setor", "Saldo", "Preço (R$)", "Código B", "Código C"]
        self.tabela_inventario.setColumnCount(len(colunas))
        self.tabela_inventario.setHorizontalHeaderLabels(colunas)
        
        header = self.tabela_inventario.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Nome estica
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Descrição estica
        
        self.layout.addWidget(self.tabela_inventario)

    def connect_signals(self):
        """Conecta os eventos dos widgets aos métodos."""
        # Timer para busca (evita requisições a cada tecla)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.carregar_dados_inventario)
        
        self.input_pesquisa.textChanged.connect(self.iniciar_busca_timer)
        self.combo_filtro_setor.currentIndexChanged.connect(self.carregar_dados_inventario)
        
        self.btn_adicionar.clicked.connect(self.abrir_formulario_adicionar)
        self.btn_editar.clicked.connect(self.abrir_formulario_editar)
        self.btn_excluir.clicked.connect(self.excluir_produto_selecionado)
        self.btn_gerar_etiquetas.clicked.connect(self.gerar_etiquetas_selecionadas)
        
        self.btn_ordenar_nome.clicked.connect(self.ordenar_por_nome)
        self.btn_ordenar_qtd.clicked.connect(self.ordenar_por_quantidade)

    # --- Lógica de Dados ---

    def iniciar_busca_timer(self):
        self.search_timer.stop()
        self.search_timer.start(300)

    def carregar_setores_filtro(self):
        """Preenche o combobox de filtro com os setores disponíveis."""
        self.combo_filtro_setor.blockSignals(True)
        self.combo_filtro_setor.clear()
        self.combo_filtro_setor.addItem("Todos os Setores", None)
        
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            # Rota precisa existir no backend (/api/setores)
            resp = requests.get(f"{API_BASE_URL}/api/setores", headers=headers)
            if resp.status_code == 200:
                setores = sorted(resp.json(), key=lambda x: x['nome'])
                for s in setores:
                    self.combo_filtro_setor.addItem(s['nome'], s['id'])
        except:
            pass # Falha silenciosa para não travar a UI
        finally:
            self.combo_filtro_setor.blockSignals(False)

    def carregar_dados_inventario(self):
        """Busca os dados na API aplicando filtros de texto e setor."""
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        
        params = {}
        
        # Filtro de Texto
        termo_busca = self.input_pesquisa.text().strip()
        if termo_busca:
            params['search'] = termo_busca
            
        # Filtro de Setor
        setor_id = self.combo_filtro_setor.currentData()
        if setor_id:
            params['setor_id'] = setor_id

        try:
            response = requests.get(f"{API_BASE_URL}/api/estoque/saldos", headers=headers, params=params)
            if response and response.status_code == 200:
                self.dados_exibidos = response.json()
                self.popular_tabela(self.dados_exibidos)
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar os dados do inventário.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)

    def popular_tabela(self, dados):
        """Preenche a QTableWidget com os dados recebidos."""
        self.tabela_inventario.setRowCount(0)
        self.tabela_inventario.setRowCount(len(dados))
        
        for linha, item in enumerate(dados):
            # Coluna 0: Código (Hidden ID)
            item_codigo = QTableWidgetItem(item['codigo'])
            item_codigo.setData(Qt.UserRole, item['id_produto'])
            self.tabela_inventario.setItem(linha, 0, item_codigo)
            
            # Coluna 1: Nome
            self.tabela_inventario.setItem(linha, 1, QTableWidgetItem(item['nome']))
            
            # Coluna 2: Descrição
            self.tabela_inventario.setItem(linha, 2, QTableWidgetItem(item.get('descricao', '')))
            
            # Coluna 3: Setor (NOVO)
            setor_nome = item.get('setor_nome', '') or '-'
            self.tabela_inventario.setItem(linha, 3, QTableWidgetItem(setor_nome))
            
            # Coluna 4: Saldo
            saldo_item = QTableWidgetItem(str(item['saldo_atual']))
            saldo_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabela_inventario.setItem(linha, 4, saldo_item)
            
            # Coluna 5: Preço
            preco_item = QTableWidgetItem(str(item.get('preco', '0.00')))
            preco_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabela_inventario.setItem(linha, 5, preco_item)
            
            # Coluna 6: Código B
            self.tabela_inventario.setItem(linha, 6, QTableWidgetItem(item.get('codigoB', '')))
            
            # Coluna 7: Código C
            self.tabela_inventario.setItem(linha, 7, QTableWidgetItem(item.get('codigoC', '')))
            
        self.tabela_inventario.resizeRowsToContents()

    # --- Ações do Usuário ---

    def ordenar_por_nome(self):
        self.dados_exibidos.sort(key=lambda item: item['nome'].lower())
        self.popular_tabela(self.dados_exibidos)

    def ordenar_por_quantidade(self):
        self.dados_exibidos.sort(key=lambda item: float(item['saldo_atual']), reverse=self.sort_qtd_desc)
        self.sort_qtd_desc = not self.sort_qtd_desc
        self.popular_tabela(self.dados_exibidos)

    def abrir_formulario_adicionar(self):
        dialog = FormularioProdutoDialog(self)
        if dialog.exec():
            self.carregar_dados_inventario()

    def abrir_formulario_editar(self):
        linha_selecionada = self.tabela_inventario.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um produto para editar.")
            return
            
        item = self.tabela_inventario.item(linha_selecionada, 0)
        produto_id = item.data(Qt.UserRole)
        
        dialog = FormularioProdutoDialog(self, produto_id=produto_id, row=linha_selecionada)
        dialog.produto_atualizado.connect(self.atualizar_linha_tabela)
        dialog.exec()

    def atualizar_linha_tabela(self, linha, dados_produto):
        """Atualiza apenas a linha editada sem recarregar tudo (Otimização)."""
        # Atualiza a memória local
        # Nota: O ideal seria atualizar self.dados_exibidos também, mas para visualização rápida:
        
        self.tabela_inventario.item(linha, 0).setText(dados_produto['codigo'])
        self.tabela_inventario.item(linha, 1).setText(dados_produto['nome'])
        self.tabela_inventario.item(linha, 2).setText(dados_produto.get('descricao', ''))
        
        # Atualiza Setor
        setor_nome = dados_produto.get('setor_nome', '') or '-'
        self.tabela_inventario.item(linha, 3).setText(setor_nome)
        
        # Saldo não muda na edição de cadastro, mantemos o que estava
        
        self.tabela_inventario.item(linha, 5).setText(dados_produto.get('preco', '0.00'))
        self.tabela_inventario.item(linha, 6).setText(dados_produto.get('codigoB', ''))
        self.tabela_inventario.item(linha, 7).setText(dados_produto.get('codigoC', ''))

    def excluir_produto_selecionado(self):
        linha_selecionada = self.tabela_inventario.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um produto para excluir.")
            return
            
        item_id = self.tabela_inventario.item(linha_selecionada, 0)
        produto_id = item_id.data(Qt.UserRole)
        nome_produto = self.tabela_inventario.item(linha_selecionada, 1).text()
        
        resposta = QMessageBox.question(self, "Confirmar Exclusão", 
                                      f"Tem a certeza de que deseja excluir '{nome_produto}'?", 
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if resposta == QMessageBox.StandardButton.Yes:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            try:
                response = requests.delete(f"{API_BASE_URL}/api/produtos/{produto_id}", headers=headers)
                if response and response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", "Produto excluído com sucesso!")
                    self.carregar_dados_inventario()
                else:
                    erro = response.json().get('erro', 'Erro desconhecido.')
                    QMessageBox.warning(self, "Erro", f"Não foi possível excluir: {erro}")
            except requests.exceptions.RequestException:
                show_connection_error_message(self)

    def gerar_etiquetas_selecionadas(self):
        selected_rows = self.tabela_inventario.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "Seleção", "Selecione produtos para gerar etiquetas.")
            return

        product_ids = []
        for index in selected_rows:
            item = self.tabela_inventario.item(index.row(), 0)
            if item:
                product_ids.append(item.data(Qt.UserRole))

        caminho_salvar, _ = QFileDialog.getSaveFileName(self, "Salvar Etiquetas", "etiquetas.pdf", "PDF (*.pdf)")
        if not caminho_salvar:
            return

        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            # Feedback visual simples
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            
            response = requests.post(f"{API_BASE_URL}/api/produtos/etiquetas", 
                                   headers=headers, 
                                   json={'product_ids': product_ids}, 
                                   stream=True)
            
            QApplication.restoreOverrideCursor()

            if response.status_code == 200:
                with open(caminho_salvar, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                QMessageBox.information(self, "Sucesso", f"Etiquetas salvas em:\n{caminho_salvar}")
            else:
                QMessageBox.warning(self, "Erro", f"Erro ao gerar: {response.status_code}")
                
        except Exception as e:
            QApplication.restoreOverrideCursor()
            show_connection_error_message(self)


class GestaoEstoqueWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.inventario_view = InventarioWidget()
        self.historico_view = HistoricoWidget()
        nav_layout = QHBoxLayout()
        self.btn_ver_inventario = QPushButton("Visão Geral do Inventário")
        self.btn_ver_historico = QPushButton("Ver Histórico de Movimentações")
        self.btn_ver_inventario.setCheckable(True)
        self.btn_ver_historico.setCheckable(True)
        self.btn_ver_inventario.setChecked(True)
        nav_layout.addWidget(self.btn_ver_inventario)
        nav_layout.addWidget(self.btn_ver_historico)
        nav_layout.addStretch(1)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.inventario_view)
        self.stack.addWidget(self.historico_view)
        self.layout.addLayout(nav_layout)
        self.layout.addWidget(self.stack)
        self.btn_ver_inventario.clicked.connect(self.mostrar_inventario)
        self.btn_ver_historico.clicked.connect(self.mostrar_historico)
    def mostrar_inventario(self):
        self.stack.setCurrentWidget(self.inventario_view)
        self.btn_ver_inventario.setChecked(True)
        self.btn_ver_historico.setChecked(False)
        self.inventario_view.carregar_dados_inventario()
    def mostrar_historico(self):
        self.stack.setCurrentWidget(self.historico_view)
        self.btn_ver_inventario.setChecked(False)
        self.btn_ver_historico.setChecked(True)
        self.historico_view.carregar_historico()

class HistoricoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.dados_completos = []
        layout_filtros = QHBoxLayout()
        self.combo_tipo = QComboBox()
        self.combo_tipo.addItems(["Todas", "Entrada", "Saida"])
        self.combo_tipo.setStyleSheet("font-size: 14px; padding: 5px;")
        self.btn_recarregar = QPushButton("Recarregar Histórico")
        layout_filtros.addWidget(QLabel("Filtrar por tipo:"))
        layout_filtros.addWidget(self.combo_tipo)
        layout_filtros.addStretch(1)
        layout_filtros.addWidget(self.btn_recarregar)
        self.tabela_historico = QTableWidget()
        self.tabela_historico.setColumnCount(8)
        self.tabela_historico.setHorizontalHeaderLabels(["Data/Hora", "Cód. Produto", "Nome Produto", "Tipo", "Qtd. Mov.", "Saldo Após", "Usuário", "Motivo da Saída"])
        self.tabela_historico.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_historico.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_historico.setAlternatingRowColors(True)
        self.layout.addLayout(layout_filtros)
        self.layout.addWidget(self.tabela_historico)
        self.btn_recarregar.clicked.connect(self.carregar_historico)
        self.combo_tipo.currentIndexChanged.connect(self.carregar_historico)
        self.carregar_historico()
    def carregar_historico(self):
        global access_token
        data_fim = QDate.currentDate()
        data_inicio = data_fim.addDays(-90)
        params = {'data_inicio': data_inicio.toString("yyyy-MM-dd"), 'data_fim': data_fim.toString("yyyy-MM-dd"), 'formato': 'json'}
        filtro_tipo = self.combo_tipo.currentText()
        if filtro_tipo != "Todas":
            params['tipo'] = filtro_tipo
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/relatorios/movimentacoes", headers=headers, params=params)
            if response and response.status_code == 200:
                self.dados_completos = response.json()
                self.popular_tabela(self.dados_completos)
            else:
                mensagem = "Não foi possível carregar o histórico."
                if response:
                    mensagem += f"\n(Erro: {response.status_code})"
                QMessageBox.warning(self, "Erro", mensagem)
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def popular_tabela(self, dados):
        self.tabela_historico.setRowCount(0)
        self.tabela_historico.setRowCount(len(dados))
        for linha, mov in enumerate(dados):
            self.tabela_historico.setItem(linha, 0, QTableWidgetItem(mov['data_hora']))
            self.tabela_historico.setItem(linha, 1, QTableWidgetItem(mov['produto_codigo']))
            self.tabela_historico.setItem(linha, 2, QTableWidgetItem(mov['produto_nome']))
            self.tabela_historico.setItem(linha, 3, QTableWidgetItem(mov['tipo']))
            self.tabela_historico.setItem(linha, 4, QTableWidgetItem(str(mov['quantidade'])))
            self.tabela_historico.setItem(linha, 5, QTableWidgetItem(str(mov.get('saldo_apos', ''))))
            self.tabela_historico.setItem(linha, 6, QTableWidgetItem(mov['usuario_nome']))
            self.tabela_historico.setItem(linha, 7, QTableWidgetItem(mov.get('motivo_saida', '')))

class RelatoriosWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        titulo = QLabel("Módulo de Geração de Relatórios")
        titulo.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        self.combo_tipo_relatorio = QComboBox()
        self.combo_tipo_relatorio.addItems(["Inventário Atual", "Histórico de Movimentações"])
        self.combo_tipo_relatorio.setStyleSheet("font-size: 16px; padding: 8px;")
        form_layout.addRow("Selecione o Relatório:", self.combo_tipo_relatorio)
        self.label_data_inicio = QLabel("Data de Início:")
        self.input_data_inicio = QDateEdit(self)
        self.input_data_inicio.setCalendarPopup(True)
        self.input_data_inicio.setDate(QDate.currentDate().addMonths(-1))
        self.input_data_inicio.setStyleSheet("font-size: 16px; padding: 8px;")
        self.label_data_fim = QLabel("Data de Fim:")
        self.input_data_fim = QDateEdit(self)
        self.input_data_fim.setCalendarPopup(True)
        self.input_data_fim.setDate(QDate.currentDate())
        self.input_data_fim.setStyleSheet("font-size: 16px; padding: 8px;")
        form_layout.addRow(self.label_data_inicio, self.input_data_inicio)
        form_layout.addRow(self.label_data_fim, self.input_data_fim)
        self.label_tipo_mov = QLabel("Tipo de Movimentação:")
        self.combo_tipo_mov = QComboBox()
        self.combo_tipo_mov.addItems(["Todas", "Entrada", "Saida"])
        self.combo_tipo_mov.setStyleSheet("font-size: 16px; padding: 8px;")
        form_layout.addRow(self.label_tipo_mov, self.combo_tipo_mov)
        layout_botoes = QHBoxLayout()
        self.btn_gerar_pdf = QPushButton("Gerar PDF")
        self.btn_gerar_pdf.setObjectName("btnNegative")
        self.btn_gerar_excel = QPushButton("Gerar Excel (XLSX)")
        self.btn_gerar_excel.setObjectName("btnPositive")
        layout_botoes.addStretch(1)
        layout_botoes.addWidget(self.btn_gerar_pdf)
        layout_botoes.addWidget(self.btn_gerar_excel)
        self.layout.addWidget(titulo)
        self.layout.addLayout(form_layout)
        self.layout.addLayout(layout_botoes)
        self.layout.addStretch(1)
        self.combo_tipo_relatorio.currentIndexChanged.connect(self.atualizar_visibilidade_filtros)
        self.btn_gerar_pdf.clicked.connect(lambda: self.gerar_relatorio('pdf'))
        self.btn_gerar_excel.clicked.connect(lambda: self.gerar_relatorio('xlsx'))
        self.atualizar_visibilidade_filtros()
    def atualizar_visibilidade_filtros(self):
        relatorio_selecionado = self.combo_tipo_relatorio.currentText()
        is_historico = (relatorio_selecionado == "Histórico de Movimentações")
        self.label_data_inicio.setVisible(is_historico)
        self.input_data_inicio.setVisible(is_historico)
        self.label_data_fim.setVisible(is_historico)
        self.input_data_fim.setVisible(is_historico)
        self.label_tipo_mov.setVisible(is_historico)
        self.combo_tipo_mov.setVisible(is_historico)
    def gerar_relatorio(self, formato):
        relatorio_selecionado = self.combo_tipo_relatorio.currentText()
        params = {'formato': formato}
        endpoint = ""
        nome_arquivo_base = ""
        if relatorio_selecionado == "Inventário Atual":
            endpoint = f"{API_BASE_URL}/api/relatorios/inventario"
            nome_arquivo_base = "relatorio_inventario"
        else:
            endpoint = f"{API_BASE_URL}/api/relatorios/movimentacoes"
            nome_arquivo_base = "relatorio_movimentacoes"
            params['data_inicio'] = self.input_data_inicio.date().toString("yyyy-MM-dd")
            params['data_fim'] = self.input_data_fim.date().toString("yyyy-MM-dd")
            tipo_mov = self.combo_tipo_mov.currentText()
            if tipo_mov != "Todas":
                params['tipo'] = tipo_mov
        extensao = f".{formato}"
        caminho_salvar, _ = QFileDialog.getSaveFileName(self, "Salvar Relatório", f"{nome_arquivo_base}{extensao}", f"Arquivos {formato.upper()} (*{extensao})")
        if not caminho_salvar:
            return
        try:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            response = requests.get(endpoint, headers=headers, params=params, stream=True)
            if response.status_code == 200:
                with open(caminho_salvar, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                QMessageBox.information(self, "Sucesso", f"Relatório salvo com sucesso em:\n{caminho_salvar}")
            else:
                QMessageBox.warning(self, "Erro", f"A API retornou um erro: {response.status_code}")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)

class FornecedoresWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.titulo = QLabel("Gestão de Fornecedores")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout_botoes = QHBoxLayout()
        self.btn_adicionar = QPushButton("➕ Adicionar Novo")
        self.btn_adicionar.setObjectName("btnPositive")
        self.btn_editar = QPushButton("✏️ Editar Selecionado")
        self.btn_editar.setObjectName("btnNeutral")
        self.btn_excluir = QPushButton("🗑️ Excluir Selecionado")
        self.btn_excluir.setObjectName("btnNegative")
        layout_botoes.addWidget(self.btn_adicionar)
        layout_botoes.addWidget(self.btn_editar)
        layout_botoes.addWidget(self.btn_excluir)
        layout_botoes.addStretch(1)
        self.tabela_fornecedores = QTableWidget()
        self.tabela_fornecedores.setColumnCount(1)
        self.tabela_fornecedores.setHorizontalHeaderLabels(["Nome"])
        self.tabela_fornecedores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_fornecedores.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.titulo)
        self.layout.addLayout(layout_botoes)
        self.layout.addWidget(self.tabela_fornecedores)
        self.btn_adicionar.clicked.connect(self.abrir_formulario_adicionar)
        self.btn_editar.clicked.connect(self.abrir_formulario_editar)
        self.btn_excluir.clicked.connect(self.excluir_fornecedor_selecionado)
        self.carregar_fornecedores()
    def carregar_fornecedores(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/fornecedores", headers=headers)
            if response.status_code == 200:
                fornecedores = response.json()
                self.tabela_fornecedores.setRowCount(len(fornecedores))
                for linha, forn in enumerate(fornecedores):
                    item_nome = QTableWidgetItem(forn['nome'])
                    item_nome.setData(Qt.UserRole, forn['id'])
                    self.tabela_fornecedores.setItem(linha, 0, item_nome)
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar os fornecedores.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def abrir_formulario_adicionar(self):
        dialog = FormularioFornecedorDialog(self)
        if dialog.exec():
            self.carregar_fornecedores()
    def abrir_formulario_editar(self):
        linha_selecionada = self.tabela_fornecedores.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um fornecedor para editar.")
            return
        item = self.tabela_fornecedores.item(linha_selecionada, 0)
        fornecedor_id = item.data(Qt.UserRole)
        dialog = FormularioFornecedorDialog(self, fornecedor_id=fornecedor_id)
        if dialog.exec():
            self.carregar_fornecedores()
    def excluir_fornecedor_selecionado(self):
        linha_selecionada = self.tabela_fornecedores.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um fornecedor para excluir.")
            return
        item = self.tabela_fornecedores.item(linha_selecionada, 0)
        fornecedor_id = item.data(Qt.UserRole)
        nome_fornecedor = item.text()
        resposta = QMessageBox.question(self, "Confirmar Exclusão", f"Tem a certeza de que deseja excluir o fornecedor '{nome_fornecedor}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resposta == QMessageBox.StandardButton.Yes:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            try:
                response = requests.delete(f"{API_BASE_URL}/api/fornecedores/{fornecedor_id}", headers=headers)
                if response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", "Fornecedor excluído com sucesso!")
                    self.carregar_fornecedores()
                else:
                    QMessageBox.warning(self, "Erro", f"Não foi possível excluir: {response.json().get('erro')}")
            except requests.exceptions.RequestException:
                show_connection_error_message(self)

class NaturezasWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.titulo = QLabel("Gestão de Naturezas")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout_botoes = QHBoxLayout()
        self.btn_adicionar = QPushButton("➕ Adicionar Nova")
        self.btn_adicionar.setObjectName("btnPositive")
        self.btn_editar = QPushButton("✏️ Editar Selecionada")
        self.btn_editar.setObjectName("btnNeutral")
        self.btn_excluir = QPushButton("🗑️ Excluir Selecionada")
        self.btn_excluir.setObjectName("btnNegative")
        layout_botoes.addWidget(self.btn_adicionar)
        layout_botoes.addWidget(self.btn_editar)
        layout_botoes.addWidget(self.btn_excluir)
        layout_botoes.addStretch(1)
        self.tabela_naturezas = QTableWidget()
        self.tabela_naturezas.setColumnCount(1)
        self.tabela_naturezas.setHorizontalHeaderLabels(["Nome"])
        self.tabela_naturezas.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_naturezas.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.titulo)
        self.layout.addLayout(layout_botoes)
        self.layout.addWidget(self.tabela_naturezas)
        self.btn_adicionar.clicked.connect(self.abrir_formulario_adicionar)
        self.btn_editar.clicked.connect(self.abrir_formulario_editar)
        self.btn_excluir.clicked.connect(self.excluir_natureza_selecionada)
        self.carregar_naturezas()
    def carregar_naturezas(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/naturezas", headers=headers)
            if response.status_code == 200:
                naturezas = response.json()
                self.tabela_naturezas.setRowCount(len(naturezas))
                for linha, nat in enumerate(naturezas):
                    item_nome = QTableWidgetItem(nat['nome'])
                    item_nome.setData(Qt.UserRole, nat['id'])
                    self.tabela_naturezas.setItem(linha, 0, item_nome)
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar as naturezas.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def abrir_formulario_adicionar(self):
        dialog = FormularioNaturezaDialog(self)
        if dialog.exec():
            self.carregar_naturezas()
    def abrir_formulario_editar(self):
        linha_selecionada = self.tabela_naturezas.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione uma natureza para editar.")
            return
        item = self.tabela_naturezas.item(linha_selecionada, 0)
        natureza_id = item.data(Qt.UserRole)
        dialog = FormularioNaturezaDialog(self, natureza_id=natureza_id)
        if dialog.exec():
            self.carregar_naturezas()
    def excluir_natureza_selecionada(self):
        linha_selecionada = self.tabela_naturezas.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione uma natureza para excluir.")
            return
        item = self.tabela_naturezas.item(linha_selecionada, 0)
        natureza_id = item.data(Qt.UserRole)
        nome_natureza = item.text()
        resposta = QMessageBox.question(self, "Confirmar Exclusão", f"Tem a certeza de que deseja excluir a natureza '{nome_natureza}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resposta == QMessageBox.StandardButton.Yes:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            try:
                response = requests.delete(f"{API_BASE_URL}/api/naturezas/{natureza_id}", headers=headers)
                if response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", "Natureza excluída com sucesso!")
                    self.carregar_naturezas()
                else:
                    QMessageBox.warning(self, "Erro", f"Não foi possível excluir: {response.json().get('erro')}")
            except requests.exceptions.RequestException:
                show_connection_error_message(self)

class EntradaRapidaWidget(QWidget):
    estoque_atualizado = Signal()
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.produto_encontrado_id = None
        self.titulo = QLabel("Entrada Rápida de Estoque")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        self.input_codigo = QLineEdit()
        self.input_codigo.setPlaceholderText("Digite ou leia o código do produto aqui")
        self.btn_verificar = QPushButton("Verificar Produto")
        self.btn_verificar.setObjectName("btnNeutral")
        layout_codigo = QHBoxLayout()
        layout_codigo.addWidget(self.input_codigo)
        layout_codigo.addWidget(self.btn_verificar)
        form_layout.addRow("Código do Produto:", layout_codigo)
        self.label_nome_produto = QLabel("Aguardando verificação...")
        form_layout.addRow("Produto Encontrado:", self.label_nome_produto)
        self.input_quantidade = QLineEdit()
        self.input_quantidade.setPlaceholderText("0")
        self.input_quantidade.setValidator(QDoubleValidator(0, 99999, 0))
        form_layout.addRow("Quantidade a Adicionar:", self.input_quantidade)
        self.btn_registrar = QPushButton("Registar Entrada")
        self.btn_registrar.setObjectName("btnPositive")
        self.layout.addWidget(self.titulo)
        self.layout.addLayout(form_layout)
        self.layout.addWidget(self.btn_registrar, 0, Qt.AlignmentFlag.AlignRight)
        self.layout.addStretch(1)
        self.btn_verificar.clicked.connect(self.verificar_produto)
        self.input_codigo.returnPressed.connect(self.verificar_produto) 
        self.btn_registrar.clicked.connect(self.registrar_entrada)
        self.input_quantidade.returnPressed.connect(self.btn_registrar.click)
        self.resetar_formulario()
    def verificar_produto(self):
        codigo_produto = self.input_codigo.text().strip()
        if not codigo_produto:
            QMessageBox.warning(self, "Atenção", "O campo de código não pode estar vazio.")
            return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/produtos/codigo/{codigo_produto}", headers=headers)
            if response and response.status_code == 200:
                dados_produto = response.json()
                self.produto_encontrado_id = dados_produto['id']
                nome = dados_produto['nome']
                self.label_nome_produto.setText(f"{nome}")
                self.label_nome_produto.setStyleSheet("font-size: 16px; font-weight: bold; color: #28a745;")
                self.input_quantidade.setEnabled(True)
                self.btn_registrar.setEnabled(True)
                self.input_quantidade.setFocus()
            else:
                self.label_nome_produto.setText("Produto não encontrado!")
                self.label_nome_produto.setStyleSheet("font-size: 16px; font-weight: bold; color: #dc3545;")
                self.produto_encontrado_id = None
                self.input_quantidade.clear()
                self.input_quantidade.setEnabled(False)
                self.btn_registrar.setEnabled(False)
                self.input_codigo.selectAll()
                self.input_codigo.setFocus()
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def registrar_entrada(self):
        quantidade = self.input_quantidade.text()
        if not self.produto_encontrado_id or not quantidade or int(quantidade) <= 0:
            QMessageBox.warning(self, "Dados Inválidos", "Verifique o produto e insira uma quantidade válida maior que zero.")
            return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"id_produto": self.produto_encontrado_id, "quantidade": int(quantidade)}
        try:
            response = requests.post(f"{API_BASE_URL}/api/estoque/entrada", headers=headers, json=dados)
            if response and response.status_code == 201:
                self.estoque_atualizado.emit()
                QMessageBox.information(self, "Sucesso", "Entrada de estoque registada com sucesso!")
                self.resetar_formulario()
            else:
                erro = response.json().get('erro', 'Erro desconhecido.')
                QMessageBox.warning(self, "Erro", f"Não foi possível registar a entrada: {erro}")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def resetar_formulario(self):
        self.produto_encontrado_id = None
        self.input_codigo.clear()
        self.input_quantidade.clear()
        self.label_nome_produto.setText("Aguardando verificação...")
        self.label_nome_produto.setStyleSheet("font-size: 16px; font-weight: bold; color: #555;")
        self.input_quantidade.setEnabled(False)
        self.btn_registrar.setEnabled(False)
        self.input_codigo.setFocus()

class SaidaRapidaWidget(QWidget):
    estoque_atualizado = Signal()
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.produto_encontrado_id = None
        self.titulo = QLabel("Saída Rápida de Estoque")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        self.input_codigo = QLineEdit()
        self.input_codigo.setPlaceholderText("Digite ou leia o código do produto aqui")
        self.btn_verificar = QPushButton("Verificar Produto")
        self.btn_verificar.setObjectName("btnNeutral")
        self.label_nome_produto = QLabel("Aguardando verificação...")
        self.input_quantidade = QLineEdit()
        self.input_quantidade.setPlaceholderText("0")
        self.input_quantidade.setValidator(QDoubleValidator(0, 99999, 0))
        self.input_motivo = QLineEdit()
        self.input_motivo.setPlaceholderText("Ex: Venda, Perda, Ajuste de inventário")
        self.btn_registrar = QPushButton("Registar Saída")
        self.btn_registrar.setObjectName("btnNegative")
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        layout_codigo = QHBoxLayout()
        layout_codigo.addWidget(self.input_codigo)
        layout_codigo.addWidget(self.btn_verificar)
        form_layout.addRow("Código do Produto:", layout_codigo)
        form_layout.addRow("Produto Encontrado:", self.label_nome_produto)
        form_layout.addRow("Quantidade a Retirar:", self.input_quantidade)
        form_layout.addRow("Motivo da Saída:", self.input_motivo)
        self.layout.addWidget(self.titulo)
        self.layout.addLayout(form_layout)
        self.layout.addWidget(self.btn_registrar, 0, Qt.AlignmentFlag.AlignRight)
        self.layout.addStretch(1)
        self.btn_verificar.clicked.connect(self.verificar_produto)
        self.input_codigo.returnPressed.connect(self.verificar_produto)
        self.btn_registrar.clicked.connect(self.registrar_saida)
        self.input_motivo.returnPressed.connect(self.btn_registrar.click)
        self.resetar_formulario()
    def verificar_produto(self):
        codigo_produto = self.input_codigo.text().strip()
        if not codigo_produto: return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/produtos/codigo/{codigo_produto}", headers=headers)
            if response and response.status_code == 200:
                dados_produto = response.json()
                self.produto_encontrado_id = dados_produto['id']
                self.label_nome_produto.setText(dados_produto['nome'])
                self.label_nome_produto.setStyleSheet("font-size: 16px; font-weight: bold; color: #28a745;")
                self.input_quantidade.setEnabled(True)
                self.input_motivo.setEnabled(True)
                self.btn_registrar.setEnabled(True)
                self.input_quantidade.setFocus()
            else:
                self.label_nome_produto.setText("Produto não encontrado!")
                self.label_nome_produto.setStyleSheet("font-size: 16px; font-weight: bold; color: #dc3545;")
                self.produto_encontrado_id = None
                self.input_quantidade.clear()
                self.input_motivo.clear()
                self.input_quantidade.setEnabled(False)
                self.input_motivo.setEnabled(False)
                self.btn_registrar.setEnabled(False)
                self.input_codigo.selectAll()
                self.input_codigo.setFocus()
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def registrar_saida(self):
        quantidade = self.input_quantidade.text()
        motivo = self.input_motivo.text().strip()
        if not self.produto_encontrado_id or not quantidade or int(quantidade) <= 0:
            QMessageBox.warning(self, "Dados Inválidos", "Verifique o produto e insira uma quantidade válida.")
            return
        if not motivo:
            QMessageBox.warning(self, "Dados Inválidos", "O campo 'Motivo da Saída' é obrigatório.")
            return
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        dados = {"id_produto": self.produto_encontrado_id, "quantidade": int(quantidade), "motivo_saida": motivo}
        try:
            response = requests.post(f"{API_BASE_URL}/api/estoque/saida", headers=headers, json=dados)
            if response and response.status_code == 201:
                self.estoque_atualizado.emit()
                QMessageBox.information(self, "Sucesso", "Saída de estoque registada com sucesso!")
                self.resetar_formulario()
            else:
                erro = response.json().get('erro', 'Erro desconhecido.')
                QMessageBox.warning(self, "Erro", f"Não foi possível registar a saída: {erro}")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def resetar_formulario(self):
        self.produto_encontrado_id = None
        self.input_codigo.clear()
        self.input_quantidade.clear()
        self.input_motivo.clear()
        self.label_nome_produto.setText("Aguardando verificação...")
        self.label_nome_produto.setStyleSheet("font-size: 16px; font-weight: bold; color: #555;")
        self.input_quantidade.setEnabled(False)
        self.input_motivo.setEnabled(False)
        self.btn_registrar.setEnabled(False)
        self.input_codigo.setFocus()

class UsuariosWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.titulo = QLabel("Gestão de Usuários")
        self.titulo.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout_botoes = QHBoxLayout()
        self.btn_adicionar = QPushButton("➕ Adicionar Novo")
        self.btn_adicionar.setObjectName("btnPositive")
        self.btn_editar = QPushButton("✏️ Editar Selecionado")
        self.btn_editar.setObjectName("btnNeutral")
        self.btn_desativar = QPushButton("🚫 Desativar/Reativar")
        self.btn_desativar.setObjectName("btnNegative")
        layout_botoes.addWidget(self.btn_adicionar)
        layout_botoes.addWidget(self.btn_editar)
        layout_botoes.addWidget(self.btn_desativar)
        layout_botoes.addStretch(1)
        self.tabela_usuarios = QTableWidget()
        self.tabela_usuarios.setColumnCount(4)
        self.tabela_usuarios.setHorizontalHeaderLabels(["Nome", "Login", "Permissão", "Status"])
        self.tabela_usuarios.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela_usuarios.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela_usuarios.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabela_usuarios.setAlternatingRowColors(True)
        self.layout.addWidget(self.titulo)
        self.layout.addLayout(layout_botoes)
        self.layout.addWidget(self.tabela_usuarios)
        self.btn_adicionar.clicked.connect(self.abrir_formulario_adicionar)
        self.btn_editar.clicked.connect(self.abrir_formulario_editar)
        self.btn_desativar.clicked.connect(self.desativar_usuario_selecionado)
        self.carregar_usuarios()
    def carregar_usuarios(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/usuarios", headers=headers)
            if response.status_code == 200:
                usuarios = response.json()
                self.tabela_usuarios.setRowCount(len(usuarios))
                for linha, user in enumerate(usuarios):
                    item_nome = QTableWidgetItem(user['nome'])
                    item_nome.setData(Qt.UserRole, user['id'])
                    status = "Ativo" if user['ativo'] else "Inativo"
                    self.tabela_usuarios.setItem(linha, 0, item_nome)
                    self.tabela_usuarios.setItem(linha, 1, QTableWidgetItem(user['login']))
                    self.tabela_usuarios.setItem(linha, 2, QTableWidgetItem(user['permissao']))
                    self.tabela_usuarios.setItem(linha, 3, QTableWidgetItem(status))
            else:
                QMessageBox.warning(self, "Erro", "Não foi possível carregar os usuários.")
        except requests.exceptions.RequestException:
            show_connection_error_message(self)
    def abrir_formulario_adicionar(self):
        dialog = FormularioUsuarioDialog(self)
        if dialog.exec():
            self.carregar_usuarios()
    def abrir_formulario_editar(self):
        linha_selecionada = self.tabela_usuarios.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um usuário para editar.")
            return
        item_id = self.tabela_usuarios.item(linha_selecionada, 0)
        usuario_id = item_id.data(Qt.UserRole)
        dialog = FormularioUsuarioDialog(self, usuario_id=usuario_id)
        if dialog.exec():
            self.carregar_usuarios()
    def desativar_usuario_selecionado(self):
        linha_selecionada = self.tabela_usuarios.currentRow()
        if linha_selecionada < 0:
            QMessageBox.warning(self, "Seleção", "Por favor, selecione um usuário.")
            return
        item_id = self.tabela_usuarios.item(linha_selecionada, 0)
        usuario_id = item_id.data(Qt.UserRole)
        nome_usuario = self.tabela_usuarios.item(linha_selecionada, 0).text()
        status_atual = self.tabela_usuarios.item(linha_selecionada, 3).text()
        acao = "desativar" if status_atual == "Ativo" else "reativar"
        resposta = QMessageBox.question(self, f"Confirmar Ação", f"Tem certeza que deseja {acao} o usuário '{nome_usuario}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if resposta == QMessageBox.StandardButton.Yes:
            global access_token
            headers = {'Authorization': f'Bearer {access_token}'}
            try:
                response = requests.delete(f"{API_BASE_URL}/api/usuarios/{usuario_id}", headers=headers)
                if response.status_code == 200:
                    QMessageBox.information(self, "Sucesso", response.json()['mensagem'])
                    self.carregar_usuarios()
                else:
                    mensagem_erro = f"O servidor retornou um erro: {response.status_code}."
                    try:
                        detalhe_erro = response.json().get('erro')
                        if detalhe_erro:
                            mensagem_erro += f"\nDetalhe: {detalhe_erro}"
                    except requests.exceptions.JSONDecodeError:
                        mensagem_erro += f"\nResposta: {response.text}"
                    QMessageBox.warning(self, "Erro", mensagem_erro)
            except requests.exceptions.RequestException:
                show_connection_error_message(self)

class TerminalWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("terminalWidget")
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.barcode_buffer = ""
        self.barcode_timer = QTimer(self)
        self.barcode_timer.setSingleShot(True)
        self.barcode_timer.setInterval(200)
        self.barcode_timer.timeout.connect(self.processar_codigo)
        self.produto_atual = None
        main_panel = QFrame()
        main_panel.setObjectName("terminalMainPanel")
        main_panel_layout = QVBoxLayout(main_panel)
        main_panel_layout.setSpacing(20)
        top_section_layout = QHBoxLayout()
        self.label_nome = QLabel("Passe um código de barras no leitor...")
        self.label_nome.setObjectName("terminalProductName")
        self.label_nome.setWordWrap(True)
        self.label_qtd_box = QFrame()
        self.label_qtd_box.setObjectName("terminalQuantityBox")
        qtd_layout = QVBoxLayout(self.label_qtd_box)
        self.label_qtd_valor = QLabel("--")
        self.label_qtd_valor.setObjectName("terminalQuantityValue")
        qtd_layout.addWidget(self.label_qtd_valor)
        top_section_layout.addWidget(self.label_nome, 4)
        top_section_layout.addWidget(self.label_qtd_box, 1)
        action_buttons_layout = QHBoxLayout()
        self.btn_remover = QPushButton("➖")
        self.btn_remover.setObjectName("btnTerminalRemove")
        self.btn_adicionar = QPushButton("➕")
        self.btn_adicionar.setObjectName("btnTerminalAdd")
        action_buttons_layout.addStretch(1)
        action_buttons_layout.addWidget(self.btn_remover)
        action_buttons_layout.addWidget(self.btn_adicionar)
        action_buttons_layout.addStretch(1)
        main_panel_layout.addLayout(top_section_layout)
        main_panel_layout.addLayout(action_buttons_layout)
        bottom_panel = QFrame()
        bottom_panel.setObjectName("terminalBottomPanel")
        bottom_panel_layout = QVBoxLayout(bottom_panel)
        self.label_descricao = QLabel("Descrição do produto aparecerá aqui.")
        self.label_descricao.setObjectName("terminalDescription")
        self.label_codigo = QLabel("Código: --")
        self.label_codigo.setObjectName("terminalCode")
        bottom_panel_layout.addWidget(self.label_descricao)
        bottom_panel_layout.addWidget(self.label_codigo)
        self.layout.addWidget(main_panel, 2)
        self.layout.addWidget(bottom_panel, 1)
        self.btn_adicionar.clicked.connect(lambda: self.abrir_dialogo_quantidade("Entrada"))
        self.btn_remover.clicked.connect(lambda: self.abrir_dialogo_quantidade("Saida"))
        self.resetar_tela()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.processar_codigo()
        else:
            self.barcode_buffer += event.text()
            self.barcode_timer.start()
    def processar_codigo(self):
        codigo = self.barcode_buffer.strip()
        self.barcode_buffer = ""
        if not codigo:
            return
        self.label_nome.setText("A procurar...")
        QApplication.processEvents()
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/estoque/saldos?search={codigo}", headers=headers)
            if response and response.status_code == 200:
                resultados = response.json()
                if resultados:
                    self.produto_atual = resultados[0]
                    self.atualizar_display()
                else:
                    self.produto_nao_encontrado()
            else:
                self.produto_nao_encontrado()
        except requests.exceptions.RequestException:
            self.produto_nao_encontrado("Erro de conexão.")
    def atualizar_display(self):
        self.label_nome.setText(self.produto_atual.get('nome', 'N/A'))
        self.label_qtd_valor.setText(str(self.produto_atual.get('saldo_atual', '--')))
        self.label_descricao.setText(self.produto_atual.get('descricao', 'Sem descrição.'))
        self.label_codigo.setText(f"Código: {self.produto_atual.get('codigo', '--')}")
        self.btn_adicionar.setEnabled(True)
        self.btn_remover.setEnabled(True)
    def produto_nao_encontrado(self, msg="Produto não encontrado."):
        self.produto_atual = None
        self.label_nome.setText(msg)
        self.resetar_tela(manter_msg=True)
    def resetar_tela(self, manter_msg=False):
        if not manter_msg:
            self.label_nome.setText("Passe um código de barras no leitor...")
        self.label_qtd_valor.setText("--")
        self.label_descricao.setText("Descrição do produto aparecerá aqui.")
        self.label_codigo.setText("Código: --")
        self.btn_adicionar.setEnabled(False)
        self.btn_remover.setEnabled(False)
    def abrir_dialogo_quantidade(self, operacao):
        if not self.produto_atual:
            return
        dialog = QuantidadeDialog(self, self.produto_atual['id_produto'], self.produto_atual['nome'], self.produto_atual['codigo'], operacao)
        dialog.estoque_modificado.connect(self.reprocessar_codigo_apos_modificacao)
        dialog.exec()
    def reprocessar_codigo_apos_modificacao(self, codigo):
        print(f"Atualização recebida para o código: {codigo}. A reprocessar...")
        self.barcode_buffer = codigo
        self.processar_codigo()

# ==============================================================================
# 5. CLASSE DA JANELA PRINCIPAL
# ==============================================================================

class JanelaPrincipal(QMainWindow):
    logoff_requested = Signal()
    def __init__(self):
        super().__init__()
        try:
            self.setWindowTitle("Sistema de Gestão de Estoque")
            self.resize(1280, 720)
            self.dados_usuario = {}
            self.stacked_widget = QStackedWidget()
            self.stacked_widget.setObjectName("mainContentArea")
            self.tela_dashboard = DashboardWidget()
            self.tela_gestao_estoque = GestaoEstoqueWidget()
            self.tela_entrada_rapida = EntradaRapidaWidget()
            self.tela_saida_rapida = SaidaRapidaWidget()
            self.tela_relatorios = RelatoriosWidget()
            self.tela_fornecedores = FornecedoresWidget()
            self.tela_naturezas = NaturezasWidget()
            self.tela_usuarios = None
            self.tela_importacao = ImportacaoWidget()
            self.tela_terminal = TerminalWidget()
            self.tela_setores = SetoresWidget()
            self.stacked_widget.addWidget(self.tela_dashboard)
            self.stacked_widget.addWidget(self.tela_gestao_estoque)
            self.stacked_widget.addWidget(self.tela_entrada_rapida)
            self.stacked_widget.addWidget(self.tela_saida_rapida)
            self.stacked_widget.addWidget(self.tela_relatorios)
            self.stacked_widget.addWidget(self.tela_fornecedores)
            self.stacked_widget.addWidget(self.tela_naturezas)
            self.stacked_widget.addWidget(self.tela_importacao)
            self.stacked_widget.addWidget(self.tela_terminal)
            self.stacked_widget.addWidget(self.tela_setores)
            menu_bar = self.menuBar()
            menu_arquivo = menu_bar.addMenu("&Arquivo")
            acao_dashboard = QAction("Dashboard", self)
            acao_dashboard.setShortcut("Ctrl+D")
            acao_dashboard.triggered.connect(self.mostrar_tela_dashboard)
            menu_arquivo.addAction(acao_dashboard)
            menu_arquivo.addSeparator()
            self.acao_mudar_senha = QAction("Alterar Minha Senha...", self)
            self.acao_mudar_senha.triggered.connect(self.abrir_dialogo_mudar_senha)
            menu_arquivo.addAction(self.acao_mudar_senha)
            menu_arquivo.addSeparator()
            acao_logoff = QAction("Fazer Logoff", self)
            acao_logoff.triggered.connect(self.logoff_requested.emit)
            menu_arquivo.addAction(acao_logoff)
            acao_sair = QAction("Sair", self)
            acao_sair.setShortcut(QKeySequence.Quit)
            acao_sair.triggered.connect(self.close)
            menu_arquivo.addAction(acao_sair)
            self.menu_cadastros = menu_bar.addMenu("&Cadastros")
            self.acao_produtos = QAction("Inventário...", self)
            self.acao_produtos.setShortcut("Ctrl+P")
            self.acao_produtos.triggered.connect(self.mostrar_tela_gestao_estoque)
            self.menu_cadastros.addAction(self.acao_produtos)
            self.acao_fornecedores = QAction("Fornecedores...", self)
            self.acao_fornecedores.setShortcut("Ctrl+F")
            self.acao_fornecedores.triggered.connect(self.mostrar_tela_fornecedores)
            self.menu_cadastros.addAction(self.acao_fornecedores)
            self.acao_naturezas = QAction("Naturezas...", self)
            self.acao_naturezas.triggered.connect(self.mostrar_tela_naturezas)
            self.menu_cadastros.addAction(self.acao_naturezas)
            self.acao_setores = QAction("Setores...", self)
            self.acao_setores.triggered.connect(self.mostrar_tela_setores)
            self.menu_cadastros.addAction(self.acao_setores)
            self.menu_cadastros.addSeparator()
            acao_importar = QAction("Importar Produtos de CSV...", self)
            acao_importar.triggered.connect(self.mostrar_tela_importacao)
            self.menu_cadastros.addAction(acao_importar)
            self.menu_cadastros.addSeparator()
            self.acao_usuarios = QAction("Usuários...", self)
            self.acao_usuarios.triggered.connect(self.mostrar_tela_usuarios)
            menu_operacoes = menu_bar.addMenu("&Operações")
            acao_entrada = QAction("Entrada Rápida de Estoque...", self)
            acao_entrada.setShortcut("Ctrl+E")
            acao_entrada.triggered.connect(self.mostrar_tela_entrada_rapida)
            menu_operacoes.addAction(acao_entrada)
            acao_saida = QAction("Saída Rápida de Estoque...", self)
            acao_saida.setShortcut("Ctrl+S")
            acao_saida.triggered.connect(self.mostrar_tela_saida_rapida)
            menu_operacoes.addAction(acao_saida)
            menu_operacoes.addSeparator()
            acao_saldos = QAction("Consultar Inventário...", self)
            acao_saldos.triggered.connect(self.mostrar_tela_gestao_estoque)
            menu_operacoes.addAction(acao_saldos)
            acao_historico = QAction("Ver Histórico de Movimentações...", self)
            acao_historico.triggered.connect(lambda: (self.mostrar_tela_gestao_estoque(), self.tela_gestao_estoque.mostrar_historico()))
            menu_operacoes.addAction(acao_historico)
            menu_relatorios = menu_bar.addMenu("&Relatórios")
            acao_gerar_relatorio = QAction("Gerar Relatório...", self)
            acao_gerar_relatorio.triggered.connect(self.mostrar_tela_relatorios)
            menu_relatorios.addAction(acao_gerar_relatorio)
            menu_ajuda = menu_bar.addMenu("&Ajuda")
            acao_sobre = QAction("Sobre...", self)
            acao_sobre.triggered.connect(self.mostrar_dialogo_sobre)
            menu_ajuda.addAction(acao_sobre)
            widget_central = QWidget()
            self.setCentralWidget(widget_central)
            layout_principal = QHBoxLayout(widget_central)
            painel_lateral = QWidget()
            painel_lateral.setObjectName("painelLateral")
            painel_lateral.setFixedWidth(220)
            self.layout_painel_lateral = QVBoxLayout(painel_lateral)
            self.layout_painel_lateral.setAlignment(Qt.AlignTop)
            self.btn_dashboard = QPushButton("🏠 Dashboard")
            self.btn_inventario = QPushButton("📦 Inventário")
            self.btn_entrada_rapida = QPushButton("➡️ Entrada Rápida")
            self.btn_saida_rapida = QPushButton("⬅️ Saída Rápida")
            self.btn_relatorios = QPushButton("📄 Relatórios")
            self.btn_fornecedores = QPushButton("🚚 Fornecedores")
            self.btn_naturezas = QPushButton("🌿 Naturezas")
            self.btn_terminal = QPushButton("🛰️ Terminal")
            self.btn_usuarios = QPushButton("👥 Usuários")
            self.btn_logoff = QPushButton("🚪 Fazer Logoff")
            self.btn_logoff.setObjectName("btnLogoff")
            self.layout_painel_lateral.addWidget(self.btn_dashboard)
            self.layout_painel_lateral.addWidget(self.btn_inventario)
            self.layout_painel_lateral.addWidget(self.btn_entrada_rapida)
            self.layout_painel_lateral.addWidget(self.btn_saida_rapida)
            self.layout_painel_lateral.addWidget(self.btn_relatorios)
            self.layout_painel_lateral.addWidget(self.btn_fornecedores)
            self.layout_painel_lateral.addWidget(self.btn_naturezas)
            self.layout_painel_lateral.addWidget(self.btn_terminal)
            self.layout_painel_lateral.addStretch(1)
            self.layout_painel_lateral.addWidget(self.btn_logoff)
            layout_principal.addWidget(painel_lateral)
            layout_principal.addWidget(self.stacked_widget)
            self.btn_dashboard.clicked.connect(self.mostrar_tela_dashboard)
            self.btn_inventario.clicked.connect(self.mostrar_tela_gestao_estoque)
            self.btn_entrada_rapida.clicked.connect(self.mostrar_tela_entrada_rapida)
            self.btn_saida_rapida.clicked.connect(self.mostrar_tela_saida_rapida)
            self.btn_relatorios.clicked.connect(self.mostrar_tela_relatorios)
            self.btn_fornecedores.clicked.connect(self.mostrar_tela_fornecedores)
            self.btn_naturezas.clicked.connect(self.mostrar_tela_naturezas)
            self.btn_terminal.clicked.connect(self.mostrar_tela_terminal)
            self.btn_logoff.clicked.connect(self.logoff_requested.emit)
            self.tela_dashboard.ir_para_produtos.connect(self.mostrar_tela_gestao_estoque)
            self.tela_dashboard.ir_para_fornecedores.connect(self.mostrar_tela_fornecedores)
            self.tela_dashboard.ir_para_entrada_rapida.connect(self.mostrar_tela_entrada_rapida)
            self.tela_dashboard.ir_para_saida_rapida.connect(self.mostrar_tela_saida_rapida)
            self.tela_dashboard.ir_para_terminal.connect(self.mostrar_tela_terminal) 
            self.tela_entrada_rapida.estoque_atualizado.connect(self.tela_gestao_estoque.inventario_view.carregar_dados_inventario)
            self.tela_saida_rapida.estoque_atualizado.connect(self.tela_gestao_estoque.inventario_view.carregar_dados_inventario)
            self.tela_importacao.produtos_importados_sucesso.connect(self.tela_gestao_estoque.inventario_view.carregar_dados_inventario)
            signal_handler.fornecedores_atualizados.connect(self.tela_fornecedores.carregar_fornecedores)
            signal_handler.naturezas_atualizadas.connect(self.tela_naturezas.carregar_naturezas)
            signal_handler.setores_atualizados.connect(self.tela_setores.carregar_setores)
            self.statusBar().showMessage("Pronto.")
        except Exception as e:
            error_log_path = os.path.join(os.path.expanduser("~"), "Desktop", "crash_log.txt")
            with open(error_log_path, "w", encoding="utf-8") as f:
                f.write(f"Ocorreu um erro crítico ao iniciar a janela principal:\n\n{e}\n\n{traceback.format_exc()}")
            QMessageBox.critical(self, "Erro de Inicialização", f"Ocorreu um erro crítico. Verifique o ficheiro 'crash_log.txt' no seu Ambiente de Trabalho.")
            sys.exit(1)
    def carregar_dados_usuario(self, dados_usuario):
        self.dados_usuario = dados_usuario
        nome_usuario = self.dados_usuario.get('nome', 'N/A')
        permissao_usuario = self.dados_usuario.get('permissao', 'N/A')
        self.statusBar().showMessage(f"Usuário: {nome_usuario} | Permissão: {permissao_usuario}")
        if self.dados_usuario.get('permissao') == 'Administrador':
            if self.tela_usuarios is None:
                self.tela_usuarios = UsuariosWidget()
                self.stacked_widget.addWidget(self.tela_usuarios)
            self.layout_painel_lateral.insertWidget(self.layout_painel_lateral.count() - 1, self.btn_usuarios)
            self.btn_usuarios.clicked.connect(self.mostrar_tela_usuarios)
            self.menu_cadastros.addAction(self.acao_usuarios)
        else:
            self.btn_usuarios.hide()
    def mostrar_tela_usuarios(self):
        if self.tela_usuarios:
            self.stacked_widget.setCurrentWidget(self.tela_usuarios)
    def mostrar_tela_dashboard(self):
        nome_utilizador = self.dados_usuario.get('nome', 'Utilizador')
        self.tela_dashboard.carregar_dados_dashboard(nome_utilizador)
        self.stacked_widget.setCurrentWidget(self.tela_dashboard)
    def mostrar_tela_entrada_rapida(self):
        self.tela_entrada_rapida.resetar_formulario()
        self.stacked_widget.setCurrentWidget(self.tela_entrada_rapida)
    def mostrar_tela_saida_rapida(self):
        self.tela_saida_rapida.resetar_formulario()
        self.stacked_widget.setCurrentWidget(self.tela_saida_rapida)
    def mostrar_tela_produtos(self):
        self.stacked_widget.setCurrentWidget(self.tela_produtos)
    def mostrar_tela_relatorios(self):
        self.stacked_widget.setCurrentWidget(self.tela_relatorios)
    def mostrar_tela_estoque(self):
        self.tela_estoque.mostrar_saldos() 
        self.stacked_widget.setCurrentWidget(self.tela_estoque)
    def mostrar_tela_fornecedores(self):     
        self.stacked_widget.setCurrentWidget(self.tela_fornecedores)
    def mostrar_tela_naturezas(self):
        self.stacked_widget.setCurrentWidget(self.tela_naturezas)
    def mostrar_dialogo_sobre(self):
        dialog = SobreDialog(self)
        dialog.exec()
    def mostrar_tela_importacao(self):
        self.stacked_widget.setCurrentWidget(self.tela_importacao)
    def mostrar_tela_gestao_estoque(self):
        self.stacked_widget.setCurrentWidget(self.tela_gestao_estoque)
        self.tela_gestao_estoque.mostrar_inventario()
    def abrir_dialogo_mudar_senha(self):
        dialog = MudarSenhaDialog(self)
        dialog.exec()
    def mostrar_tela_terminal(self):
        self.stacked_widget.setCurrentWidget(self.tela_terminal)
        self.tela_terminal.setFocus()
    def mostrar_tela_setores(self):
        self.stacked_widget.setCurrentWidget(self.tela_setores) 
class SobreDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sobre o Sistema")
        self.setMinimumWidth(400)
        self.click_count = 0
        self.sound_effect = QSoundEffect()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.setSpacing(15)
        self.logo_label = QLabel()
        logo_pixmap = QPixmap(resource_path("logo2.png"))
        logo_redimensionada = logo_pixmap.scaled(150, 90, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.logo_label.setPixmap(logo_redimensionada)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setToolTip("Hmmm, o que será que acontece se clicar aqui várias vezes?")
        self.logo_label.installEventFilter(self)
        info_text = QLabel(
            """
            <b>Sistema de Gestão de Estoque v2.5</b>
            <p>Versão 29-01-2026</p>
            <p>Desenvolvido por Matheus com Google Gemini :D.</p>
            <p>Desenvolvido para controle de estoque na Szm.</p>
            <p><b>Tecnologias:</b> Python, PySide6, Flask, SQLAlchemy.</p>
            <p>Agradecimentos especiais a Mathias pela colaboração e testes.</p>
            """
        )
        info_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_text.setWordWrap(True)
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.layout.addWidget(self.logo_label)
        self.layout.addWidget(info_text)
        self.layout.addWidget(self.ok_button, 0, Qt.AlignmentFlag.AlignCenter)
    def eventFilter(self, source, event):
        if source is self.logo_label and event.type() == QEvent.Type.MouseButtonPress:
            self.click_count += 1
            print(f"Logo clicada {self.click_count} vezes.")
            if self.click_count == 10:
                print("Easter Egg Ativado!")
                self.tocar_musica()
                self.click_count = 0
            return True
        return super().eventFilter(source, event)
    def tocar_musica(self):
        try:
            self.sound_effect.setSource(QUrl.fromLocalFile(resource_path("easter_egg.wav")))
            self.sound_effect.setVolume(0.8)
            self.sound_effect.play()
            print("A tocar o ficheiro de áudio easter_egg.wav")
        except Exception as e:
            print(f"Não foi possível tocar o som: {e}")

class InteractiveKPICard(QFrame):
    clicked = Signal()
    def __init__(self, titulo, valor_inicial="--", icone="●"):
        super().__init__()
        self.setObjectName("kpiCard")
        self.setCursor(Qt.PointingHandCursor)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setSpacing(5)
        top_layout = QHBoxLayout()
        self.label_icone = QLabel(icone)
        self.label_icone.setObjectName("kpiIcon")
        self.label_titulo = QLabel(titulo)
        self.label_titulo.setObjectName("kpiTitle")
        top_layout.addWidget(self.label_icone)
        top_layout.addWidget(self.label_titulo)
        top_layout.addStretch(1)
        self.label_valor = QLabel(valor_inicial)
        self.label_valor.setObjectName("kpiValue")
        self.layout.addLayout(top_layout)
        self.layout.addWidget(self.label_valor)
    def set_valor(self, novo_valor):
        self.label_valor.setText(str(novo_valor))
    def mouseReleaseEvent(self, event):
        self.clicked.emit()
        super().mouseReleaseEvent(event)

class DashboardWidget(QWidget):
    ir_para_produtos = Signal()
    ir_para_fornecedores = Signal()
    ir_para_entrada_rapida = Signal()
    ir_para_saida_rapida = Signal()
    ir_para_terminal = Signal()
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setContentsMargins(30, 20, 30, 20)
        self.layout.setSpacing(25)
        self.lista_curiosidades = [
            "A Cidade do Vaticano é o menor país do mundo.",
            "O mel nunca se estraga.",
            "As formigas descansam cerca de 8 minutos a cada 12 horas.",
            "O olho de um avestruz é maior que seu cérebro.",
            "Os polvos têm três corações.",
            "A Grande Muralha da China não é visível da Lua a olho nu.",
            "O som não se propaga no vácuo.",
            "O Brasil tem a maior biodiversidade do mundo.",
            "As borboletas sentem o sabor com os pés.",
            "Um raio é cinco vezes mais quente que a superfície do Sol.",
            "Seu coração bate cerca de 100.000 vezes por dia.",
            "A preguiça pode levar um mês para digerir uma folha.",
            "O Oceano Pacífico é o maior e mais profundo do mundo.",
            "A Torre Eiffel pode ser 15 cm mais alta no verão.",
            "Os camelos têm três pálpebras para se proteger da areia."
        ]
        welcome_card = QFrame()
        welcome_card.setObjectName("welcomeCard")
        welcome_layout = QHBoxLayout(welcome_card)
        logo_label = QLabel()
        logo_pixmap = QPixmap(resource_path("logo.png"))
        logo_redimensionada = logo_pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        logo_label.setPixmap(logo_redimensionada)
        message_layout = QVBoxLayout()
        self.label_boas_vindas = QLabel("Bem-vindo(a)!")
        self.label_boas_vindas.setObjectName("welcomeMessage")
        self.label_curiosidade = QLabel("Você sabia que...")
        self.label_curiosidade.setObjectName("curiosityMessage")
        self.label_curiosidade.setWordWrap(True)
        message_layout.addWidget(self.label_boas_vindas)
        message_layout.addWidget(self.label_curiosidade)
        welcome_layout.addWidget(logo_label)
        welcome_layout.addLayout(message_layout)
        welcome_layout.addStretch(1)
        kpi_title = QLabel("Resumo do Sistema")
        kpi_title.setObjectName("dashboardSectionTitle")
        action_title = QLabel("Operações Comuns")
        action_title.setObjectName("dashboardSectionTitle")
        kpi_layout = QHBoxLayout()
        self.card_produtos = InteractiveKPICard("Produtos", icone="📦")
        self.card_fornecedores = InteractiveKPICard("Fornecedores", icone="🚚")
        self.card_valor_estoque = InteractiveKPICard("Valor do Estoque (R$)", icone="💰")
        kpi_layout.addWidget(self.card_produtos)
        kpi_layout.addWidget(self.card_fornecedores)
        kpi_layout.addWidget(self.card_valor_estoque)
        action_layout = QHBoxLayout()
        self.btn_atalho_entrada = QPushButton("➡️\n\nNova Entrada")
        self.btn_atalho_entrada.setObjectName("btnDashboardAction")
        self.btn_atalho_saida = QPushButton("⬅️\n\nNova Saída")
        self.btn_atalho_saida.setObjectName("btnDashboardAction")
        self.btn_atalho_terminal = QPushButton("🛰️\n\nTerminal de Consulta")
        self.btn_atalho_terminal.setObjectName("btnDashboardAction")
        action_layout.addWidget(self.btn_atalho_entrada)
        action_layout.addWidget(self.btn_atalho_saida)
        action_layout.addWidget(self.btn_atalho_terminal)
        self.layout.addWidget(welcome_card)
        self.layout.addWidget(kpi_title)
        self.layout.addLayout(kpi_layout)
        self.layout.addWidget(action_title)
        self.layout.addLayout(action_layout)
        self.layout.addStretch(1)
        self.card_produtos.clicked.connect(self.ir_para_produtos.emit)
        self.card_fornecedores.clicked.connect(self.ir_para_fornecedores.emit)
        self.btn_atalho_entrada.clicked.connect(self.ir_para_entrada_rapida.emit)
        self.btn_atalho_saida.clicked.connect(self.ir_para_saida_rapida.emit)
        self.btn_atalho_terminal.clicked.connect(self.ir_para_terminal.emit)
    def atualizar_mensagem_boas_vindas(self, nome_utilizador):
        primeiro_nome = nome_utilizador.split(" ")[0]
        curiosidade = random.choice(self.lista_curiosidades)
        self.label_boas_vindas.setText(f"Bem-vindo(a), {primeiro_nome}!")
        self.label_curiosidade.setText(f"<i>Você sabia que... {curiosidade}</i>")
    def carregar_dados_dashboard(self, nome_utilizador):
        self.atualizar_mensagem_boas_vindas(nome_utilizador)
        self.carregar_kpis()
    def carregar_kpis(self):
        global access_token
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_BASE_URL}/api/dashboard/kpis", headers=headers, timeout=5)
            if response and response.status_code == 200:
                dados = response.json()
                self.card_produtos.set_valor(dados.get('total_produtos', 0))
                self.card_fornecedores.set_valor(dados.get('total_fornecedores', 0))
                valor_formatado = f"R$ {dados.get('valor_total_estoque', 0):.2f}".replace('.', ',')
                self.card_valor_estoque.set_valor(valor_formatado)
        except requests.exceptions.RequestException:
            show_connection_error_message(self)

# ==============================================================================
# 6. CLASSE DA JANELA DE LOGIN
# ==============================================================================

class AppManager:
    def __init__(self):
        self.login_window = None
        self.main_window = None
    def start(self):
        self.show_login_window()
    def show_login_window(self):
        self.login_window = JanelaLogin()
        self.login_window.login_successful.connect(self.show_main_window)
        self.login_window.show()
    def show_main_window(self, user_data):
        self.main_window = JanelaPrincipal()
        self.main_window.carregar_dados_usuario(user_data)
        self.main_window.show()
        self.main_window.mostrar_tela_dashboard()
        self.main_window.logoff_requested.connect(self.handle_logoff)
        self.login_window.close()
        check_for_updates()
    def handle_logoff(self):
        if self.main_window:
            self.main_window.close()
        self.show_login_window()

class JanelaLogin(QMainWindow):
    """
    Tela de Login Redesenhada - Estilo Card Centralizado (Moderno e Elegante)
    """
    login_successful = Signal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login - Sistema de Estoque")
        # Removemos o ícone daqui para deixar o estilo controlar, ou defina se preferir
        
        # 1. Widget Central com ID para o Fundo Gradiente
        self.central_widget = QWidget()
        self.central_widget.setObjectName("loginBackground")
        self.setCentralWidget(self.central_widget)

        # Layout principal para centralizar o cartão
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 2. O Cartão de Login (Card Branco)
        self.login_card = QFrame()
        self.login_card.setObjectName("loginCard")
        
        # Adiciona Sombra ao Cartão para efeito de elevação ("Elegância")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(5)
        shadow.setColor(QColor(0, 0, 0, 60)) # Sombra suave
        self.login_card.setGraphicsEffect(shadow)

        # Layout interno do cartão
        self.card_layout = QVBoxLayout(self.login_card)
        self.card_layout.setSpacing(10)
        self.card_layout.setContentsMargins(40, 40, 40, 40)

        # --- Elementos do Cartão ---

        # Logo (Centralizada)
        self.logo_label = QLabel()
        try:
            logo_pixmap = QPixmap(resource_path("logo.png"))
            if not logo_pixmap.isNull():
                # Redimensiona proporcionalmente
                logo_redimensionada = logo_pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.logo_label.setPixmap(logo_redimensionada)
                self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.logo_label.setObjectName("loginLogo")
                self.card_layout.addWidget(self.logo_label)
        except Exception:
            pass # Se não tiver logo, segue sem erro

        # Título e Subtítulo
        self.titulo = QLabel("Bem-vindo")
        self.titulo.setObjectName("loginTitle")
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.subtitulo = QLabel("Insira suas credenciais para acessar")
        self.subtitulo.setObjectName("loginSubtitle")
        self.subtitulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Campos de Entrada
        self.input_login = QLineEdit()
        self.input_login.setPlaceholderText("Usuário")
        self.input_login.setObjectName("loginInput")
        # Ícones ou styling extra podem ser feitos via CSS, mantemos limpo aqui

        self.input_senha = QLineEdit()
        self.input_senha.setPlaceholderText("Senha")
        self.input_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_senha.setObjectName("loginInput")

        # Botão de Ação
        self.botao_login = QPushButton("ENTRAR NO SISTEMA")
        self.botao_login.setObjectName("loginButton")
        self.botao_login.setCursor(Qt.PointingHandCursor)

        # Footer (Copyright ou Versão)
        self.footer = QLabel(f"Versão {APP_VERSION} © 2025")
        self.footer.setObjectName("loginFooter")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Adicionando tudo ao layout do cartão
        self.card_layout.addWidget(self.titulo)
        self.card_layout.addWidget(self.subtitulo)
        self.card_layout.addSpacing(10)
        self.card_layout.addWidget(self.input_login)
        self.card_layout.addWidget(self.input_senha)
        self.card_layout.addWidget(self.botao_login)
        self.card_layout.addSpacing(10)
        self.card_layout.addWidget(self.footer)

        # Adiciona o cartão ao layout principal da janela
        self.main_layout.addWidget(self.login_card)

        # Conexões
        self.botao_login.clicked.connect(self.fazer_login)
        self.input_senha.returnPressed.connect(self.botao_login.click)
        self.input_login.returnPressed.connect(self.input_senha.setFocus)

    def fazer_login(self):
        global access_token
        login = self.input_login.text().strip()
        senha = self.input_senha.text().strip()

        if not login or not senha:
            # Feedback visual simples (tremida ou borda vermelha seria ideal, mas alerta serve)
            QMessageBox.warning(self, "Atenção", "Por favor, preencha usuário e senha.")
            return

        # Feedback visual de carregamento
        self.botao_login.setText("Verificando...")
        self.botao_login.setEnabled(False)
        QApplication.processEvents()

        url = f"{API_BASE_URL}/api/login"
        dados = {"login": login, "senha": senha}

        try:
            # Timeout curto para não travar muito a UI se o servidor estiver off
            response = requests.post(url, json=dados, timeout=5)
            
            if response and response.status_code == 200:
                access_token = response.json()['access_token']
                
                # Pega dados do usuário
                headers = {'Authorization': f'Bearer {access_token}'}
                try:
                    resp_me = requests.get(f"{API_BASE_URL}/api/usuario/me", headers=headers, timeout=5)
                    user_data = resp_me.json() if resp_me.status_code == 200 else {'nome': login, 'permissao': 'Usuario'}
                except:
                    user_data = {'nome': login, 'permissao': 'Usuario'}

                self.login_successful.emit(user_data)
                self.close()
            else:
                erro = response.json().get('erro', 'Credenciais inválidas') if response else "Erro desconhecido"
                QMessageBox.warning(self, "Acesso Negado", f"{erro}")
        
        except requests.exceptions.ConnectionError:
            QMessageBox.critical(self, "Erro de Conexão", 
                "Não foi possível conectar ao servidor.\nVerifique se o backend está rodando no IP correto.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Ocorreu um erro inesperado:\n{e}")
        
        finally:
            # Reseta o botão independente do resultado
            self.botao_login.setText("ENTRAR NO SISTEMA")
            self.botao_login.setEnabled(True)
# ==============================================================================
# 7. BLOCO DE EXECUÇÃO PRINCIPAL
# ==============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        with open(resource_path("style.qss"), "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("AVISO: Arquivo de estilo (style.qss) não encontrado.")
    manager = AppManager()
    manager.start()
    sys.exit(app.exec())
