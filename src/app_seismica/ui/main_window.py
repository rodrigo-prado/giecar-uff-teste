from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QProgressBar,
    QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import QThreadPool

from app_seismica.core.models import JobStatus, SeismicDataset
from app_seismica.core.segy_reader import inspect_segy_metadata
from app_seismica.services.job_service import FilterJobService
from app_seismica.ui.worker import FilterWorker


class MainWindow(QMainWindow):
    def __init__(self, service: FilterJobService):
        super().__init__()
        self.service = service
        self.current_dataset: Optional[SeismicDataset] = None
        self.current_worker: Optional[FilterWorker] = None
        self.active_job_id: Optional[str] = None
        self.threadpool = QThreadPool.globalInstance()

        self.setWindowTitle("Processamento Sísmico - Filtro Passa-Baixa Butterworth")
        self.resize(500, 420)

        main_layout = QVBoxLayout()

        # Seção 1: Selecionar Arquivo
        group_import = QGroupBox("1. Selecionar Arquivo SEG-Y")
        layout_import = QVBoxLayout()
        self.btn_select_file = QPushButton("Importar Arquivo .sgy / .segy")
        self.btn_select_file.clicked.connect(self.on_select_file)
        self.lbl_file_info = QLabel("Nenhum arquivo carregado.")
        self.lbl_file_info.setWordWrap(True)
        layout_import.addWidget(self.btn_select_file)
        layout_import.addWidget(self.lbl_file_info)
        group_import.setLayout(layout_import)
        main_layout.addWidget(group_import)

        # Seção 2: Configurar Parâmetros do Filtro
        self.group_filter = QGroupBox("2. Parâmetros do Filtro Butterworth")
        self.group_filter.setEnabled(False)
        layout_filter = QVBoxLayout()

        layout_filter.addWidget(QLabel("Frequência de Corte (Hz):"))
        self.spn_cutoff = QDoubleSpinBox()
        self.spn_cutoff.setRange(0.1, 1000.0)
        self.spn_cutoff.setDecimals(1)
        self.spn_cutoff.setValue(40.0)
        layout_filter.addWidget(self.spn_cutoff)

        layout_filter.addWidget(QLabel("Ordem do Filtro (Ex: 2 a 8):"))
        self.spn_order = QSpinBox()
        self.spn_order.setRange(1, 12)
        self.spn_order.setValue(4)
        layout_filter.addWidget(self.spn_order)

        self.group_filter.setLayout(layout_filter)
        main_layout.addWidget(self.group_filter)

        # Seção 3: Execução e Controle
        group_exec = QGroupBox("3. Execução")
        layout_exec = QVBoxLayout()

        btn_box = QHBoxLayout()
        self.btn_executar = QPushButton("Executar")
        self.btn_executar.setEnabled(False)
        self.btn_executar.clicked.connect(self.on_executar)
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.clicked.connect(self.on_cancelar)
        btn_box.addWidget(self.btn_executar)
        btn_box.addWidget(self.btn_cancelar)
        layout_exec.addLayout(btn_box)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout_exec.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Aguardando importação...")
        layout_exec.addWidget(self.lbl_status)

        group_exec.setLayout(layout_exec)
        main_layout.addWidget(group_exec)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def on_select_file(self):
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        default_dir = project_root / "data" / "raw"
        default_dir.mkdir(parents=True, exist_ok=True)

        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Selecionar Arquivo SEG-Y", 
            str(default_dir), 
            "Arquivos Sísmicos (*.sgy *.segy)"
        )

        if not file_path:
            return

        try:
            self.current_dataset = inspect_segy_metadata(Path(file_path))
            self.service.register_dataset(self.current_dataset)

            nyq = self.current_dataset.nyquist_frequency_hz
            self.lbl_file_info.setText(
                f"<b>Arquivo:</b> {self.current_dataset.name}<br>"
                f"<b>Amostragem:</b> {self.current_dataset.sample_rate_ms} ms | "
                f"<b>Nyquist:</b> {nyq:.1f} Hz<br>"
                f"<b>Total de Traços:</b> {self.current_dataset.total_traces:,} | "
                f"<b>Amostras/traço:</b> {self.current_dataset.n_samples}"
            )

            self.spn_cutoff.setMaximum(nyq - 0.1)
            self.spn_cutoff.setValue(min(45.0, nyq / 2.0))

            self.group_filter.setEnabled(True)
            self.btn_executar.setEnabled(True)
            self.lbl_status.setText("Arquivo importado. Configure os parâmetros e clique em Executar.")

        except Exception as e:
            QMessageBox.critical(self, "Erro ao ler SEG-Y", f"Falha ao ler cabeçalhos:\n{str(e)}")

    def on_executar(self):
        cutoff = self.spn_cutoff.value()
        order = self.spn_order.value()

        if cutoff >= self.current_dataset.nyquist_frequency_hz:
            QMessageBox.critical(
                self, "Validação Inválida",
                f"O corte ({cutoff} Hz) não pode ser maior ou igual a Nyquist ({self.current_dataset.nyquist_frequency_hz:.1f} Hz)."
            )
            return

        try:
            job = self.service.create_filter_job(self.current_dataset.id, cutoff, order)
            self.active_job_id = job.id

            self.btn_executar.setEnabled(False)
            self.btn_select_file.setEnabled(False)
            self.btn_cancelar.setEnabled(True)
            self.progress_bar.setValue(0)
            self.lbl_status.setText("Processando chunks de traços...")

            self.current_worker = FilterWorker(self.service, job.id)
            self.current_worker.signals.progress.connect(self.on_progresso)
            self.current_worker.signals.finished.connect(self.on_sucesso)
            self.current_worker.signals.error.connect(self.on_erro)

            self.threadpool.start(self.current_worker)

        except Exception as e:
            QMessageBox.critical(self, "Erro ao criar Job", str(e))

    def on_cancelar(self):
        if self.active_job_id and self.current_worker:
            self.service.cancel_job(self.active_job_id)
            self.current_worker.cancel_token.set()
            self.lbl_status.setText("Cancelamento solicitado. Interrompendo...")
            self.btn_cancelar.setEnabled(False)

    def on_progresso(self, pct: float):
        self.progress_bar.setValue(int(pct))

    def on_sucesso(self):
        job = self.service.get_job_status(self.active_job_id)
        self._restaurar_estado_ui()
        if job.status == JobStatus.COMPLETED:
            self.lbl_status.setText(f"Concluído! Salvo em: {job.output_path}")
            QMessageBox.information(self, "Sucesso", f"Filtragem finalizada!\nResultado salvo em:\n{job.output_path}")
        elif job.status == JobStatus.CANCELLED:
            self.lbl_status.setText("Processamento cancelado pelo usuário.")
            QMessageBox.warning(self, "Cancelado", "A execução foi abortada e o arquivo parcial foi limpo.")

    def on_erro(self, msg: str):
        self._restaurar_estado_ui()
        self.lbl_status.setText("Falha na execução.")
        QMessageBox.critical(self, "Erro no Processamento", f"Ocorreu um erro durante a filtragem:\n{msg}")

    def _restaurar_estado_ui(self):
        self.btn_executar.setEnabled(True)
        self.btn_select_file.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
