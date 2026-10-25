import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import os
import joblib

print("============================================================")
print("   Digital Twin AI — Physics-Engineered AMC Model")
print("============================================================")

dataset_path = '../Matlab_part/ground_truth_dataset.csv'
if not os.path.exists(dataset_path):
    print(f"Error: Dataset not found at {dataset_path}")
    exit(1)

print("[1/4] Loading and preparing dataset (No SNR filtering)...")
df = pd.read_csv(dataset_path)

# Drop rows with NaN in features
features = ['BW_10dB', 'PeakPSD_dB', 'SpectralFlatness', 'SpectralCentroid', 
            'ReceivedSNR_dB', 'CarrierSidebandRatio', 'AmpVariance', 'AmpKurtosis', 'PhaseVariance']
df = df.dropna(subset=features)

X = df[features].values
y = df['ModType'].values
snr = df['InputSNR_dB'].values

print("\n[2/4] Extracting features and labels...")
# Split SNR along with X and y to evaluate accuracy vs SNR later
X_train, X_test, y_train, y_test, snr_train, snr_test = train_test_split(
    X, y, snr, test_size=0.2, random_state=42, stratify=y)

print("[3/4] Scaling features and training Advanced Gradient Boosting AI...")
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

model = HistGradientBoostingClassifier(
    max_iter=300, 
    max_depth=15, 
    learning_rate=0.1, 
    random_state=42
)
model.fit(X_train_scaled, y_train)

# 4. Evaluate the model
print("[4/4] Evaluating model performance...")
y_pred = model.predict(X_test_scaled)
acc = accuracy_score(y_test, y_pred)
print(f"\n---> Global Accuracy (All SNRs, -5 to 30 dB): {acc * 100:.2f}%\n")

print("Classification Report (Averaged over all SNRs):")
print(classification_report(y_test, y_pred))

# Evaluate Accuracy vs SNR
print("Accuracy vs SNR Breakdown:")
snr_bins = sorted(list(set(snr_test)))
acc_per_snr = []
for s in snr_bins:
    idx = (snr_test == s)
    acc_s = accuracy_score(y_test[idx], y_pred[idx])
    support = sum(idx)
    acc_per_snr.append(acc_s)
    if s % 5 == 0:
        print(f"  SNR {s:3d} dB: {acc_s * 100:6.2f}%  (Support: n={support})")

# Generate Accuracy vs SNR Plot
plt.figure(figsize=(8, 5))
plt.plot(snr_bins, [a*100 for a in acc_per_snr], marker='o', linestyle='-', color='b')
plt.title('Classification Accuracy vs. Input SNR')
plt.xlabel('Input SNR (dB)')
plt.ylabel('Accuracy (%)')
plt.grid(True)
plt.tight_layout()
plt.savefig('accuracy_vs_snr.png', dpi=300)

# Generate Confusion Matrix
cm = confusion_matrix(y_test, y_pred, labels=model.classes_)
plt.figure(figsize=(10, 8))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
            xticklabels=model.classes_, 
            yticklabels=model.classes_)
plt.title(f'Confusion Matrix (Averaged across ALL SNRs)\nGlobal Accuracy: {acc*100:.1f}%')
plt.ylabel('True Modulation')
plt.xlabel('Predicted Modulation')
plt.tight_layout()

output_file = 'baseline_confusion_matrix.png'
plt.savefig(output_file, dpi=300)
print(f"\nSaved plots to: accuracy_vs_snr.png and {output_file}")

# Save the trained model and scaler for the live ZMQ inference pipeline
joblib.dump(model, 'amc_model.pkl')
joblib.dump(scaler, 'amc_scaler.pkl')
print("Saved model to 'amc_model.pkl' and scaler to 'amc_scaler.pkl'")
print("============================================================")
