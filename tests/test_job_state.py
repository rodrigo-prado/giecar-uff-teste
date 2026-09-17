import pytest
from pathlib import Path
from app_seismica.core.models import JobStatus, SeismicDataset

def test_job_creation_and_validation(test_service):
    # 1. Registrar um dataset falso
    dataset = SeismicDataset(
        id="test-ds-1",
        name="Mock Dataset",
        source_path=Path("dummy.sgy"),
        n_inlines=10,
        n_crosslines=10,
        n_samples=1000,
        sample_rate_ms=2.0 # Nyquist = 250Hz
    )
    test_service.register_dataset(dataset)
    
    # 2. Criar Job válido
    job = test_service.create_filter_job(
        dataset_id="test-ds-1",
        cutoff_hz=40.0,
        order=4,
        n_workers=2,
        chunk_size=100
    )
    
    assert job.status == JobStatus.CREATED
    assert job.cutoff_hz == 40.0
    assert job.chunk_size == 100
    
    # Verificar se foi salvo no banco (o estado da memória do serviço reflete o banco)
    job_from_service = test_service.get_job_status(job.id)
    assert job_from_service.status == JobStatus.CREATED

def test_job_validation_against_nyquist(test_service):
    dataset = SeismicDataset(
        id="test-ds-2",
        name="Mock Dataset",
        source_path=Path("dummy.sgy"),
        n_inlines=10,
        n_crosslines=10,
        n_samples=1000,
        sample_rate_ms=4.0 # Nyquist = 125Hz
    )
    test_service.register_dataset(dataset)
    
    # Tentar criar job com frequência de corte maior que Nyquist deve estourar ValueError
    with pytest.raises(ValueError, match="excede ou atinge o limite de Nyquist"):
        test_service.create_filter_job(
            dataset_id="test-ds-2",
            cutoff_hz=130.0, # Inválido
            order=4
        )

def test_job_validation_invalid_cutoff_and_order(test_service):
    dataset = SeismicDataset(
        id="test-ds-invalid",
        name="Mock Dataset",
        source_path=Path("dummy.sgy"),
        n_inlines=10,
        n_crosslines=10,
        n_samples=1000,
        sample_rate_ms=4.0 # Nyquist = 125Hz
    )
    test_service.register_dataset(dataset)
    
    # Frequência de corte menor ou igual a 0
    with pytest.raises(ValueError, match="estritamente positiva"):
        test_service.create_filter_job(
            dataset_id="test-ds-invalid",
            cutoff_hz=0.0,
            order=4
        )

    with pytest.raises(ValueError, match="estritamente positiva"):
        test_service.create_filter_job(
            dataset_id="test-ds-invalid",
            cutoff_hz=-10.0,
            order=4
        )

    # Ordem inválida (menor que 1)
    with pytest.raises(ValueError, match="Ordem do filtro"):
        test_service.create_filter_job(
            dataset_id="test-ds-invalid",
            cutoff_hz=40.0,
            order=0
        )

    # Ordem inválida (maior que 12)
    with pytest.raises(ValueError, match="Ordem do filtro"):
        test_service.create_filter_job(
            dataset_id="test-ds-invalid",
            cutoff_hz=40.0,
            order=13
        )

def test_job_cancellation_state(test_service):
    dataset = SeismicDataset(
        id="test-ds-3",
        name="Mock Dataset",
        source_path=Path("dummy.sgy"),
        n_inlines=10,
        n_crosslines=10,
        n_samples=1000,
        sample_rate_ms=2.0
    )
    test_service.register_dataset(dataset)
    
    job = test_service.create_filter_job(dataset_id="test-ds-3", cutoff_hz=40.0, order=4)
    
    # Cancelar um job no estado CREATED deve ir direto para CANCELLED
    success = test_service.cancel_job(job.id)
    assert success is True
    
    job_status = test_service.get_job_status(job.id)
    assert job_status.status == JobStatus.CANCELLED
    
    # Deve refletir no banco de dados persistido
    # Se simularmos um load do banco, ele deve voltar como CANCELLED
    test_service._load_from_db()
    loaded_job = test_service.get_job_status(job.id)
    assert loaded_job.status == JobStatus.CANCELLED
