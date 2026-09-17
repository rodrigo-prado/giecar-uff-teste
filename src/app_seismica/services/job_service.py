import threading
from pathlib import Path
from typing import Dict, List, Optional, Callable
import h5py
import numpy as np
from scipy import signal
import segyio
import time
import concurrent.futures
from collections import deque
import logging

from app_seismica.core.models import Job, JobStatus, SeismicDataset, FilterParameters
from app_seismica.core.database import init_db, DBDataset, DBJob

ProgressCallback = Callable[[float, float], None]

def apply_sos_filter(sos, chunk):
    return signal.sosfiltfilt(sos, chunk, axis=1)

class FilterJobService:
    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        output_dir = project_root / "data" / "processed"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logs_dir = project_root / "data" / "logs" / "jobs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize SQLite database
        db_path = f"sqlite:///{project_root / 'data' / 'metadata.db'}"
        self.SessionLocal = init_db(db_path)
        
        self._datasets: Dict[str, SeismicDataset] = {}
        self._jobs: Dict[str, Job] = {}
        self._cancel_tokens: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        
        self._load_from_db()

    def _load_from_db(self):
        with self.SessionLocal() as session:
            db_datasets = session.query(DBDataset).all()
            for db_dset in db_datasets:
                dataset = SeismicDataset(
                    id=db_dset.id,
                    name=db_dset.name,
                    source_path=Path(db_dset.source_path),
                    n_inlines=db_dset.n_inlines,
                    n_crosslines=db_dset.n_crosslines,
                    n_samples=db_dset.n_samples,
                    sample_rate_ms=db_dset.sample_rate_ms
                )
                self._datasets[dataset.id] = dataset

            db_jobs = session.query(DBJob).all()
            for db_job in db_jobs:
                try:
                    status = JobStatus[db_job.status]
                except KeyError:
                    status = JobStatus.FAILED
                
                # Se o app foi fechado enquanto rodava ou estava na fila, marcamos como falha
                if status in (JobStatus.RUNNING, JobStatus.CREATED):
                    status = JobStatus.FAILED
                    db_job.status = status.name
                    session.commit()
                    
                    # Registra a falha no log do respectivo job
                    job_id_str = str(db_job.id)
                    logger = self._get_job_logger(job_id_str)
                    logger.error("Job marcado como FAILED (Falha) pois a aplicação foi encerrada inesperadamente antes da sua conclusão.")
                    self._close_job_logger(job_id_str)

                job_id = str(db_job.id)
                job = Job(
                    id=job_id,
                    dataset_id=db_job.dataset_id,
                    cutoff_hz=db_job.cutoff_hz,
                    order=db_job.order,
                    n_workers=db_job.n_workers or 1,
                    status=status,
                    progress=100.0 if status == JobStatus.COMPLETED else 0.0,
                    output_path=Path(db_job.output_path) if db_job.output_path else None,
                    duration_sec=db_job.duration_sec
                )
                self._jobs[job_id] = job
                self._cancel_tokens[job_id] = threading.Event()

    def _get_job_logger(self, job_id: str) -> logging.Logger:
        logger_name = f"JobLogger_{job_id}"
        logger = logging.getLogger(logger_name)
        
        # Se o logger já tem handlers configurados, retornamos para não duplicar
        if logger.handlers:
            return logger
            
        logger.setLevel(logging.INFO)
        log_file = self.logs_dir / f"job_{job_id}.log"
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        
        # Remove propagation to avoid cluttering root logger
        logger.propagate = False
        return logger

    def _close_job_logger(self, job_id: str):
        logger_name = f"JobLogger_{job_id}"
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    def register_dataset(self, dataset: SeismicDataset) -> None:
        with self._lock:
            self._datasets[dataset.id] = dataset
            
            with self.SessionLocal() as session:
                db_dset = session.query(DBDataset).filter_by(id=dataset.id).first()
                if not db_dset:
                    db_dset = DBDataset(
                        id=dataset.id,
                        name=dataset.name,
                        source_path=str(dataset.source_path),
                        n_inlines=dataset.n_inlines,
                        n_crosslines=dataset.n_crosslines,
                        n_samples=dataset.n_samples,
                        sample_rate_ms=dataset.sample_rate_ms
                    )
                    session.add(db_dset)
                    session.commit()

    def create_filter_job(self, dataset_id: str, cutoff_hz: float, order: int, n_workers: int = 1) -> Job:
        with self._lock:
            dataset = self._datasets.get(dataset_id)
            if not dataset:
                raise KeyError(f"Dataset '{dataset_id}' não encontrado.")

            # Validação estrita da regra de negócio
            params = FilterParameters(cutoff_hz=cutoff_hz, order=order)
            params.validate_against_nyquist(dataset.nyquist_frequency_hz)

            with self.SessionLocal() as session:
                db_job = DBJob(
                    dataset_id=dataset_id,
                    cutoff_hz=cutoff_hz,
                    order=order,
                    n_workers=n_workers,
                    status=JobStatus.CREATED.name
                )
                session.add(db_job)
                session.commit()
                session.refresh(db_job)
                job_id = str(db_job.id)

            job = Job(
                id=job_id,
                dataset_id=dataset_id,
                cutoff_hz=cutoff_hz,
                order=order,
                n_workers=n_workers,
                status=JobStatus.CREATED,
                progress=0.0
            )
            self._jobs[job_id] = job
            self._cancel_tokens[job_id] = threading.Event()
                
            return job

    def _update_job_status_in_db(self, job: Job):
        try:
            with self.SessionLocal() as session:
                db_job = session.query(DBJob).filter_by(id=int(job.id)).first()
                if db_job:
                    db_job.status = job.status.name
                    db_job.output_path = str(job.output_path) if job.output_path else None
                    db_job.duration_sec = job.duration_sec
                    session.commit()
        except Exception:
            pass

    def run_filter_job(
        self,
        job_id: str,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_token: Optional[threading.Event] = None,
        pause_token: Optional[threading.Event] = None
    ) -> None:
        logger = self._get_job_logger(job_id)
        
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                logger.error(f"Tentativa de rodar job inexistente: {job_id}")
                self._close_job_logger(job_id)
                raise KeyError(f"Job '{job_id}' não encontrado.")
            dataset = self._datasets[job.dataset_id]
            token = cancel_token or self._cancel_tokens[job_id]
            job.status = JobStatus.RUNNING
            self._update_job_status_in_db(job)
            
        logger.info(f"Iniciando Job {job_id}")
        logger.info(f"Parâmetros: Dataset='{dataset.name}', Frequência de Corte={job.cutoff_hz}Hz, Ordem={job.order}, Workers={job.n_workers}")
            
        job_dir = self.output_dir / str(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # O arquivo de saída fica dentro do diretório do job, com o nome original + _filtered.h5
        output_name = f"{dataset.source_path.stem}_filtered.h5"
        output_h5 = job_dir / output_name
        job.output_path = output_h5
        logger.info(f"Arquivo de saída: {output_h5}")

        # Projeto do filtro Butterworth passa-baixa em Second-Order Sections (SOS)
        nyq = dataset.nyquist_frequency_hz
        wn = job.cutoff_hz / nyq
        sos = signal.butter(job.order, wn, btype="lowpass", output="sos")

        chunk_size = 500  # lê e processa em lotes de 500 traços
        total_traces = dataset.total_traces
        
        start_time = time.time()
        total_pause_time = 0.0

        try:
            with segyio.open(str(dataset.source_path), mode="r", ignore_geometry=True) as sgy:
                with h5py.File(output_h5, "w") as h5:
                    # Dataset HDF5 alocado previamente para escrita incremental
                    dset = h5.create_dataset(
                        "filtered_traces",
                        shape=(total_traces, dataset.n_samples),
                        dtype=np.float32,
                        chunks=(min(chunk_size, total_traces), dataset.n_samples)
                    )

                    active_futures = deque()
                    
                    with concurrent.futures.ProcessPoolExecutor(max_workers=job.n_workers) as executor:
                        for start_idx in range(0, total_traces, chunk_size):
                            # Verifica pausa e contabiliza o tempo que ficou pausado
                            if pause_token and not pause_token.is_set():
                                logger.info(f"Job pausado em {start_idx}/{total_traces} traços")
                                p_start = time.time()
                                pause_token.wait()
                                pause_dur = time.time() - p_start
                                total_pause_time += pause_dur
                                logger.info(f"Job retomado. Tempo em pausa: {pause_dur:.2f}s")
                                
                            # Ponto de checagem cooperativo de cancelamento
                            if token.is_set():
                                logger.info("Sinal de cancelamento detectado")
                                executor.shutdown(wait=False, cancel_futures=True)
                                with self._lock:
                                    job.status = JobStatus.CANCELLED
                                    self._update_job_status_in_db(job)
                                self._cleanup_partial_output(output_h5)
                                logger.info("Job cancelado com sucesso")
                                return

                            end_idx = min(start_idx + chunk_size, total_traces)
                            # Leitura de chunk
                            raw_chunk = np.array([sgy.trace[i] for i in range(start_idx, end_idx)], dtype=np.float32)

                            # Envia pro pool
                            future = executor.submit(apply_sos_filter, sos, raw_chunk)
                            active_futures.append((start_idx, end_idx, future))

                            # Mantém fila no máximo 2x n_workers para não estourar RAM com dados lidos
                            while len(active_futures) >= job.n_workers * 2:
                                s_idx, e_idx, f = active_futures.popleft()
                                # Escrita incremental
                                dset[s_idx:e_idx, :] = f.result()

                                # Emissão de progresso
                                pct = (e_idx / total_traces) * 100.0
                                current_dur = (time.time() - start_time) - total_pause_time
                                with self._lock:
                                    job.progress = pct
                                    job.duration_sec = current_dur
                                if progress_callback:
                                    progress_callback(pct, current_dur)
                                    
                        # Descarrega os restantes
                        while active_futures:
                            if token.is_set():
                                logger.info("Sinal de cancelamento detectado no descarregamento de chunks")
                                executor.shutdown(wait=False, cancel_futures=True)
                                with self._lock:
                                    job.status = JobStatus.CANCELLED
                                    self._update_job_status_in_db(job)
                                self._cleanup_partial_output(output_h5)
                                logger.info("Job cancelado com sucesso")
                                return
                                
                            s_idx, e_idx, f = active_futures.popleft()
                            dset[s_idx:e_idx, :] = f.result()
                            pct = (e_idx / total_traces) * 100.0
                            current_dur = (time.time() - start_time) - total_pause_time
                            with self._lock:
                                job.progress = pct
                                job.duration_sec = current_dur
                            if progress_callback:
                                progress_callback(pct, current_dur)

            with self._lock:
                job.status = JobStatus.COMPLETED
                job.progress = 100.0
                job.duration_sec = (time.time() - start_time) - total_pause_time
                self._update_job_status_in_db(job)
            
            logger.info(f"Job {job_id} concluído com sucesso em {job.duration_sec:.2f}s")

        except Exception as exc:
            if isinstance(exc, RuntimeError) and "cannot schedule new futures after shutdown" in str(exc):
                logger.warning(f"Processamento do Job {job_id} interrompido porque a aplicação está sendo encerrada.")
                with self._lock:
                    job.status = JobStatus.FAILED
                    job.error_message = "Aplicação encerrada abruptamente durante execução."
                    self._update_job_status_in_db(job)
            else:
                logger.exception(f"Erro fatal durante a execução do Job {job_id}: {exc}")
                with self._lock:
                    job.status = JobStatus.FAILED
                    job.error_message = str(exc)
                    self._update_job_status_in_db(job)
            self._cleanup_partial_output(output_h5)
            raise
        finally:
            self._close_job_logger(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            token = self._cancel_tokens.get(job_id)
            job = self._jobs.get(job_id)
            if not token or not job:
                return False

            if job.status == JobStatus.RUNNING:
                token.set()
                return True
            elif job.status == JobStatus.CREATED:
                job.status = JobStatus.CANCELLED
                self._update_job_status_in_db(job)
                return True
            return False

    def get_job_status(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' não encontrado.")
            return job

    def list_jobs(
        self,
        dataset_id: Optional[str] = None,
        status: Optional[JobStatus] = None
    ) -> List[Job]:
        with self._lock:
            jobs = list(self._jobs.values())

        if dataset_id:
            jobs = [j for j in jobs if j.dataset_id == dataset_id]
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def _cleanup_partial_output(self, file_path: Path) -> None:
        """Trata o output parcial deletando-o caso falhe ou seja cancelado."""
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError:
            pass
