from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Dict, Any


class JobStatus(Enum):
    CREATED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


@dataclass
class FilterParameters:
    cutoff_hz: float
    order: int

    def validate_against_nyquist(self, nyquist_hz: float) -> None:
        if self.cutoff_hz <= 0:
            raise ValueError("A frequência de corte deve ser estritamente positiva.")
        if self.cutoff_hz >= nyquist_hz:
            raise ValueError(
                f"Frequência de corte ({self.cutoff_hz} Hz) excede ou atinge o limite "
                f"de Nyquist do dado ({nyquist_hz:.1f} Hz)."
            )
        if not (1 <= self.order <= 12):
            raise ValueError(f"Ordem do filtro ({self.order}) inválida. Use um valor entre 1 e 12.")


@dataclass
class SeismicDataset:
    id: str
    name: str
    source_path: Path
    n_inlines: int
    n_crosslines: int
    n_samples: int
    sample_rate_ms: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if isinstance(self.source_path, str):
            self.source_path = Path(self.source_path)

    @property
    def total_traces(self) -> int:
        return self.n_inlines * self.n_crosslines

    @property
    def nyquist_frequency_hz(self) -> float:
        # dt em segundos = sample_rate_ms / 1000.0
        dt_sec = self.sample_rate_ms / 1000.0
        return 1.0 / (2.0 * dt_sec)


@dataclass
class Job:
    id: str  # Será preenchido com a string da sequence
    dataset_id: str
    cutoff_hz: float
    order: int
    n_workers: int = 1
    chunk_size: int = 500
    status: JobStatus = JobStatus.CREATED
    progress: float = 0.0
    output_path: Optional[Path] = None
    error_message: Optional[str] = None
    duration_sec: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
