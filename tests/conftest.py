import pytest

@pytest.fixture
def test_service(tmp_path):
    """
    Cria um FilterJobService configurado para usar um banco de dados em memória
    e um diretório temporário para os arquivos, garantindo isolamento total.
    """
    import app_seismica.services.job_service as js
    import app_seismica.core.database as db
    from app_seismica.services.job_service import FilterJobService
    
    # Faz um monkeypatch no banco de dados apenas para esta instância de teste
    # Como FilterJobService faz init_db("sqlite:///:memory:"), precisamos injetar
    # Mas como ele cria o engine dentro do __init__, vamos interceptar:
    
    class TestFilterJobService(FilterJobService):
        def __init__(self):
            # Inicializa caminhos em tmp_path
            self.output_dir = tmp_path / "data" / "processed"
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir = tmp_path / "data" / "logs" / "jobs"
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Força o banco em memória
            self.SessionLocal = db.init_db("sqlite:///:memory:")
            
            self._datasets = {}
            self._jobs = {}
            self._cancel_tokens = {}
            import threading
            self._lock = threading.Lock()
            
            self._load_from_db()
            
    return TestFilterJobService()
