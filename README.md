# SDCS · Physical Digital Twin & Pluto SDR Benchmark Platform

An industrial-grade, physics-consistent **Digital Twin** and hardware-in-the-loop (HITL) modulation benchmarking suite for **Software Defined Communication Systems (SDCS)**.

The platform continuously evaluates, scores, and predicts optimal modulation schemes across the 8 taught analog and digital modulations under realistic physical impairments (AWGN, time-varying Rayleigh/Rician fading, Carrier Frequency Offset (CFO), and Wiener phase noise).

---

## 1. System Architecture

```mermaid
graph TD
    subgraph Frontend ["Web Dashboard (http://127.0.0.1:5000)"]
        UI["Hero Modulation Selector & Control Toolbar"]
        Viz["Canvases: Phosphor Constellation, PSD/Waterfall, Eye, IQ"]
        Charts["Chart.js: Score Timeline, BER Curves, Twin Ranking"]
        Gauges["Radial Score Gauge (0-100) & Sub-score Bars"]
    end

    subgraph Backend ["Python Core & Telemetry Engine (fs = 1 MSPS)"]
        Eng["Engine (engine.py): Streaming @ 10 Hz"]
        Twin["Digital Twin (twin.py): Optimization @ 1 Hz"]
        DSP["DSP Core: waveforms.py, channel.py, receiver.py"]
        Theory["Analytical Theory & Scorer: theory.py, scoring.py"]
        Bridge["PlutoBridge (hardware.py): ZMQ & XML-RPC"]
    end

    subgraph Hardware ["Pluto SDR Hardware-in-the-Loop"]
        GRC["GNU Radio Flowgraph (pluto_hitl.grc)"]
        Pluto["ADALM-PLUTO SDR (Over-the-Air RF @ 2.4 GHz)"]
    end

    UI -->|REST POST /api/*| Eng
    Eng -->|Socket.IO Telemetry @ 10 Hz| Viz
    Eng -->|Socket.IO Telemetry @ 10 Hz| Gauges
    Twin -->|Socket.IO Prediction @ 1 Hz| Charts
    Eng <--> DSP
    DSP <--> Theory
    Eng <-->|ZMQ :5556 (TX) / :5555 (RX)| Bridge
    Bridge <-->|XML-RPC :8090 (LO/Gain/Atten)| GRC
    Bridge <-->|ZMQ Complex IQ + 150 kHz IF| GRC
    GRC <-->|IIO Driver| Pluto
```

---

## 2. Supported Modulation Schemes

The platform strictly supports the 8 core taught communication schemes:

| Modulation | Category | Bits/Symbol ($k$) | Description / Constellation |
|---|---|---|---|
| **BPSK** | Digital | 1 | Binary Phase Shift Keying ($\pm 1$, RRC shaped) |
| **QPSK** | Digital | 2 | Quadrature Phase Shift Keying ($(\pm 1 \pm j)/\sqrt{2}$, Gray mapped) |
| **16-QAM** | Digital | 4 | 16-state Quadrature Amplitude Modulation ($\{\pm 1, \pm 3\}/\sqrt{10}$) |
| **ASK** | Digital | 1 | Amplitude Shift Keying / On-Off Keying ($\{0, \sqrt{2}\}$) |
| **FSK** | Digital | 1 | Continuous-Phase Frequency Shift Keying (Tones $\pm h R_s / 2$) |
| **AM_DSBSC** | Analog | — | Double-Sideband Suppressed-Carrier ($m(t) \cos \omega_c t$) |
| **AM_DSBTC** | Analog | — | Double-Sideband Transmitted-Carrier ($(1 + \mu m(t)) \cos \omega_c t$) |
| **FM** | Analog | — | Frequency Modulation ($\exp(j 2\pi \Delta f \int m(\tau) d\tau)$) |

---

## 3. Physical Link Budgeting: Fixed $C/N_0$ Model

Unlike naive simulators that hold $E_b/N_0$ constant, this platform models reality: **the channel is defined by its Carrier-to-Noise spectral density ($C/N_0$), not per-modulation SNR**:

$$\frac{C}{N_0}\text{ [dB-Hz]} = \text{SNR}_B + 10 \log_{10}(B_{\text{alloc}})$$

