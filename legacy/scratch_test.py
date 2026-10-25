import sys
sys.path.append('.')
import numpy as np
from scipy.signal import butter, lfilter
from dashboard.app import compute_spectral_features
from python_ml.scenario_simulator import generate_fm, generate_fdi

fs = 100000
b, a = butter(5, [0.12, 0.28], btype='bandpass')

sig_fm = generate_fm(fs, 0.1)
sig_fm_filt = lfilter(b, a, sig_fm).astype(np.float32)
f_fm = compute_spectral_features(sig_fm_filt, fs)

sig_fdi = generate_fdi(fs, 0.1)
sig_fdi_filt = lfilter(b, a, sig_fdi).astype(np.float32)
f_fdi = compute_spectral_features(sig_fdi_filt, fs)

print(f"Synthetic FM Features: {f_fm[0, :4]}")
print(f"Synthetic FDI Features: {f_fdi[0, :4]}")
