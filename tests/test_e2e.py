import segyio
import numpy as np
import h5py
from pathlib import Path
from app_seismica.core.models import JobStatus, SeismicDataset

def create_dummy_segy(path: Path):
    """
    Cria um arquivo SEG-Y minúsculo e válido estruturalmente usando segyio.
    Total: 3 inlines x 3 crosslines = 9 traços.
    100 amostras por traço.
    """
    spec = segyio.spec()
    spec.ilines = [1, 2, 3]
    spec.xlines = [1, 2, 3]
    spec.samples = list(range(100))
    spec.format = 1  # IBM float (standard)
    
    with segyio.create(str(path), spec) as f:
        # Preenche com ruído aleatório
        synthetic_data = np.random.randn(9, 100).astype(np.float32)
        
        # O segyio gerencia as matrizes
        trace_idx = 0
        for il in spec.ilines:
            for xl in spec.xlines:
                f.header[trace_idx] = {
                    segyio.su.iline: il,
                    segyio.su.xline: xl
                }
                f.trace[trace_idx] = synthetic_data[trace_idx]
                trace_idx += 1

def test_full_pipeline_e2e(test_service, tmp_path):
    """
    Simula o fluxo completo de um usuário:
    1. Importa um arquivo SEG-Y real (mockado)
    2. Cria o Job de filtro
    3. Roda o processamento (lendo blocos, processando, escrevendo HDF5)
    4. Verifica se o HDF5 final foi gerado corretamente
    """
    # 1. Preparar o arquivo
    segy_path = tmp_path / "test_data.sgy"
    create_dummy_segy(segy_path)
    
    # 2. Registrar o Dataset no Serviço
    dataset = SeismicDataset(
        id="e2e-ds-1",
        name="E2E Dummy Dataset",
        source_path=segy_path,
        n_inlines=3,
        n_crosslines=3,
        n_samples=100,
        sample_rate_ms=2.0 # dt = 2ms -> Nyquist = 250Hz
    )
    test_service.register_dataset(dataset)
    
    # 3. Criar Job
    job = test_service.create_filter_job(
        dataset_id="e2e-ds-1",
        cutoff_hz=40.0,
        order=4,
        n_workers=1,  # 1 worker pra não ter dor de cabeça com multiprocessing no pytest
        chunk_size=5  # chunks pequenos para testar a fila num arquivo de 9 traços
    )
    
    # 4. Executar o Job (isso roda sincronicamente na mesma thread no teste)
    test_service.run_filter_job(job.id)
    
    # 5. Verificações de Estado e Banco de Dados
    final_job = test_service.get_job_status(job.id)
    assert final_job.status == JobStatus.COMPLETED
    assert final_job.progress == 100.0
    assert final_job.output_path is not None
    assert final_job.output_path.exists()
    
    # 6. Verificações do Arquivo HDF5 (Output)
    with h5py.File(final_job.output_path, "r") as h5:
        assert "filtered_traces" in h5
        dset = h5["filtered_traces"]
        # Deve ter o exato mesmo shape do SEG-Y original (9 traços, 100 amostras)
        assert dset.shape == (9, 100)
        assert dset.dtype == np.float32
        
        # Garante que o HDF5 não tem valores "vazios" (zeros puros não intencionais)
        # Como era ruído aleatório, a chance de a média de energia ser 0 é nula
        data_read = dset[:]
        assert np.mean(np.abs(data_read)) > 0.0
