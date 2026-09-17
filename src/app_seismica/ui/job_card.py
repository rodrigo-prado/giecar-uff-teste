from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton
from PySide6.QtCore import Qt

class JobCard(QFrame):
    def __init__(self, filename, cutoff, order, n_workers=1, parent=None):
        super().__init__(parent)
        self.is_paused = False
        
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        
        header_layout = QHBoxLayout()
        title = QLabel(filename)
        params = QLabel(f"Corte: {cutoff} Hz | Ordem: {order} | Processos: {n_workers}")
        params.setAlignment(Qt.AlignRight)
        
        header_layout.addWidget(title)
        header_layout.addWidget(params)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("Aguardando execução...")
        
        self.btn_pause = QPushButton("Pausar")
        self.btn_cancel = QPushButton("Cancelar")
        
        self.btn_view = QPushButton("Visualizar")
        self.btn_view.hide()
        
        # Conexões serão feitas pela MainWindow
        
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_view)
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
                current_text = self.status_label.text()
                if "(" in current_text:
                    timer_part = current_text.split("(")[1]
                    self.update_status(f"Em Pausa... ({timer_part}")
                else:
                    self.update_status("Em Pausa...")
            else:
                self.btn_pause.setText("Pausar")
                current_text = self.status_label.text()
                if "(" in current_text:
                    timer_part = current_text.split("(")[1]
                    self.update_status(f"Processando (Retomado)... ({timer_part}")
                else:
                    self.update_status("Processando (Retomado)...")
            callback(self.is_paused)
        self.btn_pause.clicked.connect(on_pause)
        
    def set_cancel_callback(self, callback):
        self.btn_cancel.clicked.connect(callback)
        
    def set_view_callback(self, callback):
        self.btn_view.clicked.connect(callback)

    def update_progress(self, value, duration_sec):
        self.progress_bar.setValue(value)
        if duration_sec is not None:
            if self.is_paused:
                self.status_label.setText(f"Em Pausa... ({duration_sec:.1f}s)")
            else:
                self.status_label.setText(f"Processando... ({duration_sec:.1f}s)")

    def update_status(self, text):
        self.status_label.setText(text)
        
    def set_cancelled(self):
        self.status_label.setText("Cancelado.")
        self.btn_pause.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_view.hide()
        
    def set_finished(self, output_path, duration_sec=None):
        self.progress_bar.setValue(100)
        dur_str = f" em {duration_sec:.1f}s" if duration_sec else ""
        self.status_label.setText(f"Concluído{dur_str}! Salvo em: {output_path}")
        self.btn_pause.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_view.show()
        
    def set_error(self, error_msg):
        self.status_label.setText(f"Erro: {error_msg}")
        self.btn_pause.setEnabled(False)
        self.btn_cancel.setEnabled(False)
        self.btn_view.hide()

