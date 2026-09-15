import uuid
from pathlib import Path
import segyio
from app_seismica.core.models import SeismicDataset


def inspect_segy_metadata(filepath: Path) -> SeismicDataset:
    filepath = Path(filepath)
    if not filepath.is_file():
        raise FileNotFoundError(f"Arquivo SEG-Y não encontrado: {filepath}")

    with segyio.open(str(filepath), mode="r", ignore_geometry=True) as sgy:
        try:
            n_ilines = len(sgy.ilines)
            n_xlines = len(sgy.xlines)
        except Exception:
            # Fallback para 2D ou arquivos sem geometria de grid regular
            n_ilines = 1
            n_xlines = sgy.tracecount

        n_samples = len(sgy.samples)
        # segyio.tools.dt retorna o intervalo em microssegundos (ex: 2000 ou 4000)
        dt_us = segyio.tools.dt(sgy)
        sample_rate_ms = dt_us / 1000.0

    return SeismicDataset(
        id=str(uuid.uuid4())[:8],
        name=filepath.stem,
        source_path=filepath,
        n_inlines=n_ilines,
        n_crosslines=n_xlines,
        n_samples=n_samples,
        sample_rate_ms=sample_rate_ms
    )
