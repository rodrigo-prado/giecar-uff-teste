import uuid
import threading
from pathlib import Path
from typing import Dict, List, Optional, Callable
import h5py
import numpy as np
from scipy import signal
import segyio

from app_seismica.core.models import Job, JobStatus, SeismicDataset, FilterParameters
from app_seismica.core.database import init_db, DBDataset, DBJob

ProgressCallback = Callable[[float], None]


class FilterJobService:
    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        output_dir = project_root / "data" / "processed"
        output_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
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

                job_id = str(db_job.id)
                job = Job(
                    id=job_id,
                    dataset_id=db_job.dataset_id,
                    cutoff_hz=db_job.cutoff_hz,
                    order=db_job.order,
                    status=status,
                    progress=100.0 if status == JobStatus.COMPLETED else 0.0,
                    output_path=Path(db_job.output_path) if db_job.output_path else None
                )
                self._jobs[job_id] = job
                self._cancel_tokens[job_id] = threading.Event()

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

    def create_filter_job(self, dataset_id: str, cutoff_hz: float, order: int) -> Job:
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
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' não encontrado.")
            dataset = self._datasets[job.dataset_id]
            token = cancel_token or self._cancel_tokens[job_id]
            job.status = JobStatus.RUNNING
            self._update_job_status_in_db(job)
            
        job_dir = self.output_dir / str(job.id)
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # O arquivo de saída fica dentro do diretório do job, com o nome original + _filtered.h5
        output_name = f"{dataset.source_path.stem}_filtered.h5"
        output_h5 = job_dir / output_name
        job.output_path = output_h5

        # Projeto do filtro Butterworth passa-baixa em Second-Order Sections (SOS)
        nyq = dataset.nyquist_frequency_hz
        wn = job.cutoff_hz / nyq
        sos = signal.butter(job.order, wn, btype="lowpass", output="sos")

        chunk_size = 500  # lê e processa em lotes de 500 traços
        total_traces = dataset.total_traces

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

                    for start_idx in range(0, total_traces, chunk_size):
                        # Verifica pausa
                        if pause_token:
                            pause_token.wait()
                            
                        # Ponto de checagem cooperativo de cancelamento
                        if token.is_set():
                            with self._lock:
                                job.status = JobStatus.CANCELLED
                                self._update_job_status_in_db(job)
                            self._cleanup_partial_output(output_h5)
                            return

                        end_idx = min(start_idx + chunk_size, total_traces)
                        # Leitura de chunk
                        raw_chunk = np.array([sgy.trace[i] for i in range(start_idx, end_idx)], dtype=np.float32)

                        # Filtragem passa-baixa forward-backward (fase zero)
                        filtered_chunk = signal.sosfiltfilt(sos, raw_chunk, axis=1)

                        # Escrita incremental
                        dset[start_idx:end_idx, :] = filtered_chunk

                        # Emissão de progresso
                        pct = (end_idx / total_traces) * 100.0
                        with self._lock:
                            job.progress = pct
                        if progress_callback:
                            progress_callback(pct)

            with self._lock:
                job.status = JobStatus.COMPLETED
                job.progress = 100.0
                self._update_job_status_in_db(job)

        except Exception as exc:
            with self._lock:
                job.status = JobStatus.FAILED
                job.error_message = str(exc)
                self._update_job_status_in_db(job)
            self._cleanup_partial_output(output_h5)
            raise

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
