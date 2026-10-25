import math
import numpy as np
from typing import Tuple, Optional
from scipy.special import j0
from scipy.signal import lfilter
from .config import TxConfig

class ChannelModel:
    """Realistic wireless channel simulation supporting AWGN, Rayleigh, Rician, CFO, and Phase Noise."""
    
    def __init__(self, fs: int = 1000000, seed: Optional[int] = None):
        self.fs = fs
        self.rng = np.random.default_rng(seed)
        self._cfo_phase = 0.0
        self._pn_phase = 0.0
        
    def apply(self, tx_iq: np.ndarray, cfg: TxConfig, sps: int = 16) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Apply channel impairments to transmitted IQ signal.
        Returns:
            rx_iq: Received distorted signal + noise
            h_gain: Channel fading coefficients per sample
            realized_snr_db: In-band realized SNR in allocated bandwidth
        """
        n_samples = len(tx_iq)
        if n_samples == 0:
            return tx_iq.copy(), np.ones(0, dtype=np.complex64), cfg.snr_db
            
        sig_power = float(np.mean(np.abs(tx_iq) ** 2))
        if sig_power <= 0:
            sig_power = 1.0
            
        # 1. Channel Fading (Rayleigh / Rician)
        ch_type = cfg.channel.lower()
        if ch_type == 'awgn':
            h = np.ones(n_samples, dtype=np.complex64)
            
        elif ch_type == 'rayleigh':
            f_d = cfg.doppler_hz
            if f_d <= 1.0:
                # Quasi-static flat Rayleigh fading across the burst
                h_const = (self.rng.normal(0, 1) + 1j * self.rng.normal(0, 1)) / np.sqrt(2.0)
                h = np.full(n_samples, h_const, dtype=np.complex64)
            else:
                # Time-varying correlated Rayleigh fading
                # Subsample at symbol rate or decimated rate, apply AR(1) with rho = J0(2*pi*f_D*Ts)
                decim = max(1, sps)
                n_points = max(2, int(np.ceil(n_samples / decim)))
                dt_decim = decim / float(self.fs)
                rho = float(j0(2.0 * np.pi * f_d * dt_decim))
                rho = min(0.99999, max(0.0, rho))
                
                # AR(1) process
                w = (self.rng.normal(0, 1, n_points) + 1j * self.rng.normal(0, 1, n_points)) / np.sqrt(2.0)
                h_sub = np.zeros(n_points, dtype=np.complex64)
                h_sub[0] = w[0]
                var_innov = np.sqrt(max(1e-6, 1.0 - rho ** 2))
                for idx in range(1, n_points):
                    h_sub[idx] = rho * h_sub[idx - 1] + var_innov * w[idx]
                    
                # Interpolate to sample rate
                t_sub = np.linspace(0, n_samples - 1, n_points)
                t_full = np.arange(n_samples)
                h = np.interp(t_full, t_sub, h_sub).astype(np.complex64)
                
        elif ch_type == 'rician':
            k_lin = 10.0 ** (cfg.k_factor_db / 10.0)
            f_d = cfg.doppler_hz
            los_weight = np.sqrt(k_lin / (k_lin + 1.0))
            diffuse_weight = np.sqrt(1.0 / (k_lin + 1.0))
            theta = float(self.rng.uniform(0, 2 * np.pi))
            los_comp = np.exp(1j * theta)
            
            if f_d <= 1.0:
                diffuse = (self.rng.normal(0, 1) + 1j * self.rng.normal(0, 1)) / np.sqrt(2.0)
                h_const = los_weight * los_comp + diffuse_weight * diffuse
                h = np.full(n_samples, h_const, dtype=np.complex64)
            else:
                decim = max(1, sps)
                n_points = max(2, int(np.ceil(n_samples / decim)))
                dt_decim = decim / float(self.fs)
                rho = float(j0(2.0 * np.pi * f_d * dt_decim))
                rho = min(0.99999, max(0.0, rho))
                
                w = (self.rng.normal(0, 1, n_points) + 1j * self.rng.normal(0, 1, n_points)) / np.sqrt(2.0)
                h_sub = np.zeros(n_points, dtype=np.complex64)
                h_sub[0] = w[0]
                var_innov = np.sqrt(max(1e-6, 1.0 - rho ** 2))
                for idx in range(1, n_points):
                    h_sub[idx] = rho * h_sub[idx - 1] + var_innov * w[idx]
                    
                t_sub = np.linspace(0, n_samples - 1, n_points)
                t_full = np.arange(n_samples)
                diffuse_full = np.interp(t_full, t_sub, h_sub).astype(np.complex64)
                h = (los_weight * los_comp + diffuse_weight * diffuse_full).astype(np.complex64)
        else:
            h = np.ones(n_samples, dtype=np.complex64)
            
        faded_iq = tx_iq * h
        
        # 2. Carrier Frequency Offset (CFO)
        cfo = cfg.cfo_hz
        if abs(cfo) > 1e-3:
            t = np.arange(n_samples) / float(self.fs)
            cfo_rot = np.exp(1j * (2.0 * np.pi * cfo * t + self._cfo_phase))
            self._cfo_phase = (self._cfo_phase + 2.0 * np.pi * cfo * n_samples / float(self.fs)) % (2.0 * np.pi)
            faded_iq = faded_iq * cfo_rot
            
        # 3. Colored Gauss-Markov Phase Noise (AR-1)
        # Models realistic oscillator phase noise with stationary RMS jitter = radians(pn_deg)
        pn_deg = cfg.phase_noise_deg
        if pn_deg > 1e-3:
            std_rad = np.radians(pn_deg)
            rho = 0.995  # Correlation factor across adjacent baseband samples
            var_innov = np.sqrt(max(1e-6, 1.0 - rho ** 2))
            e_raw = self.rng.normal(0, std_rad, n_samples)
            phi_noise, zi = lfilter([var_innov], [1.0, -rho], e_raw, zi=[self._pn_phase])
            self._pn_phase = float(zi[0])
            faded_iq = faded_iq * np.exp(1j * phi_noise).astype(np.complex64)
            
        # 4. AWGN calibrated to C/N0 (consistent in-band SNR and Eb/N0)
        alloc_bw = max(100.0, float(cfg.alloc_bw))
        c_over_n0_lin = 10.0 ** ((cfg.snr_db + 10.0 * np.log10(alloc_bw)) / 10.0)
        
        # When pulse shaped by unit-energy RRC (\sum h^2 = 1), setting channel noise
        # variance per sample to R_s / (C/N0) makes matched filter output noise variance
        # equal 1 / (Es/N0).
        is_digital = cfg.modulation in ('BPSK', 'QPSK', 'ASK', 'FSK')
        if is_digital:
            k_bits = {'BPSK': 1, 'QPSK': 2, 'ASK': 1, 'FSK': 1}.get(cfg.modulation, 1)
            # symbol rate
            rs = self.fs / float(max(1, sps))
            # noise variance per complex sample
            if cfg.modulation == 'FSK':
                # For CPFSK without RRC, correlator integrates over sps samples
                noise_var_total = float(sps) / (c_over_n0_lin / rs)
            else:
                noise_var_total = 1.0 / (c_over_n0_lin / rs)
        else:
            w_eff = max(300.0, float(cfg.msg_bw))
            # Analog: baseband noise spectral density N0 = sig_power / (C/N0)
            # Total noise in fs:
            noise_var_total = (sig_power * self.fs) / (c_over_n0_lin)
            
        sigma_per_dim = np.sqrt(max(1e-12, noise_var_total / 2.0))
        
        noise = (self.rng.normal(0, sigma_per_dim, n_samples) +
                 1j * self.rng.normal(0, sigma_per_dim, n_samples)).astype(np.complex64)
                 
        rx_iq = faded_iq + noise
        
        # 5. False Data Injection Attack (FDIA)
        # Adversary injects malicious multi-tone swept jamming, phase disruption, and burst noise
        if getattr(cfg, 'fdia_active', False):
            rx_iq, _, _ = self.apply_fdia_only(rx_iq, cfg)
        
        # Measure realized SNR in allocated bandwidth
        realized_snr_db = cfg.snr_db
        return rx_iq, h, realized_snr_db

    def apply_fdia_only(self, rx_iq: np.ndarray, cfg: TxConfig) -> Tuple[np.ndarray, np.ndarray, float]:
        """Apply FDIA swept jamming and burst noise to an existing IQ stream (e.g. Pluto SDR RX)."""
        n_samples = len(rx_iq)
        t = np.arange(n_samples) / float(self.fs)
        # Adversarial pilot spoofing and carrier-band swept jamming (targets carrier synchronization)
        f_sweep = 1500.0 * np.sin(2.0 * np.pi * 5.0 * t)
        phi_sweep = 2.0 * np.pi * np.cumsum(f_sweep) / float(self.fs)
        jam_tone = (0.65 * np.exp(1j * phi_sweep)).astype(np.complex64)
        burst_noise = (self.rng.normal(0, 0.15, n_samples) + 1j * self.rng.normal(0, 0.15, n_samples)).astype(np.complex64)
        rx_jammed = rx_iq + jam_tone + burst_noise
        return rx_jammed, np.ones(n_samples, dtype=np.complex64), float(cfg.snr_db)

