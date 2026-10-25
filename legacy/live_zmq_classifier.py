import zmq
import numpy as np
import joblib
from scipy.signal import hilbert
from scipy.stats import kurtosis
import struct
import warnings
import time

# Suppress warnings for zero division in some features
warnings.filterwarnings('ignore')

def compute_spectral_features(signal, fs, snr_db=20):
    """
    Python port of MATLAB compute_spectral_features.
    Expects real passband signal.
    """
    feat = {}
    eps = np.finfo(float).eps
    
    # 1. Time-Domain Envelope Features
    analytic = hilbert(signal)
    env = np.abs(analytic)
    env_norm = env / (np.mean(env) + eps)
    
    feat['amp_variance'] = np.var(env_norm, ddof=1)
    feat['amp_kurtosis'] = kurtosis(env_norm, fisher=False)
    
    # Phase feature
    inst_phase = np.unwrap(np.angle(analytic))
    phase_deriv = np.diff(inst_phase)
    feat['phase_variance'] = np.var(phase_deriv, ddof=1)
    
    # Normalize signal
    signal = signal / (np.std(signal) + eps)
    
    # 2. Frequency-Domain Features
    N = len(signal)
    S = np.abs(np.fft.fftshift(np.fft.fft(signal)))**2 / N
    f = np.fft.fftshift(np.fft.fftfreq(N, d=1/fs))
    
    # Occupied Bandwidth (99%)
    total_power = np.sum(S)
    cum_power = np.cumsum(S)
    lower_idx = np.searchsorted(cum_power, 0.005 * total_power)
    upper_idx = np.searchsorted(cum_power, 0.995 * total_power)
    feat['bw_10db'] = f[upper_idx] - f[lower_idx] if upper_idx < N else 0
    
    # Positive frequency half
    pos = f >= 0
    f_p = f[pos]
    S_p = S[pos]
    
    # Smooth PSD (movmedian window 5) - simple implementation
    from scipy.ndimage import median_filter
    S_p_smooth = median_filter(S_p, size=5)
    
    peak_val = np.max(S_p_smooth)
    feat['peak_psd_db'] = 10 * np.log10(peak_val + eps)
    
    S_nz = S_p[S_p > 0]
    if len(S_nz) > 0:
        feat['spectral_flatness'] = np.exp(np.mean(np.log(S_nz))) / (np.mean(S_nz) + eps)
    else:
        feat['spectral_flatness'] = 0
        
    total_p = np.sum(S_p)
    if total_p > 0:
        feat['spectral_centroid'] = np.sum(f_p * S_p) / total_p
    else:
        feat['spectral_centroid'] = 0
        
    # Carrier-to-Sideband Ratio (fc = 10000 Hz)
    fc = 10000
    bin_width = 50
    carrier_bin = (f_p >= fc - bin_width) & (f_p <= fc + bin_width)
    carrier_power = np.sum(S_p[carrier_bin])
    feat['carrier_sideband_ratio'] = carrier_power / total_p if total_p > 0 else 0
    
    feature_vector = [
        feat['bw_10db'],
        feat['peak_psd_db'],
        feat['spectral_flatness'],
        feat['spectral_centroid'],
        snr_db, 
        feat['carrier_sideband_ratio'],
        feat['amp_variance'],
        feat['amp_kurtosis'],
        feat['phase_variance']
    ]
    return np.array(feature_vector).reshape(1, -1)


def main():
    print("============================================================")
    print("   Digital Twin AI — Live GNU Radio ZMQ Receiver")
    print("============================================================")
    
    print("[1/3] Loading trained model and scaler...")
    try:
        model = joblib.load('amc_model.pkl')
        scaler = joblib.load('amc_scaler.pkl')
    except Exception as e:
        print(f"Error loading model: {e}. Please run 'python initial_baseline_model.py' first.")
        return
        
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind("tcp://127.0.0.1:5555")
    
    print("[2/3] ZMQ PULL socket bound to tcp://127.0.0.1:5555")
    print("[3/3] Awaiting live IQ stream from GNU Radio...")
    
    # MATLAB dataset used N=10000 samples per trial at fs=100000
    CHUNK_SIZE = 10000
    fs = 100000
    
    buffer = b""
    frame_count = 0
    
    while True:
        try:
            msg = socket.recv(zmq.NOBLOCK)
            buffer += msg
        except zmq.Again:
            time.sleep(0.01)
            continue
            
        # 4 bytes per float32
        bytes_needed = CHUNK_SIZE * 4
        
        while len(buffer) >= bytes_needed:
            chunk = buffer[:bytes_needed]
            buffer = buffer[bytes_needed:]
            
            # Unpack binary float32 data from GNU Radio
            signal = np.array(struct.unpack(f"{CHUNK_SIZE}f", chunk))
            
            # Extract features live
            features = compute_spectral_features(signal, fs)
            
            # Predict
            features_scaled = scaler.transform(features)
            prediction = model.predict(features_scaled)[0]
            
            frame_count += 1
            print(f"[Frame {frame_count:04d}] Predicted Modulation: -->  {prediction}  <--")

if __name__ == "__main__":
    main()
