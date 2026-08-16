# SDCS-S3 - Digital Twin AI for Software Defined Communication Systems

This repository contains the mid-semester checkpoint for the Digital Twin project for Software Defined Communication Systems (SDCS). The project simulates various communication modulations over different channels and trains an AI model to detect the modulation type from spectral features.

## What has been done so far (Mid-Semester Checkpoint)
1. **MATLAB Data Generation (`Matlab_part/`)**:
   - Developed a modular simulation for 4 digital (ASK, FSK, BPSK, QPSK) and 3 analog (AM-DSB-SC, AM-DSB-TC, FM) modulation schemes.
   - Simulated transmission over AWGN and Rayleigh Fading channels across a wide SNR sweep (-5 dB to 30 dB).
   - Extracted 4 key spectral features: 10 dB Bandwidth, Peak PSD, Spectral Flatness, and Spectral Centroid.
   - Validated simulations by comparing empirical BER against theoretical limits and generating publication-quality figures.

2. **Python AI Baseline (`python_ml/`)**:
   - Built a Python infrastructure using `pandas` and `scikit-learn` to process the MATLAB-generated datasets.
   - Trained a Random Forest classifier as an initial baseline model.
   - Filtered out extremely noisy data (SNR < 20 dB) to demonstrate that the spectral features correctly identify the 7 modulation schemes under clean conditions, achieving an accuracy of ~81%.

## What needs to be done next
- **Hyperparameter Tuning**: Optimize the AI model to maintain high accuracy at lower SNR levels.
- **False Data Injection (FDI) Defense**: Introduce adversarial "fake data" into the system to simulate hacker injections.
- **Anomaly Detection**: Implement an Isolation Forest or similar algorithm to detect and mitigate the injected FDI data in real-time, completing the Digital Twin security framework.
