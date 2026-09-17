from pathlib import Path
from typing import Optional
import os
import psutil

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton, 
    QFileDialog, QMessageBox, QGroupBox, QLineEdit, QComboBox,
    QStatusBar
)
from PySide6.QtCore import QThreadPool, Qt, QTimer

from app_seismica.core.models import JobStatus, SeismicDataset
from app_seismica.core.segy_reader import inspect_segy_metadata
from app_seismica.services.job_service import FilterJobService
from app_seismica.ui.worker import FilterWorker
from app_seismica.ui.job_card import JobCard
from app_seismica.ui.trace_viewer import TraceViewerDialog


class MainWindow(QMainWindow):
    def __init__(self, service: FilterJobService):
        super().__init__()
        self.service = service
        self.current_dataset: Optional[SeismicDataset] = None
        self.current_worker: Optional[FilterWorker] = None
        self.active_job_id: Optional[str] = None
        self.threadpool = QThreadPool.globalInstance()

        self.setWindowTitle("Processamento Sísmico - Filtro Passa-Baixa Butterworth")
        self.resize(1400, 800)

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
        
        layout_filter.addWidget(QLabel("Número de Processos (Workers):"))
        self.spn_workers = QSpinBox()
        self.spn_workers.setRange(1, 32)
        self.spn_workers.setValue(4)
        layout_filter.addWidget(self.spn_workers)

        layout_filter.addWidget(QLabel("Tamanho do Lote (Chunk Size):"))
        self.spn_chunk_size = QSpinBox()
        self.spn_chunk_size.setRange(10, 1000000)
        self.spn_chunk_size.setSingleStep(100)
        self.spn_chunk_size.setValue(500)
        layout_filter.addWidget(self.spn_chunk_size)

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

        # --- Filtros ---
        layout_filtros = QHBoxLayout()
        layout_filtros.addWidget(QLabel("Filtrar por:"))
        
        self.txt_filter_id = QLineEdit()
        self.txt_filter_id.setPlaceholderText("ID do Job")
        self.txt_filter_id.textChanged.connect(self.apply_filters)
        layout_filtros.addWidget(self.txt_filter_id)

        self.txt_filter_dataset = QLineEdit()
        self.txt_filter_dataset.setPlaceholderText("Nome do Dataset")
        self.txt_filter_dataset.textChanged.connect(self.apply_filters)
        layout_filtros.addWidget(self.txt_filter_dataset)

        self.cmb_filter_status = QComboBox()
        self.cmb_filter_status.addItem("Todos os Status", None)
        for status in JobStatus:
            self.cmb_filter_status.addItem(status.name, status)
        self.cmb_filter_status.currentIndexChanged.connect(self.apply_filters)
        layout_filtros.addWidget(self.cmb_filter_status)

        layout_exec.addLayout(layout_filtros)

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

        self.all_job_cards = {}  # Mapeia job_id -> JobCard

        self._restore_jobs()
        
        # Configuração do Monitoramento de Memória no Rodapé
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.process = psutil.Process(os.getpid())
        self.peak_memory_mb = 0.0
        
        self.memory_timer = QTimer(self)
        self.memory_timer.timeout.connect(self.update_memory_usage)
        self.memory_timer.start(1000) # Atualiza a cada 1 segundo

    def update_memory_usage(self):
        try:
            current_mem_mb = self.process.memory_info().rss / (1024 * 1024)
            if current_mem_mb > self.peak_memory_mb:
                self.peak_memory_mb = current_mem_mb
                
            self.status_bar.showMessage(
                f"Uso de Memória RAM (App): {current_mem_mb:.1f} MB  |  Pico Histórico: {self.peak_memory_mb:.1f} MB"
            )
        except Exception:
            pass

    def apply_filters(self):
        filter_id = self.txt_filter_id.text().strip().lower()
        filter_dataset_name = self.txt_filter_dataset.text().strip().lower()
        filter_status = self.cmb_filter_status.currentData()

        for job_id, card in self.all_job_cards.items():
            job = self.service._jobs.get(job_id)
            if not job:
                continue
            
            dataset = self.service._datasets.get(job.dataset_id)
            dataset_name = dataset.name.lower() if dataset else ""
            
            show = True
            if filter_id and filter_id not in job.id.lower():
                show = False
            if filter_dataset_name and filter_dataset_name not in dataset_name:
                show = False
            if filter_status and job.status != filter_status:
                show = False
                
            card.setVisible(show)

    def _restore_jobs(self):
        jobs = self.service.list_jobs()
        for job in jobs:
            dataset = self.service._datasets.get(job.dataset_id)
            if not dataset:
                continue
                
            card = JobCard(f"[{job.id}] {dataset.name}", job.cutoff_hz, job.order, job.n_workers)
            self.jobs_layout.insertWidget(0, card)
            self.all_job_cards[job.id] = card
            
            def open_viewer(checked=False, j=job, ds=dataset):
                dialog = TraceViewerDialog(ds.source_path, j.output_path, ds.total_traces, self)
                dialog.exec()
            
            card.set_view_callback(open_viewer)
            
            if job.status == JobStatus.COMPLETED:
                card.set_finished(job.output_path, job.duration_sec)
            elif job.status == JobStatus.CANCELLED:
                card.set_cancelled()
            elif job.status == JobStatus.FAILED:
                card.set_error(job.error_message or "Processo interrompido/falhou.")
        
        self.apply_filters()

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
        n_workers = self.spn_workers.value()
        chunk_size = self.spn_chunk_size.value()

        if cutoff >= self.current_dataset.nyquist_frequency_hz:
            QMessageBox.critical(
                self, "Validação Inválida",
                f"O corte ({cutoff} Hz) não pode ser maior ou igual a Nyquist ({self.current_dataset.nyquist_frequency_hz:.1f} Hz)."
            )
            return

        try:
            job = self.service.create_filter_job(self.current_dataset.id, cutoff, order, n_workers, chunk_size)

            # Criar e adicionar o card à UI no topo
            card = JobCard(f"[{job.id}] {self.current_dataset.name}", cutoff, order, job.n_workers)
            self.jobs_layout.insertWidget(0, card)
            self.all_job_cards[job.id] = card
            card.update_status("Processando chunks de traços...")
            
            self.apply_filters()

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
            
            def open_viewer(checked=False):
                dialog = TraceViewerDialog(self.current_dataset.source_path, job.output_path, self.current_dataset.total_traces, self)
                dialog.exec()
            card.set_view_callback(open_viewer)
            
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
                card.set_finished(job.output_path, job.duration_sec)
            elif job.status == JobStatus.CANCELLED:
                card.set_cancelled()
            del self.active_workers[job_id]
            self.apply_filters()

    def on_erro(self, msg: str, job_id: str):
        if hasattr(self, 'active_workers') and job_id in self.active_workers:
            self.active_workers[job_id]["card"].set_error(msg)
            del self.active_workers[job_id]
            self.apply_filters()

    def _restaurar_estado_ui(self):
        self.btn_executar.setEnabled(True)
        self.btn_select_file.setEnabled(True)