When a modulation's symbol rate $R_s$ or bit rate $R_b$ adapts to fit the allocated channel bandwidth $B_{\text{alloc}}$, the realized energy-per-bit to noise density changes accordingly:

$$\frac{E_b}{N_0}\text{ [dB]} = \frac{C}{N_0} - 10 \log_{10}(R_{b,\text{actual}})$$

### Rate Adaptation Rules
1. **Linear Digital Schemes**: Occupied bandwidth $B_{\text{occ}} = R_s(1 + \alpha)$. If requested $R_b / k > B_{\text{alloc}} / (1 + \alpha)$, the rate is throttled to fit the channel.
2. **FSK**: Carson bandwidth $B_{\text{occ}} = R_s(h + 1 + \alpha)$.
3. **AM**: Requires $2W$. If $B < 2W$, the message is low-pass filtered to $W' = B/2$ (fidelity factor $W'/W$).
4. **FM**: Carson bandwidth $B = 2(\beta + 1)W$. Effective modulation index $\beta_{\text{eff}} = \min(\beta, B/(2W) - 1)$.

---

## 4. Mathematical Performance Formulas

### Theoretical Digital BER
- **BPSK / QPSK in AWGN**:
  $$P_b = Q\left(\sqrt{2 \gamma_b}\right) = \frac{1}{2}\text{erfc}\left(\sqrt{\gamma_b}\right)$$
- **16-QAM in AWGN** (Gray coded):
  $$P_b \approx \frac{3}{8}\text{erfc}\left(\sqrt{\frac{4}{10}\gamma_b}\right)$$
- **Non-Coherent Orthogonal FSK in AWGN**:
  $$P_b = \frac{1}{2}\exp\left(-\frac{\gamma_b}{2}\right)$$
- **Rayleigh Fading**:
  - BPSK/QPSK: $P_b = \frac{1}{2}\left(1 - \sqrt{\frac{\bar{\gamma}_b}{1 + \bar{\gamma}_b}}\right)$
  - FSK (Non-coherent): $P_b = \frac{1}{2 + \bar{\gamma}_b}$
  - ASK (OOK Envelope): $P_b = \frac{1}{2 + \bar{\gamma}_b / 2}$

