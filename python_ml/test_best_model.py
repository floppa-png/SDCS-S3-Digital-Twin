import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

df = pd.read_csv('../Matlab_part/ground_truth_dataset.csv')
df = df.dropna(subset=['BW_10dB', 'PeakPSD_dB', 'SpectralFlatness', 'SpectralCentroid', 'ReceivedSNR_dB'])

# Use all data
X = df[['BW_10dB', 'PeakPSD_dB', 'SpectralFlatness', 'SpectralCentroid', 'ReceivedSNR_dB']]
y = df['ModType']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print("Training best model on ALL data...")
rf_model = RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_split=5, class_weight='balanced', random_state=42)
rf_model.fit(X_train_scaled, y_train)

y_pred = rf_model.predict(X_test_scaled)
print(f"Accuracy: {accuracy_score(y_test, y_pred)*100:.2f}%")

# Cross validation to check overfitting
cv_scores = cross_val_score(rf_model, X_train_scaled, y_train, cv=5)
print(f"CV Accuracy: {cv_scores.mean()*100:.2f}% (+/- {cv_scores.std()*2*100:.2f}%)")
