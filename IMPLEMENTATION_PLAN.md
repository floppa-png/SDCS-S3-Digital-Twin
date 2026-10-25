# SDCS Digital Twin — Modulation Optimizer: IMPLEMENTATION PLAN (hand-off document)

> **For the executing model:** This file is self-contained. The full codebase audit is already done (Section 1).
> Do NOT re-audit everything — read only the files you are about to modify. Execute phases in order.
> Every phase has acceptance criteria — verify them before moving on. Keep chatter minimal; the user is token-limited.
> OS: Windows, PowerShell. Python venv: `python_ml\venv\Scripts\python.exe` (Python 3.14; has numpy 2.5, scipy 1.18,
> scikit-learn 1.9, pandas 3, flask 3.1, flask-socketio 5.6, pyzmq 27, joblib, matplotlib, seaborn). GNU Radio 3.10.12
> runs separately (radioconda / GRC) — NOT inside the venv. Do not add heavy deps. Frontend libs via CDN only.

---

## 0. User requirements (verbatim intent)

1. Every input parameter of the transmitted wave (bandwidth etc.) is editable from the website **except modulation**.
2. **Modulation** is pulled out as a **big, prominent selector above all other inputs**.
3. Website computes BER, SNR and all other metrics needed to judge how efficient the chosen modulation is for the given wave/channel.
4. **Randomize** button: when enabled, every **10–15 s (random interval)** randomizes all wave characteristics **except modulation** (modulation stays in the user's hands).
5. Performance metrics shown **below the input area**, plus a **total score** for how good the current modulation is.
6. The **Digital Twin** predicts the **best modulation** for the current inputs; a button **auto-applies** it.
7. User sees **real-time** metric updates and sees them **actually improve** after applying.
8. Insanely good-looking UI with live-updating graphs (to impress the professor).
9. Modify the **GRC flowgraph** so the website's waveform goes → GRC → Pluto (TX) and the received signal comes back.
10. **Modulation list must stay the taught set**: `AM_DSBSC, AM_DSBTC, FM, ASK, FSK, BPSK, QPSK, QAM(16-QAM)`.
    Each of them must be able to *legitimately* win in some regime (Section 4). If after honest tuning some
    cannot win without hacks, fall back to the expanded list (OOK, BFSK, BPSK, QPSK, 8PSK, 16QAM, 64QAM + AM/FM).
11. Graphify: user said **yes** → Phase 0.
12. Security rule (global): validate all input server-side, no XSS (no unescaped innerHTML), no wildcard CORS, etc.

---

## 1. Audit findings (already verified — these are the bugs to fix)

| # | File | Problem |
|---|------|---------|
| 1 | `pluto_hitl.grc`, `pluto_hitl.py`, `python_ml/pluto_hitl.py` | TX LO = 2.400 GHz, RX LO = 2.39999 GHz (10 kHz offset). Simulator sends a **real** 10 kHz passband signal as complex (imag=0); RX takes `complex_to_real` with BBDC on → spectrum folded/shifted (images at 0 Hz & 20 kHz, DC one removed by BBDC). Feature extractor assumes 10 kHz carrier → hardware classification is garbage. |
| 2 | same | `samp_rate = 100 kSPS` is below Pluto's normal minimum (~521 kSPS with default FIR). Likely rejected/clamped silently. |
| 3 | `python_ml/scenario_simulator.py` | "Data" is a deterministic alternating square wave `sign(cos(2π·bw/2·t))`, not random bits. QAM picks one random amplitude per chunk (fake). `AM_DSBSC` maps to the DSB-TC generator. No demodulator → **BER impossible**. SNR is defined over full fs bandwidth (inconsistent with MATLAB's in-band `bw_ratio`). Polls Flask over HTTP every chunk (wasteful). |
| 4 | `dashboard/app.py` | "Optimizer score" is a hand heuristic (`eff*bw*(1+margin*0.1)`), not physics. Randomizer **changes modulation** (user forbids) and runs every 5 s. Ignores `amc_model.pkl`; retrains on 350 synthetic samples at import time. SNR feature hard-coded to 20. `cors_allowed_origins="*"`. `TX_CONFIG.update(request.json)` with **no validation** (security). Forensics log written on every anomaly (711 KB committed). Ideal "twin" wave is a cosmetic hard-coded cosine. |
| 5 | `dashboard/static/app.js` | Uses `innerHTML` with server data (XSS-prone pattern). Charts minimal. |
| 6 | `Matlab_part/modulation_bank.m` (optional fixes, low priority) | FSK demod comment says non-coherent but it is coherent (cos-only correlators); FSK modulator is not phase-continuous (`cos(2π f_vec .* t)` → splatter). `rayleigh_channel` multiplies real passband by `|h|` only (no phase rotation) → optimistic for coherent schemes. Feature name `bw_10db` is actually 99 % OBW. Document these in README; fixing MATLAB is optional. |
| 7 | Root clutter | `untitled.py`, `scratch_test.py`, `test_sim.py`, `pluto_twin.grc` are scratch → move to `legacy/`. |

---

## 2. Target architecture

```
Browser (index.html + JS canvases/Chart.js)
   ▲  Socket.IO: 'frame' (10 Hz), 'twin' (~1 Hz), 'config', 'event'
   │  REST: /api/config, /api/modulation, /api/apply_best, /api/randomize, /api/preset, /api/mode, /api/state
Flask app (dashboard/app.py)  ── owns ──►  twin_core.engine.Engine (background threads)
                                              │
              ┌───────────────────────────────┼────────────────────────────────┐
         mode = "sim"                                                    mode = "pluto"
  tx_frame → channel.apply() → rx                tx_frame → IF shift → ZMQ PUSH bind tcp://127.0.0.1:5556
                                                   → GRC zeromq_pull_source → iio_pluto_sink (TX, LO=fc)
                                                   ~~ air / cable ~~
                                                   iio_pluto_source (RX, LO=fc) → zeromq_push_sink (complex)
                                                   → ZMQ PULL bind tcp://127.0.0.1:5555 → IF down-shift → rx
                                  rx → receiver.demod() → metrics → scoring → emit
                                  Twin thread: Monte-Carlo + analytic evaluation of ALL 8 mods on the
                                  (configured or estimated) channel → ranking → best → emit
                                  RF params → XML-RPC → GRC (http://127.0.0.1:8090) set_center_freq/... 
```

### New package `twin_core/` (project root)

| File | Responsibility |
|------|----------------|
| `__init__.py` | exports |
| `config.py` | `TxConfig` dataclass + `PARAM_SPEC` table (Section 3) + `validate(partial_dict) -> (clean, errors)`; whitelist keys, type-cast, clamp, reject unknown. `derive(cfg, mod) -> LinkPlan` (Section 5.1). |
| `waveforms.py` | Complex-baseband modulators for the 8 mods; RRC filter design; frame builder (preamble + header + payload + guard). |
| `channel.py` | AWGN (C/N0-consistent), Rayleigh/Rician time-varying fading (AR(1) with ρ=J0(2π f_D T_s)), CFO, Wiener phase noise. Seeded RNG. |
| `receiver.py` | Frame sync (preamble xcorr), CFO + phase estimation, AGC, matched filter, timing, per-mod demodulators, analog demods, header decode. |
| `theory.py` | Closed-form BER/SNR formulas + numeric fading averaging (Section 6). |
| `metrics.py` | All metric computations (Section 7) + rolling accumulators (reset on config change). |
| `scoring.py` | Sub-scores, profile weights, total 0–100, grade (Section 8). |
| `twin.py` | `DigitalTwin.evaluate(cfg, channel_state) -> ranking` (Section 9). Cache by config hash. |
| `hardware.py` | `PlutoBridge`: ZMQ PUSH/PULL sockets, IF shift, RX ring buffer, link detection, XML-RPC client for RF params. |
| `presets.py` | 8 scenario presets (Section 4) — each designed so a specific mod wins. |
| `engine.py` | `Engine`: state, frame loop thread (~10 Hz), twin thread (~1 Hz), randomizer thread, autopilot, event log, thread-safe config updates (lock + `cfg_version` int). |

Keep `fs = 1_000_000` S/s everywhere (Pluto-safe). Digital IF offset `f_IF = 150 kHz` in pluto mode only (moves signal off DC so BBDC/LO leakage do not destroy it).

---

## 3. Input parameters (all editable from the website except `modulation`)

`R` = included in auto-randomization; `HW` = hardware-only (sent to GRC via XML-RPC, never randomized).

| Group | key | Label | Type / range | Default | R |
|-------|-----|-------|--------------|---------|---|
| Selector | `modulation` | Modulation (BIG selector) | enum of 8 | `BPSK` | **never** |
| Source | `source_type` | Source | `digital` \| `analog` | `digital` | R (30 % analog) |
| Source | `data_rate` | Required bit rate (digital) | 1 000 – 400 000 b/s | 50 000 | R |
| Source | `msg_bw` | Message bandwidth W (analog) | 300 – 20 000 Hz | 5 000 | R |
| Source | `pcm_bits` | PCM bits/sample (analog over digital mods) | 4 – 12 | 8 | R |
| Spectrum | `alloc_bw` | Allocated channel bandwidth B | 5 000 – 400 000 Hz | 60 000 | R |
| Spectrum | `rolloff` | RRC roll-off α | 0.10 – 1.00 | 0.35 | R |
| Spectrum | `center_freq` | Center frequency (Pluto LO) | 325e6 – 3.8e9 Hz | 2.4e9 | HW |
| Link | `snr_db` | Link SNR measured in allocated B | −5 – 35 dB | 12 | R |
| Link | `channel` | Channel model | `awgn` \| `rayleigh` \| `rician` | `awgn` | R |
| Link | `k_factor_db` | Rician K | −10 – 20 dB | 6 | R |
| Link | `doppler_hz` | Max Doppler f_D | 0 – 2 000 Hz | 0 | R |
| Link | `cfo_hz` | Residual carrier offset | 0 – 5 000 Hz | 0 | R |
| Link | `phase_noise_deg` | Phase noise (rms per symbol) | 0 – 20 ° | 0 | R |
| Mod params | `am_index` | AM index μ (DSB-TC) | 0.1 – 1.0 | 0.8 | R |
| Mod params | `fm_beta` | FM index β (requested; capped by B) | 0.5 – 10 | 5 | R |
| Mod params | `fsk_h` | FSK modulation index h | 0.5 – 2.0 | 1.0 | R |
| QoS | `target_ber` | Target BER | 1e-7 – 1e-2 (log) | 1e-5 | R |
| QoS | `target_snr_out` | Target output SNR (analog) | 10 – 50 dB | 30 | R |
| QoS | `packet_bits` | Packet size | 64 – 4 096 | 1 024 | R |
| Scoring | `profile` | Scoring profile | `balanced` \| `reliability` \| `throughput` \| `low_power` | `balanced` | no |
| Pluto RF | `tx_atten_db` | TX attenuation | 0 – 89.75 dB | 30 | HW |
| Pluto RF | `rx_gain_db` | RX manual gain | 0 – 73 dB | 40 | HW |

Randomization ranges should be slightly narrower than the full range (avoid absurd links), e.g. `snr_db` U(0, 30),
`alloc_bw` log-U(10 k, 300 k), `data_rate` log-U(5 k, 300 k), `cfo_hz` 60 % zero / 40 % U(0, 3000), `doppler_hz` 60 % zero / 40 % U(0, 800),
`phase_noise_deg` 60 % zero / 40 % U(0, 12), channel {awgn .5, rayleigh .3, rician .2}.

Randomizer: when enabled, sleeps `U(10, 15)` s, then randomizes all `R` keys, bumps `cfg_version`, emits `config` +
`event{type:'randomize', next_in_s}`. The UI shows a circular countdown ring. Also a one-shot "Shuffle" button.
**Autopilot** toggle (optional demo): after each randomization, wait 3 s (audience sees score drop), then auto-apply twin best.

---

## 4. Making every taught modulation win legitimately (textbook trade-offs)

Key modelling decision (physically consistent, no hacks): **the channel is fixed by C/N0, not by per-mod SNR.**
`C/N0 [dB-Hz] = snr_db + 10·log10(alloc_bw)`. Each mod then gets `Eb/N0 = C/N0 − 10·log10(Rb_actual)`.
And **rate adaptation to fit the channel**: a transmitter never exceeds `alloc_bw`; if the requested rate does not
fit, it lowers the symbol rate (digital), lowers β / low-pass-filters the message (analog), or lowers PCM bits.
Lower rate ⇒ higher Eb/N0 but lower throughput/fidelity. This naturally produces different winners:

| Preset (presets.py) | Key settings | Expected winner | Why (textbook) |
|---|---|---|---|
| `deep_space` | digital, Rb 10 k, B 200 k, SNR −2 dB, AWGN, phase noise 8° | **BPSK** | Power-limited, BW plentiful → all fit; BPSK most tolerant of phase error (±90° decision region) & simplest coherent RX; QPSK suffers phase noise. |
| `balanced` | digital, Rb 100 k, B 75 k, SNR 14, AWGN | **QPSK** | BPSK doesn't fit (needs 135 k) → rate cut; QAM needs more Eb/N0; QPSK fits with margin. |
| `crowded_spectrum` | digital, Rb 200 k, B 70 k, SNR 28, AWGN | **QAM** | Only 16-QAM reaches the rate in B (Rb/B ≈ 2.9 b/s/Hz); SNR high enough. |
| `leo_doppler` | digital, Rb 20 k, B 120 k, SNR 14, Rayleigh f_D 600 Hz, CFO 3 kHz | **FSK** | Non-coherent FSK tolerates CFO/fast fading; coherent PSK/QAM lose lock; BW allows FSK's wider spectrum. |
| `iot_tag` | digital, Rb 20 k, B 32 k, SNR 22, CFO 2 kHz, profile `low_power` | **ASK** (OOK) | FSK doesn't fit B; CFO kills coherent schemes; OOK envelope detector = lowest complexity/power (50 % duty). |
| `am_broadcast` | analog, W 5 k, B 11 k, SNR 30, CFO 800 Hz, phase noise 10° | **AM_DSBTC** | Only DSB (2W) fits; impairments break coherent DSB-SC; envelope detector is immune. PCM digital needs ≥ ~5.4W·… → doesn't fit. |
| `coherent_voice` | analog, W 5 k, B 11 k, SNR 12, AWGN, no CFO | **AM_DSBSC** | Only DSB fits; at low SNR DSB-SC gives γ_out = γ vs DSB-TC μ²/(2+μ²)·γ (≥ 4.8 dB worse) and TC hits envelope threshold. |
| `fm_radio` | analog, W 15 k, B 200 k, SNR 20, Rayleigh f_D 50 Hz | **FM** | Wideband FM gain 3β²P_m·γ above threshold; PCM over PSK/QAM collapses under uncoded Rayleigh fading. |

Rule for the implementer: **tune preset parameters, never the physics/scoring, to make a preset's winner hold.**
`tests/test_winner_regimes.py` must assert each winner. If ≥ 2 presets cannot be made to hold without bending the
scoring, stop and switch to the expanded list (requirement 10).

Digital source + analog mods (AM/FM): not applicable (they carry analog messages). Show these cards greyed with tooltip
"Analog modulation — select an analog source". Analog source + digital mods: PCM (n bits, sampling 2.5·W) → fully applicable.

---

## 5. Signal processing specification

### 5.1 Link plan `derive(cfg, mod)` (shared by live engine and twin)
- `k` bits/symbol: BPSK 1, QPSK 2, QAM 4, ASK 1, FSK 1.
- Occupied BW model: linear mods `B_occ = Rs(1+α)`; FSK `B_occ ≈ Rs(h + 1 + α)` (validated against measured 99 % OBW in tests; if mismatch > 15 %, use calibrated factor).
- Digital source: `Rb_req = data_rate`. Analog source on digital mod: `Rb_req = pcm_bits · 2.5·W`; if it doesn't fit, reduce `pcm_bits` down to 4 first, then reduce rate (message low-pass ⇒ fidelity loss).
- `Rs = min(Rb_req/k, alloc_bw / occ_factor)`, then snap so `sps = round(fs/Rs)` is integer in [4, 1000]; `Rs = fs/sps`; `Rb = k·Rs`.
- AM (both): needs `2W`; if `B < 2W` message is low-pass to `W' = B/2` (fidelity factor `W'/W`).
- FM: `β_eff = min(fm_beta, B/(2W) − 1)`; if `β_eff < 0.3` ⇒ treat message LPF to fit with β=0.3 (narrowband FM).
- Return `LinkPlan{Rs, sps, Rb, B_occ, ebn0_db, esn0_db, snr_occ_db, gamma_analog_db, fits, notes[]}` with
  `ebn0_db = C/N0 − 10log10(Rb)`, `gamma_analog_db = C/N0 − 10log10(W')` (baseband SNR γ = S_R/(N0·W)).

### 5.2 Frame format (all digital mods; complex baseband at fs)
`[guard 16 sym zeros][preamble 63-sym m-sequence, BPSK][header 32 sym BPSK: frame_id 16 bit + cfg_version 8 bit + CRC-8][payload N sym of selected mod][guard 16 sym]`
- `N = clip(round(0.08·Rs), 128, 4096)` symbols (frame ≈ 80–100 ms max at low rates).
- Payload bits: `np.random.default_rng()` fresh random; engine keeps a ring `{frame_id: bits}` of last 128 frames (needed in pluto mode).
- Pulse shaping: RRC, span 8 symbols, roll-off α, unit energy; TX amplitude normalized so mean power = 1 (sim) / peak ≤ 0.7 (pluto, avoids DAC clip).
- Constellations (Gray): BPSK ±1; QPSK (±1±j)/√2; 16-QAM Gray ±1,±3 /√10; ASK/OOK {0, √2} (avg Es = 1); FSK: CPFSK, tones ±h·Rs/2, phase-continuous, rectangular freq pulse (not RRC); preamble/header still BPSK-RRC.
- Analog (AM/FM): no frame; message = sum of 3 tones at {0.2, 0.5, 0.85}·W' with random phases, normalized P_m = 0.5;
  DSB-SC `m(t)`, DSB-TC `(1 + μ m(t))` (|m| ≤ 1), FM `exp(j2π Δf ∫m)` with `Δf = β_eff·W'`. Complex baseband (carrier = 0 Hz in baseband; the "carrier" is the Pluto LO).

### 5.3 Channel (sim mode; also optional digital emulation on top of real RF in pluto mode)
Order: fading → CFO → phase noise → AWGN.
- AWGN: noise power set from **C/N0**: `N0 = P_s / 10^(C/N0/10)`, per-sample variance `N0·fs` (complex, split I/Q). This makes SNR in B equal `snr_db` for every mod.
- Rayleigh/Rician: complex gain h[n] per sample from AR(1) per symbol (ρ = J0(2π f_D T_s), `scipy.special.j0`), linear-interpolated; f_D = 0 ⇒ one constant draw per frame (block). Rician: `h = √(K/(K+1)) e^{jθ} + √(1/(K+1))·CN(0,1)`.
- CFO: `x · exp(j2π f_cfo n/fs)` with random initial phase.
- Phase noise: Wiener process, per-sample std = `deg2rad(phase_noise_deg)/√sps`.

### 5.4 Receiver
- Frame sync: normalized cross-correlation with preamble waveform; peak → timing. In pluto mode search the RX ring buffer, extract complete frames.
- CFO estimate: phase of `Σ r[n]·conj(r[n−L/2])·conj(p…)` over preamble halves (Moose/ Kay); correct. Phase & gain from preamble LS fit. AGC normalization.
- Linear mods: matched RRC → sample at optimal offset → 2nd-order decision-directed PLL (loop BW ≈ 0.01·Rs) to track residual CFO/phase noise → slicer → bits. (Costas for BPSK, 4th-power/DD for QPSK, DD for QAM.)
- ASK/OOK: non-coherent: |matched-filter| → threshold = midpoint of two-cluster k-means (2 iters) on |y|.
- FSK: non-coherent energy detector: |Σ r·e^{−j2π f0 t}|² vs |Σ r·e^{−j2π f1 t}|² per symbol (robust to CFO < Rs/4).
- Header decode (BPSK) → frame_id → look up TX bits → count errors. Frames with CRC fail are counted as lost packets (PER).
- Analog: DSB-SC coherent (Costas loop phase recovery; with CFO it will fail — intended), DSB-TC envelope `|r| − mean`, FM discriminator `angle(r[n]·conj(r[n−1]))·fs/(2π Δf)`; LPF (Butterworth order 6, cutoff W'); output SNR via LS-alignment (port `measure_analog_snr` from `Matlab_part/modulation_bank.m` lines 380–432, including xcorr delay search).
- PCM path: decode bits → dequantize → output SNR vs original message.

---

## 6. Theory (`theory.py`) — overlay curves + twin fallback when MC errors < 10

AWGN, per bit, `γb = Eb/N0` (linear):
- BPSK, QPSK: `Q(√(2γb))`
- 16-QAM (Gray): `0.75·Q(√(0.8γb))` (≈ (4/k)(1−1/√M) Q(√(3k γb/(M−1))))
- ASK/OOK non-coherent: `0.5·exp(−γb/2)` ; coherent: `Q(√γb)` (show non-coherent, it's what we implement)
- FSK non-coherent orthogonal: `0.5·exp(−γb/2)`
- Fading: numerically average the AWGN formula over the fading pdf of |h|² (draw 20 000 samples of |h|² once per channel config; Rayleigh exponential, Rician non-central χ²). Closed-form checks for tests: Rayleigh BPSK `0.5(1−√(γ̄/(1+γ̄)))`, NC-FSK `1/(2+γ̄)`.
Analog (γ = S_R/(N0 W'), P_m = 0.5):
- DSB-SC: `SNR_o = γ`
- DSB-TC: `SNR_o = μ²P_m/(1+μ²P_m)·γ`; threshold: if CNR in 2W' < 10 dB apply steep degradation (use MC value).
- FM: `SNR_o = 3β²P_m·γ` above threshold (CNR in Carson BW `2(β+1)W'` ≥ 10 dB); below threshold use MC.
- PCM: `SNR_o = 2^{2n} / (1 + 4(2^{2n}−1)·P_b)` (tone full-scale; cap at 6.02n + 1.76 dB).
Shannon: `C = B·log2(1 + SNR_B)`.

---

## 7. Metrics (computed live for current mod, and predicted by twin for all mods)

| Metric | Definition | Shown as |
|---|---|---|
| BER (measured) | errors / bits over rolling window (last ≤ 2·10⁶ bits or since cfg change); show "< 1/N" if 0 errors | tile + sparkline, log |
| BER (theory) | Section 6 at current Eb/N0 & channel | small text under BER |
| SER | symbol errors / symbols | tile |
| PER | lost or errored packets (`packet_bits`) / packets | tile |
| Eb/N0, Es/N0 | from link plan | tile |
| SNR (est.) | data-aided from preamble: `10log10(|ĥ|²/σ̂²)` mapped to occupied BW → compare to set value | tile ("set vs measured") |
| EVM (rms %) | linear mods: `√(mean|y−ŝ|²)/√(mean|ŝ|²)` | tile |
| Spectral efficiency | `Rb / B_occ` b/s/Hz | tile |
| Goodput | `Rb·(1−PER)·payload_fraction` | tile (kb/s) |
| Rate achievement | goodput / required rate | bar |
| Shannon capacity & efficiency | `C`, `Rb/C` %, gap to capacity at target BER (dB) | tile |
| OBW (99 %) | measured from Welch PSD vs `alloc_bw` | tile with compliance badge |
| Link margin | `Eb/N0_avail − Eb/N0_req(target_ber)` dB (req solved by bisection on theory) | tile |
| PAPR | `10log10(max|x|²/mean|x|²)` of TX waveform | tile |
| Output SNR (analog) | measured; theory alongside | replaces BER tiles for analog |
| Figure of merit (analog) | `SNR_o / γ` | tile |
| Total score | Section 8 | gauge |

---

## 8. Scoring (`scoring.py`) — all sub-scores in [0, 1]

- **Reliability** `S_rel`: digital `clip(−log10(max(BER,1e-9)) / −log10(target_ber), 0, 1)`; analog/PCM `clip(SNR_o_dB / target_snr_out, 0, 1)`.
- **Rate** `S_rate`: digital `clip(goodput / data_rate, 0, 1)`; analog: message-bandwidth fidelity `W'/W`.
- **Spectral fit** `S_bw`: `1` if OBW ≤ alloc_bw else `exp(−3·(OBW/alloc_bw − 1))` (should be ~1 by design; guards measurement).
- **Power / margin** `S_pwr`: `sigmoid(link_margin_dB / 3)` (digital); analog: `sigmoid((SNR_o − target)/3)`.
- **Complexity** `S_cplx` (receiver complexity, textbook): ASK .95, AM_DSBTC 1.0, FSK .85, FM .80, BPSK .70, AM_DSBSC .65, QPSK .55, QAM .35.
- **PAPR** `S_papr`: `clip(1 − (PAPR_dB − 0)/10, 0, 1)` (FM/FSK constant envelope ≈ 1).

Profiles (weights sum to 1):

| profile | rel | rate | bw | pwr | cplx | papr |
|---|---|---|---|---|---|---|
| balanced | .35 | .25 | .10 | .15 | .10 | .05 |
| reliability | .55 | .10 | .05 | .20 | .05 | .05 |
| throughput | .25 | .45 | .15 | .10 | .03 | .02 |
| low_power | .25 | .15 | .05 | .20 | .20 | .15 |

`total = round(100 · Σ w·S)`; hard rule: if `S_rel < 0.2` (link unusable) multiply total by `0.5`. Grade: A+ ≥ 90, A ≥ 80, B ≥ 65, C ≥ 50, D ≥ 35, F.
The live score uses **measured** metrics (EMA-smoothed over ~1 s); twin scores use predicted metrics. Display both.

---

## 9. Digital Twin (`twin.py`)

- Input: current `TxConfig` + **channel state**. Sim mode: channel state = config. Pluto mode: estimated from live RX
  (measured SNR → C/N0, measured CFO, measured fading variance of |ĥ| across frames) — this is what makes it a *twin*.
- For each of the 8 mods: `derive()` → quick Monte-Carlo through the same `waveforms`/`channel`/`receiver` code with
  ≥ 20 000 bits (digital) or 0.2 s message (analog); if errors < 10 use theory (Section 6) and flag `source:'theory'`.
- Compute metrics (Section 7) → score (Section 8) → ranking. Not-applicable mods get `score=0, reason`.
- `confidence` = margin between #1 and #2 scores mapped to %.
- Run in its own thread every ~1 s and immediately on config change (debounced 300 ms); cache by config hash; cap runtime (if > 800 ms, reduce bits).
- **Twin fidelity**: compare twin's predicted score/BER for the *current* mod with the live measured value → show "Twin error ±x pts". Great talking point.
- BER-vs-Eb/N0 curves for all mods (theory, current channel) recomputed on channel change → sent in `twin` payload for the chart.
- Optional (Phase 7): keep AMC classifier as "Blind AMC verification" (retrain on new complex-baseband features via `python_ml/train_amc.py`, load pkl, use **estimated** SNR feature, not 20).

---

## 10. Backend API (`dashboard/app.py`) — Flask + Flask-SocketIO, `async_mode='threading'`

- Bind `127.0.0.1:5000`. `cors_allowed_origins=["http://127.0.0.1:5000","http://localhost:5000"]`. `MAX_CONTENT_LENGTH = 4 KB`. Require `Content-Type: application/json` on POST (cheap CSRF mitigation for localhost). Never echo raw input into HTML.
- `GET /` → index.html
- `GET /api/state` → `{config, cfg_version, mode, link_up, randomizer:{enabled,next_in_s}, autopilot, presets:[names]}`
- `POST /api/config` body: partial dict of Section 3 keys **except `modulation`** → `config.validate` → 200 `{config}` or 400 `{errors}`.
- `POST /api/modulation` `{modulation}` (whitelist) → 200.
- `POST /api/apply_best` → sets modulation = twin best; emits `event{type:'apply', from, to, predicted_gain}`.
- `POST /api/randomize` `{enabled: bool}` and `POST /api/shuffle` (one-shot).
- `POST /api/autopilot` `{enabled: bool}`; `POST /api/preset` `{name}` (whitelist); `POST /api/mode` `{mode:'sim'|'pluto'}`; `POST /api/reset_stats`.
- Socket emits:
  - `frame` (~10 Hz): `{t, cfg_version, mod, source:'sim'|'pluto', metrics{...Section 7}, score{total, grade, subs{}}, viz{const:[[i,q]×≤600], psd_db:[256], psd_f:[f0,f1], eye:[[...]×≤48 traces of 2·sps' pts (resampled to 64)], iq:{i:[400], q:[400]}}}` — round floats to 4 sig. digits.
  - `twin` (~1 Hz): `{cfg_version, ranking:[{mod, score, grade, applicable, reason, metrics:{ber, ebn0, se, goodput, snr_out, margin}}], best, confidence, fidelity, curves:{ebn0:[...], mods:{BPSK:[...],...}}}`
  - `config` on any change; `event` for randomize/apply/preset/link/mode changes (UI toast + log).

---

## 11. Frontend (rewrite `dashboard/templates/index.html`, `dashboard/static/css/style.css`, `dashboard/static/js/*.js`)

Libraries (CDN, pinned versions + SRI if available): socket.io 4.7.x, Chart.js 4.4.x, GSAP 3.12.x. Fonts: **Space Grotesk** (UI) + **JetBrains Mono** (numbers).
Theme: deep space navy `#060A13`, glass panels `rgba(255,255,255,.04)` + 1px `rgba(148,163,184,.14)` border + backdrop-blur, animated subtle grid/noise background with 2 slow gradient orbs.
Accents: cyan `#22D3EE`, violet `#8B5CF6`, good `#A3E635`, warn `#F59E0B`, bad `#F43F5E`. Fixed per-mod colors (used across all charts):
BPSK `#22D3EE`, QPSK `#8B5CF6`, QAM `#F472B6`, ASK `#F59E0B`, FSK `#A3E635`, AM_DSBSC `#60A5FA`, AM_DSBTC `#FB923C`, FM `#2DD4BF`.

Layout (single page, top → bottom; unique `id`s on every interactive element; one `<h1>`; title + meta description):
1. **Header bar**: logo "SDCS · Digital Twin", status pills (Engine ●, Pluto LINK ●/○ with RX rate, Twin ●), Sim/Pluto mode segmented toggle, FPS.
2. **Modulation hero selector** (full width, big): 8 cards (~140 px tall) each with an animated SVG glyph (constellation dots / waveform), name, "k b/sym" or "analog", live **twin-predicted score badge**, greyed + tooltip if not applicable. Selected card: glowing border in its color. Twin's best card gets an animated "★ TWIN PICK" ribbon. Click = POST /api/modulation.
3. **Waveform input panel**: grouped accordions/cards (Source · Spectrum · Link/Channel · Modulation params · QoS & scoring · Pluto RF). Each param = range slider + numeric field + unit, live value, debounced POST (250 ms). Analog-only/digital-only fields show/hide by `source_type`. Toolbar: **Auto-Randomize** toggle with SVG countdown ring (next 10–15 s), **Shuffle once**, **Presets** dropdown, **Autopilot** toggle, **Reset stats**.
4. **Performance panel** (directly below inputs): big animated radial **score gauge** (0–100, color by grade, GSAP tween) + grade letter + "measured vs twin-predicted" sub-label; sub-score bars (6); metric tiles grid (Section 7) each with value (GSAP count-up), unit, ▲/▼ delta vs 5 s ago (green/red), 30-s sparkline (tiny canvas).
5. **Digital Twin panel**: horizontal bar ranking of all 8 mods (Chart.js, per-mod colors, current outlined, best glowing); recommendation card: "Switch BPSK → QPSK · +27 pts · BER 3e-2 → 4e-6 · goodput +48 %" + huge **Apply Twin Recommendation** button (disabled when already best; pulses when gain ≥ 10 pts); confidence % and twin-fidelity readout.
6. **Live visualization grid** (2–3 columns, responsive):
   - Constellation (custom canvas, phosphor persistence: fade previous frame with `rgba(6,10,19,.25)` fill, additive glow dots in mod color, ideal points as rings).
   - Spectrum: PSD line (canvas, gradient fill) with allocated-BW shaded band + OBW markers, plus **waterfall** beneath (canvas, scrolling, colormap).
   - Eye diagram (canvas persistence, digital) / demodulated message vs original (analog).
   - Time-domain I/Q (canvas, two traces).
   - **BER vs Eb/N0** (Chart.js, log-y): theory curves for all mods in their colors + pulsing marker at current operating point (and measured BER point).
   - **Score history timeline** (Chart.js, last 120 s): live score line; vertical annotation lines labelled "APPLY BPSK→QPSK", "RANDOMIZE", "PRESET" (draw via custom plugin, no extra lib). This is the "see it improve" chart.
   - Radar: current mod sub-scores vs twin best.
7. **Event log** (textContent only) + compact footer with formulas link/tooltips ("ⓘ" on each metric explaining the formula — professors love this).
Animations: GSAP entrance stagger, card hover lift/tilt, toast on events, confetti-free "glow pulse" on score improvement ≥ 10. Use `requestAnimationFrame` for canvases; drop frames if tab hidden. All DOM text via `textContent` (no `innerHTML` with data).
Files: `static/js/main.js` (socket + state), `static/js/controls.js` (inputs, selector, buttons), `static/js/viz.js` (canvas renderers), `static/js/charts.js` (Chart.js charts), `static/css/style.css`.

---

## 12. GNU Radio / Pluto (website → GRC → Pluto → air → GRC → website)

Rewrite `pluto_hitl.grc` (GRC 3.10.12 YAML; keep `generate_options: qt_gui` so local QT plots are available; title "SDCS Digital Twin — Pluto HITL"):
- Variables: `samp_rate = 1000000`, `center_freq = 2400000000`, `tx_atten = 30`, `rx_gain = 40`, `rf_bw = 1500000`.
- `xmlrpc_server` block: `addr: 127.0.0.1`, `port: '8090'` → exposes `set_center_freq`, `set_tx_atten`, `set_rx_gain`, `set_samp_rate`, `set_rf_bw` (auto-generated setters).
- `zeromq_pull_source_0`: type complex, `tcp://127.0.0.1:5556`, bind False, timeout 100, hwm −1 → `iio_pluto_sink_0`: uri `ip:192.168.2.1`, frequency `center_freq`, samplerate `samp_rate`, bandwidth `rf_bw`, attenuation1 `tx_atten`, buffer_size 8192, cyclic False, filter_source 'Auto'.
- `iio_pluto_source_0`: uri `ip:192.168.2.1`, frequency `center_freq` (**same LO as TX**), samplerate `samp_rate`, bandwidth `rf_bw`, gain1 'manual', manual_gain1 `rx_gain`, quadrature True, rfdc True, bbdc True, buffer_size 8192, len_tag_key '' → `zeromq_push_sink_0`: type **complex** (NOT complex_to_real), `tcp://127.0.0.1:5555`, bind False.
- Optional: `qtgui_freq_sink_x` + `qtgui_const_sink_x` on RX for local viewing.
- Remove `blocks_complex_to_real`.
- Regenerate `pluto_hitl.py` (press "Generate" in GRC, or hand-write the equivalent) and update headless `python_ml/pluto_hitl.py` the same way (+ `from xmlrpc.server import SimpleXMLRPCServer` thread exposing setters, as GRC generates).
Python side (`twin_core/hardware.py`): PUSH `bind tcp://127.0.0.1:5556` with `SNDHWM=4` (backpressure paces TX to real time), PULL `bind tcp://127.0.0.1:5555`; TX: `x·exp(+j2π f_IF n/fs)` with continuous phase; RX: down-shift by `f_IF`, low-pass (FIR, cutoff alloc_bw/2+margin), ring buffer 2 s; `link_up` if > 0.5·fs samples/s arriving. XML-RPC via `xmlrpc.client.ServerProxy("http://127.0.0.1:8090", allow_none=True)` with socket timeout 0.5 s; values validated by `config.py` before sending; failures → `event{type:'hw_error'}`, never crash.
In pluto mode, SNR control = digital AWGN added before TX (labelled "injected noise"); the twin uses the **measured** SNR. Fading/CFO emulation optionally applied digitally pre-TX (toggle "Emulate channel on top of RF").

`run_project.py`: start `dashboard/app.py` (engine inside, default mode `sim`); `--hitl` flag sets mode `pluto` at start and prints: "Open pluto_hitl.grc in GRC → Execute → then open http://127.0.0.1:5000". Remove the separate simulator process and the "press ENTER" step (engine auto-detects link). Kill children on exit.

**When to plug in the Pluto:** only at Phase 6. Everything before is verified in sim mode.

---

## 13. Execution phases & acceptance criteria

**Phase 0 — housekeeping (5 min)**
- Run `graphify .` in project root (user approved). Append to `.gitignore`:
  ```
  # Graphify output
  graphify-out/
  .graphify_analysis.json
  # Runtime logs
  dashboard/*.log
  ```
- Move `untitled.py`, `scratch_test.py`, `test_sim.py`, `pluto_twin.grc`, `python_ml/scenario_simulator.py` (after Phase 3), `python_ml/synthetic_tx.py`, `python_ml/live_zmq_classifier.py` into `legacy/` (don't delete). Create `requirements.txt` from the venv list above.

**Phase 1 — DSP core** (`config.py, waveforms.py, channel.py, receiver.py, theory.py, metrics.py`)
- `tests/test_ber_awgn.py`: for BPSK, QPSK, QAM, ASK(NC), FSK(NC) at Eb/N0 ∈ {0,4,8} dB, measured BER within ±25 % (or ±2σ binomial) of theory with ≥ 2e5 bits.
- `tests/test_analog.py`: DSB-SC SNR_o ≈ γ ± 1.5 dB; FM above threshold within ± 2 dB of 3β²P_mγ (cap at 50 dB numeric limit).
- Frame sync recovers frames with CFO up to 3 kHz (sim) for BPSK header.
- Run tests with `python_ml\venv\Scripts\python.exe -m pytest -q` (install pytest into venv if missing — needs network/bypass approval; alternatively write tests as plain `python tests\run_all.py` with asserts to avoid the dep).

**Phase 2 — Twin + scoring + presets** (`scoring.py, twin.py, presets.py`)
- `tests/test_winner_regimes.py`: each preset → expected winner (Section 4). Twin eval time < 800 ms per config on this laptop.

**Phase 3 — Engine + backend** (`engine.py, hardware.py`, rewrite `dashboard/app.py`)
- `tests/test_api_validation.py` using Flask test client: unknown keys → 400; out-of-range → clamped or 400 (pick one, be consistent: **400 with message**); modulation not changeable via `/api/config`; bad JSON → 400.
- Randomizer: intervals in [10,15] s; modulation unchanged across 20 randomizations (unit test with time mocked).
- App boots in < 5 s (no training at import).

**Phase 4 — Frontend** (Section 11). Verify in browser (browser_subagent): all panels render, frame rate ≥ 8 Hz, no console errors, selecting a mod updates within 1 s, Apply button changes mod and score timeline shows a rise with an "APPLY" marker.

**Phase 5 — Docs**: rewrite `README.md` (architecture diagram, formulas, presets table, how to run), `Instructions.txt` (new run steps). Mention MATLAB caveats (Section 1 #6).

**Phase 6 — Hardware (ask user to plug in Pluto now)**: open new `pluto_hitl.grc` in GRC, Execute; `python run_project.py --hitl`; verify link pill turns green, constellation locks for BPSK/QPSK at tx_atten 30 / rx_gain 40 (cable or antennas ~1 m), measured SNR shown, XML-RPC sliders retune Pluto (watch GRC QT freq sink). Troubleshoot: if no samples → check ZMQ bind/connect roles, sample rate accepted (`iio_attr`), firewall for localhost.

**Phase 7 — optional polish**: AMC verification panel (retrained), FDI injection button + Isolation Forest panel (reuse idea from old app, train on new features at startup in background thread, never block boot), PDF/PNG export of the session report.

---

## 14. Security checklist (must pass before "done")
- [ ] All POST inputs validated via `PARAM_SPEC` whitelist; `modulation`, `preset`, `mode`, `profile`, `channel`, `source_type` enum-checked.
- [ ] No wildcard CORS; server bound to 127.0.0.1; JSON content-type enforced; `MAX_CONTENT_LENGTH` set.
- [ ] No `innerHTML` with server/user data in JS (use `textContent` / DOM creation).
- [ ] XML-RPC target hard-coded to localhost; values clamped before sending.
- [ ] No pickle loading from user-controlled paths (only bundled `amc_model.pkl`, Phase 7).
- [ ] Log files size-capped / rotated (`logging.handlers.RotatingFileHandler`, 1 MB).
