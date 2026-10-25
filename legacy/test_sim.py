import numpy as np
import joblib
from scipy.signal import hilbert
from scipy.stats import kurtosis
import warnings
warnings.filterwarnings('ignore')

model = joblib.load('python_ml/amc_model.pkl')
scaler = joblib.load('python_ml/amc_scaler.pkl')

def compute_spectral_features(signal, fs=100000):
    feat = {}
    eps = np.finfo(float).eps
    analytic = hilbert(signal)
    env = np.abs(analytic)
    env_norm = env / (np.mean(env) + eps)
    feat['amp_variance'] = np.var(env_norm, ddof=1)
    feat['amp_kurtosis'] = kurtosis(env_norm, fisher=False)
    inst_phase = np.unwrap(np.angle(analytic))
    phase_deriv = np.diff(inst_phase)
    feat['phase_variance'] = np.var(phase_deriv, ddof=1)
    signal = signal / (np.std(signal) + eps)
    N = len(signal)
    S = np.abs(np.fft.fftshift(np.fft.fft(signal)))**2 / N
    f = np.fft.fftshift(np.fft.fftfreq(N, d=1/fs))
    total_power = np.sum(S)
    cum_power = np.cumsum(S)
    lower_idx = np.searchsorted(cum_power, 0.005 * total_power)
    upper_idx = np.searchsorted(cum_power, 0.995 * total_power)
    feat['bw_10db'] = f[upper_idx] - f[lower_idx] if upper_idx < N else 0
    pos = f >= 0
    f_p = f[pos]
    S_p = S[pos]
    from scipy.ndimage import median_filter
    S_p_smooth = median_filter(S_p, size=5)
    peak_val = np.max(S_p_smooth)
    feat['peak_psd_db'] = 10 * np.log10(peak_val + eps)
    S_nz = S_p[S_p > 0]
    feat['spectral_flatness'] = np.exp(np.mean(np.log(S_nz))) / (np.mean(S_nz) + eps) if len(S_nz) > 0 else 0
    total_p = np.sum(S_p)
    feat['spectral_centroid'] = np.sum(f_p * S_p) / total_p if total_p > 0 else 0
    fc = 10000
    bin_width = 50
    carrier_bin = (f_p >= fc - bin_width) & (f_p <= fc + bin_width)
    carrier_power = np.sum(S_p[carrier_bin])
    feat['carrier_sideband_ratio'] = carrier_power / total_p if total_p > 0 else 0
    feature_vector = [
        feat['bw_10db'], feat['peak_psd_db'], feat['spectral_flatness'],
        feat['spectral_centroid'], 20, feat['carrier_sideband_ratio'],
        feat['amp_variance'], feat['amp_kurtosis'], feat['phase_variance']
    ]
    return np.array(feature_vector).reshape(1, -1)

def test_signal(name, sig):
    features = compute_spectral_features(sig)
    feat_scaled = scaler.transform(features)
    pred = model.predict(feat_scaled)[0]
    probs = model.predict_proba(feat_scaled)[0]
    top_3_idx = np.argsort(probs)[::-1][:3]
    classes = model.classes_
    top_3 = [(classes[i], probs[i]) for i in top_3_idx]
    print(f"--- {name} ---")
    print(f"Predicted: {pred}")
    print(f"Top 3: {top_3}")
    print(f"Features: BW={features[0,0]:.1f}, PeakPSD={features[0,1]:.1f}, Flatness={features[0,2]:.5f}, Centroid={features[0,3]:.1f}")
    print(f"AmpVar={features[0,6]:.3f}, AmpKurt={features[0,7]:.3f}, PhaseVar={features[0,8]:.3f}\n")

fs = 100000
t = np.arange(0, 0.1, 1/fs)

# AM
msg_am = np.cos(2 * np.pi * 1000 * t)
sig_am = (1 + 0.8 * msg_am) * np.cos(2 * np.pi * 10000 * t)
test_signal("AM", sig_am)

# FM
msg_fm = np.cumsum(np.cos(2 * np.pi * 1000 * t)) / fs
sig_fm = np.cos(2 * np.pi * 10000 * t + 2 * np.pi * 5000 * msg_fm)
test_signal("FM", sig_fm)

# ASK
data_ask = (np.sign(np.cos(2 * np.pi * 500 * t)) > 0).astype(float)
sig_ask = data_ask * np.cos(2 * np.pi * 10000 * t)
test_signal("ASK", sig_ask)

# FSK
data_fsk = np.sign(np.cos(2 * np.pi * 500 * t))
inst_freq = 10000 + 2000 * data_fsk
phase = np.cumsum(inst_freq) / fs
sig_fsk = np.cos(2 * np.pi * phase)
test_signal("FSK", sig_fsk)

# BPSK
data_bpsk = np.sign(np.cos(2 * np.pi * 500 * t))
sig_bpsk = data_bpsk * np.cos(2 * np.pi * 10000 * t)
test_signal("BPSK", sig_bpsk)
