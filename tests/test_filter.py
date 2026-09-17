import numpy as np
from scipy import signal
from app_seismica.services.job_service import apply_sos_filter

def test_butterworth_filter_correctness():
    """
    Testa se o filtro Butterworth passa-baixa realmente atenua frequências altas
    e preserva frequências baixas em um traço sísmico sintético.
    """
    # 1. Configurar parâmetros do sinal sintético
    fs = 1000.0  # Frequência de amostragem: 1000 Hz (dt = 1ms)
    nyq = fs / 2.0  # Nyquist = 500 Hz
    t = np.arange(0, 1.0, 1.0 / fs)  # 1 segundo de dados (1000 amostras)

    # 2. Criar duas ondas: uma de baixa frequência (10 Hz) e uma de alta (100 Hz)
    f_low = 10.0
    f_high = 100.0
    wave_low = np.sin(2 * np.pi * f_low * t)
    wave_high = 0.5 * np.sin(2 * np.pi * f_high * t)
    
    # Sinal combinado (o "traço" sintético)
    synthetic_trace = wave_low + wave_high

    # O apply_sos_filter espera um array 2D (chunks de traços)
    # Shape: (1, 1000) - 1 traço, 1000 amostras
    chunk = np.array([synthetic_trace])

    # 3. Projetar o filtro: Passa-baixa cortando em 40 Hz
    cutoff_hz = 40.0
    order = 4
    wn = cutoff_hz / nyq
    sos = signal.butter(order, wn, btype="lowpass", output="sos")

    # 4. Aplicar o filtro
    filtered_chunk = apply_sos_filter(sos, chunk)
    filtered_trace = filtered_chunk[0]

    # 5. Validação (Corretude)
    
    # a) A amplitude da onda de baixa frequência (10 Hz) deve ser bem preservada.
    # Vamos checar a energia (variância) ou a amplitude de pico
    # Como a onda original de 10Hz tem amplitude 1, o sinal filtrado deve ser parecido com ela
    
    error_low_freq = np.mean((filtered_trace - wave_low) ** 2)
    # O erro entre o sinal filtrado e a onda pura de 10Hz deve ser bem pequeno
    assert error_low_freq < 0.05, f"Onda de baixa frequência foi distorcida demais. Erro: {error_low_freq}"

    # b) Para ser ainda mais estrito matematicamente, podemos checar as frequências via FFT
    fft_original = np.abs(np.fft.rfft(synthetic_trace))
    fft_filtered = np.abs(np.fft.rfft(filtered_trace))
    freqs = np.fft.rfftfreq(len(synthetic_trace), 1.0 / fs)

    # Achar os índices aproximados para 10 Hz e 100 Hz
    idx_10hz = np.argmin(np.abs(freqs - 10.0))
    idx_100hz = np.argmin(np.abs(freqs - 100.0))

    # A energia no 10Hz deve continuar quase a mesma
    assert fft_filtered[idx_10hz] > 0.9 * fft_original[idx_10hz], "Sinal de 10Hz foi muito atenuado!"
    
    # A energia no 100Hz deve ser esmagada (bem atenuada, já que o corte foi 40Hz)
    assert fft_filtered[idx_100hz] < 0.1 * fft_original[idx_100hz], "Sinal de 100Hz não foi atenuado o suficiente!"
