import sys
from PySide6.QtWidgets import QApplication
from app_seismica.services.job_service import FilterJobService
from app_seismica.ui.main_window import MainWindow

def main():
    # 1. Instancia a aplicação Qt
    app = QApplication(sys.argv)
    
    # 2. Injeta as dependências (Service)
    service = FilterJobService()
    
    # 3. Cria e exibe a janela principal
    window = MainWindow(service)
    window.show()
    
    # 4. Inicia o loop de eventos
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
