from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QScrollArea,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton, 
    QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import QThreadPool, Qt

from app_seismica.core.models import JobStatus, SeismicDataset
from app_seismica.core.segy_reader import inspect_segy_metadata
from app_seismica.services.job_service import FilterJobService
from app_seismica.ui.worker import FilterWorker
from app_seismica.ui.job_card import JobCard


class MainWindow(QMainWindow):
    def __init__(self, service: FilterJobService):
        super().__init__()
        self.service = service
        self.current_dataset: Optional[SeismicDataset] = None
        self.current_worker: Optional[FilterWorker] = None
        self.active_job_id: Optional[str] = None
        self.threadpool = QThreadPool.globalInstance()

        self.setWindowTitle("Processamento Sísmico - Filtro Passa-Baixa Butterworth")
        self.resize(1000, 800)

        main_layout = QVBoxLayout()

        # Seção 1: Selecionar Arquivo
        group_import = QGroupBox("Selecionar Arquivo SEG-Y")
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
        self.group_filter = QGroupBox("Parâmetros do Filtro Butterworth")
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

        # Botão para adicionar o job foi movido para cá
        self.btn_executar = QPushButton("Adicionar à Fila")
        self.btn_executar.setEnabled(False)
        self.btn_executar.clicked.connect(self.on_executar)
        layout_filter.addWidget(self.btn_executar)

        self.group_filter.setLayout(layout_filter)
        main_layout.addWidget(self.group_filter)

        # Seção 3: Execução e Controle
        group_exec = QGroupBox("Fila de Processamento")
        layout_exec = QVBoxLayout()

        # --- A Fila de Processamento (ScrollArea) ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumHeight(200) # Garante um espaço visual bacana
        
        # O container que vai segurar os cards lá dentro
        self.jobs_container = QWidget()
        self.jobs_layout = QVBoxLayout(self.jobs_container)
        self.jobs_layout.setAlignment(Qt.AlignTop) # Empilha os cards de cima para baixo
        
        self.scroll_area.setWidget(self.jobs_container)
        layout_exec.addWidget(self.scroll_area)
        # ----------------------------------------------------------

        group_exec.setLayout(layout_exec)
        main_layout.addWidget(group_exec)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self._restore_jobs()

    def _restore_jobs(self):
        jobs = self.service.list_jobs()
        for job in jobs:
            dataset = self.service._datasets.get(job.dataset_id)
            if not dataset:
                continue
                
            card = JobCard(dataset.name, job.cutoff_hz, job.order)
            self.jobs_layout.insertWidget(0, card)
            
            if job.status == JobStatus.COMPLETED:
                card.set_finished(job.output_path)
            elif job.status == JobStatus.CANCELLED:
                card.set_cancelled()
            elif job.status == JobStatus.FAILED:
                card.set_error(job.error_message or "Processo interrompido/falhou.")

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
                f"Arquivo: {self.current_dataset.name} | "
                f"Amostragem: {self.current_dataset.sample_rate_ms} ms | "
                f"Nyquist: {nyq:.1f} Hz | "
                f"Total de Traços: {self.current_dataset.total_traces:,} | "
                f"Amostras/traço: {self.current_dataset.n_samples}"
            )

            self.spn_cutoff.setMaximum(nyq - 0.1)
            self.spn_cutoff.setValue(min(45.0, nyq / 2.0))

            self.group_filter.setEnabled(True)
            self.btn_executar.setEnabled(True)

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

            # Criar e adicionar o card à UI no topo
            card = JobCard(self.current_dataset.name, cutoff, order)
            self.jobs_layout.insertWidget(0, card)
            card.update_status("Processando chunks de traços...")

            # Mantém referência dos workers ativos se quiser cancelar todos
            if not hasattr(self, 'active_workers'):
                self.active_workers = {}
            
            worker = FilterWorker(self.service, job.id)
            self.active_workers[job.id] = {"worker": worker, "card": card}

            # Configurações do Worker
            worker.signals.progress.connect(card.update_progress)
            
            # Callbacks dos botões do Card
            def on_pause_toggled(is_paused):
                if is_paused:
                    worker.pause_token.clear() # Vermelho = bloqueia thread
                else:
                    worker.pause_token.set()   # Verde = libera thread
                    
            def on_cancel_clicked():
                self.service.cancel_job(job.id)
                worker.cancel_token.set()
                worker.pause_token.set() # Precisa destravar se estiver pausado para poder cancelar
                card.update_status("Cancelamento solicitado...")
                card.btn_pause.setEnabled(False)
                card.btn_cancel.setEnabled(False)

            card.set_pause_callback(on_pause_toggled)
            card.set_cancel_callback(on_cancel_clicked)
            
            # Precisamos usar um wrapper para passar o job_id correto nos sinais
            def on_finished(jid=job.id):
                self.on_sucesso(jid)
            def on_err(msg, jid=job.id):
                self.on_erro(msg, jid)
                
            worker.signals.finished.connect(on_finished)
            worker.signals.error.connect(on_err)

            self.threadpool.start(worker)

        except Exception as e:
            QMessageBox.critical(self, "Erro ao criar Job", str(e))

    def on_sucesso(self, job_id):
        job = self.service.get_job_status(job_id)
        
        if hasattr(self, 'active_workers') and job_id in self.active_workers:
            card = self.active_workers[job_id]["card"]
            if job.status == JobStatus.COMPLETED:
                card.set_finished(job.output_path)
            elif job.status == JobStatus.CANCELLED:
                card.set_cancelled()
            del self.active_workers[job_id]

    def on_erro(self, msg: str, job_id: str):
        if hasattr(self, 'active_workers') and job_id in self.active_workers:
            self.active_workers[job_id]["card"].set_error(msg)
            del self.active_workers[job_id]

    def _restaurar_estado_ui(self):
        self.btn_executar.setEnabled(True)
        self.btn_select_file.setEnabled(True)
