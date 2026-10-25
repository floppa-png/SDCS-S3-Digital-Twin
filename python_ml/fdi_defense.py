import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import os

print("============================================================")
print("   Digital Twin AI — False Data Injection (FDI) Defense")
print("============================================================")

dataset_path = '../Matlab_part/ground_truth_dataset.csv'
if not os.path.exists(dataset_path):
    print(f"Error: Dataset not found at {dataset_path}")
    exit(1)

print("[1/5] Loading legitimate dataset...")
df_clean = pd.read_csv(dataset_path)
df_clean = df_clean.dropna(subset=['BW_10dB', 'PeakPSD_dB', 'SpectralFlatness', 'SpectralCentroid'])

# Use high-SNR signals as our "normal" baseline behavior
df_clean = df_clean[df_clean['InputSNR_dB'] >= 15].copy()
features = ['BW_10dB', 'PeakPSD_dB', 'SpectralFlatness', 'SpectralCentroid']
X_clean = df_clean[features].values

print("[2/5] Simulating Hacker (False Data Injection)...")
# Generate adversarial fake data that mimics the real features but is statistically off
n_fake = int(0.2 * len(X_clean))  # 20% of data is injected by hacker
fake_BW = np.random.uniform(50000, 100000, n_fake) # Impossibly high bandwidths
fake_Peak = np.random.uniform(-10, 10, n_fake)     # Unusually high power
fake_Flat = np.random.uniform(0.8, 1.0, n_fake)    # Very flat (noise jamming)
fake_Centroid = np.random.uniform(0, 50000, n_fake)

X_fake = np.column_stack((fake_BW, fake_Peak, fake_Flat, fake_Centroid))

# Combine datasets (Label: 1 for normal, -1 for anomaly)
X_mixed = np.vstack((X_clean, X_fake))
y_true = np.array([1] * len(X_clean) + [-1] * n_fake)

print("[3/5] Scaling features & Training Isolation Forest...")
scaler = StandardScaler()
X_clean_scaled = scaler.fit_transform(X_clean)
X_mixed_scaled = scaler.transform(X_mixed)

# Train the AI only on what it knows is clean data
# We set contamination=0.01 so it only flags the most extreme 1% of the clean data as anomalies, reducing false positives.
iso_forest = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
iso_forest.fit(X_clean_scaled)

print("[4/5] Detecting Anomalies in live mixed data stream...")
y_pred = iso_forest.predict(X_mixed_scaled)

# Calculate Detection Rate
true_positives = np.sum((y_pred == -1) & (y_true == -1))
detection_rate = true_positives / n_fake
false_alarms = np.sum((y_pred == -1) & (y_true == 1))
fpr = false_alarms / len(X_clean)

print(f"\n---> Hacker Detection Rate: {detection_rate*100:.2f}%")
print(f"---> False Alarm Rate: {fpr*100:.2f}%\n")

print("[5/5] Generating FDI Defense plot...")
plt.figure(figsize=(10, 6))
# We'll plot Peak PSD vs Bandwidth to visualize the anomaly detection
plt.style.use('dark_background')

# Plot legitimate signals
plt.scatter(X_mixed[y_true == 1, 0], X_mixed[y_true == 1, 1], 
            c='cyan', alpha=0.5, label='Legitimate Signals', s=20)

# Plot injected signals
plt.scatter(X_mixed[y_true == -1, 0], X_mixed[y_true == -1, 1], 
            c='red', marker='x', label='Hacker FDI (Injected)', s=40)

# Circle the ones the AI caught
plt.scatter(X_mixed[y_pred == -1, 0], X_mixed[y_pred == -1, 1], 
            facecolors='none', edgecolors='yellow', s=100, label='AI Detected Anomaly')

plt.title('Digital Twin FDI Defense: Isolation Forest')
plt.xlabel('10 dB Bandwidth (Hz)')
plt.ylabel('Peak PSD (dB)')
plt.legend(loc='upper right')
plt.grid(True, alpha=0.2)

output_file = 'fdi_defense_scatter.png'
plt.savefig(output_file, dpi=300)
print(f"Saved plot to: {output_file}")
print("============================================================")
