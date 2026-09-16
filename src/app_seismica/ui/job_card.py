from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Qt

class JobCard(QFrame):
    def __init__(self, filename, cutoff, order, parent=None):
        super().__init__(parent)
        self.is_paused = False
        
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        
        header_layout = QHBoxLayout()
        title = QLabel(filename)
        params = QLabel(f"Corte: {cutoff} Hz | Ordem: {order}")
        params.setAlignment(Qt.AlignRight)
        
        header_layout.addWidget(title)
        header_layout.addWidget(params)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("Aguardando execução...")
        
        self.btn_pause = QPushButton("Pausar")
        self.btn_cancel = QPushButton("Cancelar")
        
        # Conexões serão feitas pela MainWindow
        
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_pause)
        bottom_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(header_layout)
        layout.addWidget(self.progress_bar)
        layout.addLayout(bottom_layout)

    def set_pause_callback(self, callback):
        def on_pause():
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.btn_pause.setText("Retomar")
                self.update_status("Em Pausa...")
            else:
                self.btn_pause.setText("Pausar")
                self.update_status("Processando...")
            callback(self.is_paused)
        self.btn_pause.clicked.connect(on_pause)
        
    def set_cancel_callback(self, callback):
        self.btn_cancel.clicked.connect(callback)

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_status(self, text):
        self.status_label.setText(text)
        
    def set_finished(self, output_path):
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Concluído! Salvo em: {output_path}")
        self.btn_pause.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        
    def set_error(self, error_msg):
        self.status_label.setText(f"Erro: {error_msg}")
        self.btn_pause.setEnabled(False)
        self.btn_cancel.setEnabled(False)

