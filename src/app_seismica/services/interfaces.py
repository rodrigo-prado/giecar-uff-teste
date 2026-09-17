from typing import Protocol, List, Optional, Callable
import threading
from app_seismica.core.models import Job, JobStatus

# Assinatura do callback: recebe percentual (0.0 a 100.0) ou valor normalizado (0.0 a 1.0)
ProgressCallback = Callable[[float], None]

class FilterJobServiceProtocol(Protocol):
    def create_filter_job(
        self, 
        dataset_id: str, 
        cutoff_hz: float, 
        order: int
    ) -> Job:
        """Cria e persiste o registro do job com status inicial PENDING."""
        ...

    def run_filter_job(
        self, 
        job_id: str, 
        progress_callback: Optional[ProgressCallback] = None, 
        cancel_token: Optional[threading.Event] = None
    ) -> None:
        """
        Executa a filtragem passa-baixa de forma síncrona/bloqueante dentro
        da thread que a chamou (ideal para ser envolvida por QRunnable/QThread).
        """
        ...

    def cancel_job(self, job_id: str) -> bool:
        """Sinaliza o cancelamento e atualiza o estado do job."""
        ...

    def get_job_status(self, job_id: str) -> Job:
        """Recupera a entidade Job atualizada."""
        ...

    def list_jobs(
        self, 
        dataset_id: Optional[str] = None, 
        status: Optional[JobStatus] = None
    ) -> List[Job]:
        """Filtra e lista jobs registrados."""
        ...