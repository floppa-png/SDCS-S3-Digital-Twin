import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier

# Load data
df = pd.read_csv('../Matlab_part/ground_truth_dataset.csv')
features = ['BW_10dB', 'PeakPSD_dB', 'SpectralFlatness', 'SpectralCentroid', 
            'ReceivedSNR_dB', 'CarrierSidebandRatio', 'AmpVariance', 'AmpKurtosis', 'PhaseVariance']
df = df.dropna(subset=features)

X = df[features].values
y = df['ModType'].values
snr = df['InputSNR_dB'].values

# Same split as baseline model
X_train, X_test, y_train, y_test, snr_train, snr_test = train_test_split(
    X, y, snr, test_size=0.2, random_state=42, stratify=y)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

model = HistGradientBoostingClassifier(max_iter=300, max_depth=15, learning_rate=0.1, random_state=42)
model.fit(X_train_scaled, y_train)

y_pred = model.predict(X_test_scaled)

fm_mask = (y_test == 'FM')
correct_fm_mask = fm_mask & (y_pred == 'FM')
error_fm_dsbsc_mask = fm_mask & (y_pred == 'AM_DSBSC')
pv_idx = features.index('PhaseVariance')

print("--- SNR Binned PhaseVariance Analysis ---")
snr_bins = sorted(list(set(snr_test[fm_mask])))
for s in snr_bins:
    idx_snr = (snr_test == s)
    correct_snr = correct_fm_mask & idx_snr
    error_snr = error_fm_dsbsc_mask & idx_snr
    
    c_pv = X_test[correct_snr, pv_idx]
    e_pv = X_test[error_snr, pv_idx]
    
    if sum(error_snr) > 0:
        c_mean = np.mean(c_pv) if len(c_pv) > 0 else np.nan
        e_mean = np.mean(e_pv)
        print(f"SNR {s:3d} dB -> Errors: {sum(error_snr):2d} | Correct Mean PV: {c_mean:.4f} | Error Mean PV: {e_mean:.4f}")