### Theoretical Analog Output SNR
- **AM-DSBSC**: $\text{SNR}_{o} = \gamma = \frac{S_R}{N_0 W'}$
- **AM-DSBTC** (Envelope detector):
  $$\text{SNR}_{o} = \frac{\mu^2 P_m}{1 + \mu^2 P_m} \cdot \gamma$$
  *(For peak-normalized multitone, $P_m \approx 0.186$)*
- **FM** (Discriminator above threshold):
  $$\text{SNR}_{o} = 3 \beta_{\text{eff}}^2 P_m \cdot \gamma$$

---

## 5. Multi-Objective Scoring Function

The total performance score (0 to 100) is evaluated across 6 normalized sub-scores $S \in [0, 1]$:
1. **Reliability ($S_{\text{rel}}$)**: $-\log_{10}(\text{BER}) / -\log_{10}(\text{BER}_{\text{target}})$ (Digital) or $\text{SNR}_o / \text{SNR}_{\text{target}}$ (Analog).
2. **Rate Achievement ($S_{\text{rate}}$)**: $\text{Goodput} / \text{DataRate}_{\text{req}}$ (Digital) or $W'/W$ (Analog).
3. **Spectral Fit ($S_{\text{bw}}$)**: $1.0$ if $B_{\text{occ}} \le B_{\text{alloc}}$, decaying exponentially if exceeded.
4. **Power Margin ($S_{\text{pwr}}$)**: $\text{sigmoid}(\text{Margin}_{\text{dB}} / 3)$.
5. **Receiver Complexity ($S_{\text{cplx}}$)**: ASK 0.95, AM-DSBTC 1.00, FSK 0.85, FM 0.80, BPSK 0.70, AM-DSBSC 0.65, QPSK 0.55, 16-QAM 0.35.
6. **PAPR Efficiency ($S_{\text{papr}}$)**: $\text{clip}(1 - \text{PAPR}_{\text{dB}} / 10, 0, 1)$.

### Profile Weights
| Profile | Rel | Rate | BW | Pwr | Cplx | PAPR |
|---|---|---|---|---|---|---|
| **Balanced** | 0.35 | 0.25 | 0.10 | 0.15 | 0.10 | 0.05 |
| **Reliability** | 0.55 | 0.10 | 0.05 | 0.20 | 0.05 | 0.05 |
| **Throughput** | 0.25 | 0.45 | 0.15 | 0.10 | 0.03 | 0.02 |
| **Low Power** | 0.25 | 0.15 | 0.05 | 0.20 | 0.20 | 0.15 |

*Hard Penalty*: If $S_{\text{rel}} < 0.2$ (broken link), total score is penalized by 50%.

---

## 6. Physical Scenario Presets & Verified Winners

Every taught modulation wins legitimately in its natural textbook operating regime:

| Preset Name | Key Channel & Physical Impairments | Expected Winner | Physical Rationale |
|---|---|---|---|
| `deep_space` | SNR $-2$ dB, $B$ 200 kHz, AWGN, Phase Noise $8^\circ$ | **BPSK** | Power-limited; BPSK has widest decision margin ($\pm 90^\circ$). |
| `urban_cellular` | SNR $14$ dB, $B$ 75 kHz, $R_b$ 100 kbps, AWGN | **QPSK** | BPSK exceeds bandwidth; QPSK fits bandwidth cleanly. |
| `leo_doppler` | Rayleigh $f_D = 600$ Hz, CFO $3000$ Hz, SNR $14$ dB | **FSK** | Non-coherent energy detector immune to carrier unlock and Doppler floor. |
| `iot_tag` | Low-Power Profile, $B$ 32 kHz, CFO $2000$ Hz | **ASK** | Diode envelope detector has lowest receiver complexity & power. |
| `am_broadcast` | Analog, $B$ 11 kHz, CFO $800$ Hz, Phase Noise $10^\circ$ | **AM_DSBTC** | Envelope detector is immune to carrier frequency offset. |
| `coherent_voice` | Analog, $B$ 11 kHz, SNR $12$ dB, Clean AWGN | **AM_DSBSC** | Full suppressed-carrier power efficiency without envelope thresholding. |
| `fm_radio` | Analog, $B$ 200 kHz, SNR $20$ dB, Rayleigh $f_D = 50$ Hz | **FM** | Wideband FM gain ($3\beta^2 P_m \gamma$) exceeds AM limits above threshold. |

---

## 7. How to Run the Platform

### Running in High-Fidelity Simulation Mode (No Hardware Needed)
```powershell
# 1. Activate Python virtual environment
.\python_ml\venv\Scripts\activate

# 2. Launch master runner
python run_project.py

# 3. Open browser interface
# Navigate to: http://127.0.0.1:5000
```

### Running with Pluto SDR (Phase 6 HITL Mode)
```powershell
# 1. Connect ADALM-PLUTO via USB (verify ping 192.168.2.1)
# 2. Launch GNU Radio proxy:
python python_ml/pluto_hitl.py
# (Or open pluto_hitl.grc in GNU Radio Companion and click Execute)

# 3. Start master runner with hardware enabled:
python run_project.py --hitl

# 4. Open browser interface: http://127.0.0.1:5000
# Observe Pluto LINK indicator turn green with 1 MSPS throughput!
```

---

## 8. Verification & Test Suite

The platform includes a rigorous automated test suite verifying every layer of the DSP core, scoring, and API:

```powershell
# Run DSP Bit Error Rate & AWGN verification
.\python_ml\venv\Scripts\python.exe tests/test_ber_awgn.py

# Run Analog Demodulation & Zero-Phase SNR tests
.\python_ml\venv\Scripts\python.exe tests/test_analog.py

# Run Digital Twin Winner Regimes (8/8 Preset Assertions)
.\python_ml\venv\Scripts\python.exe tests/test_winner_regimes.py

# Run Backend API Validation & Security Suite
.\python_ml\venv\Scripts\python.exe tests/test_api_validation.py
```

All tests pass with 100% deterministic mathematical precision.
