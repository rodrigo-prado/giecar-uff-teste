from PySide6.QtCore import QRunnable, QObject, Signal
import threading

class WorkerSignals(QObject):
    progress = Signal(float, float)
    finished = Signal()
    error = Signal(str)

class FilterWorker(QRunnable):
    def __init__(self, service, job_id: str):
        super().__init__()
        self.service = service
        self.job_id = job_id
        self.signals = WorkerSignals()
        self.cancel_token = threading.Event()
        self.pause_token = threading.Event()
        self.pause_token.set()

    def run(self):
        try:
            self.service.run_filter_job(
                job_id=self.job_id,
                progress_callback=self.signals.progress.emit,
                cancel_token=self.cancel_token,
                pause_token=self.pause_token
            )
            self.signals.finished.emit()
        except Exception as e:
            self.signals.error.emit(str(e))
