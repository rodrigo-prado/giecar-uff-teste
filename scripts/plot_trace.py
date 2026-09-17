import segyio
import h5py
import matplotlib.pyplot as plt
import numpy as np

# 1. Caminhos dos arquivos (ajuste o nome do .h5 para o arquivo exato que você gerou)
segy_path = "data/raw/volve_psdm_full_time.segy"
h5_path = "data/processed/072f7d5c_filtered.h5" 
nome_dataset_h5 = "filtered_traces"

# Índice do traço que vamos inspecionar (ex: traço número 10.000)
trace_idx = 10000 

# 2. Extraindo o traço original (SEG-Y)
with segyio.open(segy_path, ignore_geometry=True) as sgy:
    original_trace = sgy.trace[trace_idx]
    
    # Pega o intervalo de amostragem em milissegundos para o eixo X
    dt_ms = segyio.tools.dt(sgy) / 1000.0  
    
    n_samples = len(original_trace)
    time_axis = np.arange(n_samples) * dt_ms

# 3. Extraindo o traço filtrado (HDF5)
with h5py.File(h5_path, "r") as h5_file:
    filtered_trace = h5_file[nome_dataset_h5][trace_idx]

# 4. Configurando a plotagem
plt.figure(figsize=(14, 6))

# Original ao fundo (cinza claro)
plt.plot(time_axis, original_trace, label="Original (SEG-Y)", color="lightgray", linewidth=2.5)

# Filtrado por cima (azul)
plt.plot(time_axis, filtered_trace, label="Filtrado (HDF5)", color="blue", linewidth=1.5)

# Estética do gráfico
plt.title(f"Validação do Filtro Butterworth - Traço {trace_idx}")
plt.xlabel("Tempo (ms)")
plt.ylabel("Amplitude")
plt.legend(loc="upper right")
plt.grid(True, linestyle="--", alpha=0.6)

# Zoom em um intervalo de tempo para ver os detalhes da onda (ajuste se quiser)
plt.xlim(1000, 1500) 

plt.tight_layout()
plt.show()
