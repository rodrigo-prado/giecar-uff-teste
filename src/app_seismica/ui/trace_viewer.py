from pathlib import Path
import segyio
import h5py
import numpy as np

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QWidget, QLineEdit
)
from PySide6.QtCore import Qt

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

class TraceViewerDialog(QDialog):
    def __init__(self, raw_path: Path, filtered_path: Path, total_traces: int, parent=None):
        super().__init__(parent)
        self.raw_path = raw_path
        self.filtered_path = filtered_path
        self.total_traces = total_traces
        
        self.current_trace = 0
        
        # Load dt_ms
        with segyio.open(str(self.raw_path), ignore_geometry=True, strict=False) as sgy:
            self.dt_ms = segyio.tools.dt(sgy) / 1000.0
            
        self.setWindowTitle("Visualizador de Traços")
        self.resize(1000, 600)
        
        layout = QVBoxLayout(self)
        
        # --- Matplotlib Canvas ---
        self.figure = Figure(figsize=(10, 5))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        layout.addWidget(self.canvas)
        
        # --- Controles de Navegação ---
        nav_layout = QHBoxLayout()
        
        self.btn_fast_prev = QPushButton("<<")
        self.btn_fast_prev.setAutoDefault(False)
        self.btn_fast_prev.clicked.connect(self.go_to_first)
        
        self.btn_prev = QPushButton("<")
        self.btn_prev.setAutoDefault(False)
        self.btn_prev.clicked.connect(self.go_prev)
        
        self.txt_trace_idx = QLineEdit()
        self.txt_trace_idx.setMaximumWidth(80)
        self.txt_trace_idx.setAlignment(Qt.AlignCenter)
        self.txt_trace_idx.returnPressed.connect(self.on_jump_to_trace)
        
        self.lbl_total = QLabel(f" / {self.total_traces - 1}")
        
        self.btn_next = QPushButton(">")
        self.btn_next.setAutoDefault(False)
        self.btn_next.clicked.connect(self.go_next)
        
        self.btn_fast_next = QPushButton(">>")
        self.btn_fast_next.setAutoDefault(False)
        self.btn_fast_next.clicked.connect(self.go_to_last)
        
        nav_layout.addStretch()
        nav_layout.addWidget(self.btn_fast_prev)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.txt_trace_idx)
        nav_layout.addWidget(self.lbl_total)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_fast_next)
        nav_layout.addStretch()
        
        layout.addLayout(nav_layout)
        
        # Render initial trace
        self.update_plot()
        
    def go_to_first(self):
        self.navigate_to(0)
        
    def go_prev(self):
        self.navigate_to(self.current_trace - 1)
        
    def go_next(self):
        self.navigate_to(self.current_trace + 1)
        
    def go_to_last(self):
        self.navigate_to(self.total_traces - 1)
        
    def navigate_to(self, new_trace: int):
        if new_trace < 0:
            new_trace = 0
        elif new_trace >= self.total_traces:
            new_trace = self.total_traces - 1
            
        if new_trace != self.current_trace:
            self.current_trace = new_trace
            self.update_plot()

    def on_jump_to_trace(self):
        try:
            val = int(self.txt_trace_idx.text())
            if 0 <= val < self.total_traces:
                self.current_trace = val
                self.update_plot()
            else:
                self.txt_trace_idx.setText(str(self.current_trace))
        except ValueError:
            self.txt_trace_idx.setText(str(self.current_trace))

    def update_plot(self):
        self.txt_trace_idx.setText(str(self.current_trace))
        
        try:
            with segyio.open(str(self.raw_path), ignore_geometry=True, strict=False) as sgy:
                original_trace = sgy.trace[self.current_trace]
                
            with h5py.File(str(self.filtered_path), "r") as h5_file:
                filtered_trace = h5_file["filtered_traces"][self.current_trace]
        except Exception as e:
            self.ax.clear()
            self.ax.text(0.5, 0.5, f"Erro ao ler traço:\n{e}", ha="center", va="center")
            self.canvas.draw()
            return

        n_samples = len(original_trace)
        time_axis = np.arange(n_samples) * self.dt_ms
        
        self.ax.clear()
        
        # Plot
        self.ax.plot(time_axis, original_trace, label="Original (SEG-Y)", color="lightgray", linewidth=2.0)
        self.ax.plot(time_axis, filtered_trace, label="Filtrado (HDF5)", color="blue", linewidth=1.0)
        
        self.ax.set_title(f"Traço {self.current_trace}")
        self.ax.set_xlabel("Tempo (ms)")
        self.ax.set_ylabel("Amplitude")
        self.ax.legend(loc="upper right")
        self.ax.grid(True, linestyle="--", alpha=0.6)
        
        self.figure.tight_layout()
        self.canvas.draw()
