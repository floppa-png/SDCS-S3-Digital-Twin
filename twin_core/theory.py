import math
import numpy as np
from scipy.special import erfc
from typing import Dict, Any, Optional
from .config import TxConfig, LinkPlan

def q_func(x: float) -> float:
    """Gaussian Q-function Q(x) = 0.5 * erfc(x / sqrt(2))."""
    if x <= 0:
        return 0.5 * erfc(0.0)
    return 0.5 * float(erfc(x / np.sqrt(2.0)))

class TheoreticalCalculator:
    """Theoretical performance calculations (BER, SNR, Shannon) for communication channels."""
    
    _fading_samples: Optional[np.ndarray] = None
    
    @classmethod
    def get_rayleigh_samples(cls, n: int = 20000) -> np.ndarray:
        if cls._fading_samples is None or len(cls._fading_samples) != n:
            # Exponential with mean 1 for |h|^2
            cls._fading_samples = np.random.exponential(1.0, size=n)
        return cls._fading_samples

    @staticmethod
    def ber_awgn(mod: str, ebn0_db: float) -> float:
        """Compute theoretical Bit Error Rate in AWGN."""
        gamma_b = 10.0 ** (ebn0_db / 10.0)
        
        if mod in ('BPSK', 'QPSK'):
            # Q(sqrt(2 * gamma_b))
            return q_func(np.sqrt(2.0 * gamma_b))
            
        elif mod == 'ASK':
            # Non-coherent OOK: 0.5 * exp(-gamma_b / 2)
            return 0.5 * math.exp(-0.5 * gamma_b)
            
        elif mod == 'FSK':
            # Non-coherent BFSK: 0.5 * exp(-gamma_b / 2)
            return 0.5 * math.exp(-0.5 * gamma_b)
            
        return 0.5

    @staticmethod
    def ber_rayleigh(mod: str, ebn0_db: float) -> float:
        """Compute theoretical BER in flat Rayleigh fading."""
        gamma_b = 10.0 ** (ebn0_db / 10.0)
        
        if mod in ('BPSK', 'QPSK'):
            # Analytical: 0.5 * (1 - sqrt(gamma / (1 + gamma)))
            return 0.5 * (1.0 - math.sqrt(gamma_b / (1.0 + gamma_b)))
            
        elif mod == 'FSK':
            # Analytical non-coherent BFSK: 1 / (2 + gamma_b)
            return 1.0 / (2.0 + gamma_b)
            
        elif mod == 'ASK':
            # Analytical non-coherent OOK in Rayleigh fading: requires 3 dB more Eb/N0 than orthogonal BFSK
            return 1.0 / (2.0 + (gamma_b / 2.0))
            
        return 0.5

    @staticmethod
    def ber_rician(mod: str, ebn0_db: float, k_factor_db: float) -> float:
        """Compute theoretical BER in Rician fading via numerical integration."""
        gamma_b = 10.0 ** (ebn0_db / 10.0)
        k_lin = 10.0 ** (k_factor_db / 10.0)
        
        # Draw Rician envelope squared |h|^2
        n = 10000
        los = np.sqrt(k_lin / (k_lin + 1.0))
        diffuse_i = np.random.normal(0, np.sqrt(0.5 / (k_lin + 1.0)), n)
        diffuse_q = np.random.normal(0, np.sqrt(0.5 / (k_lin + 1.0)), n)
        h_mag_sq = (los + diffuse_i) ** 2 + diffuse_q ** 2
        
        g_inst = gamma_b * h_mag_sq
        if mod in ('BPSK', 'QPSK'):
            bers = 0.5 * erfc(np.sqrt(2.0 * g_inst) / np.sqrt(2.0))
        elif mod in ('ASK', 'FSK'):
            bers = 0.5 * np.exp(-0.5 * g_inst)
        else:
            bers = np.full(n, 0.5)
            
        return float(np.mean(bers))

    @classmethod
    def calculate_ber(cls, mod: str, plan: LinkPlan, cfg: TxConfig) -> float:
        """Dispatch theoretical BER for current channel model."""
        if not plan.is_digital:
            return 0.0
            
        ch = cfg.channel.lower()
        if ch == 'awgn':
            return cls.ber_awgn(mod, plan.ebn0_db)
        elif ch == 'rayleigh':
            return cls.ber_rayleigh(mod, plan.ebn0_db)
        elif ch == 'rician':
            return cls.ber_rician(mod, plan.ebn0_db, cfg.k_factor_db)
        return cls.ber_awgn(mod, plan.ebn0_db)

    @staticmethod
    def calculate_analog_snr(mod: str, plan: LinkPlan, cfg: TxConfig) -> float:
        """Compute theoretical output SNR (dB) for analog modulations."""
        if not getattr(plan, 'applicable', True) or plan.occupied_bw <= 0.0 or plan.msg_bw_effective <= 0.0:
            return 0.0
        gamma_lin = 10.0 ** (plan.gamma_analog_db / 10.0)
        p_m = 0.186  # Multitone message power normalized to peak 1.0
        
        if mod == 'AM_DSBSC':
            # Coherent DSB-SC: SNR_out = gamma
            return float(plan.gamma_analog_db)
            
        elif mod == 'AM_DSBTC':
            # Envelope detected DSB-TC: mu^2 * Pm / (1 + mu^2 * Pm) * gamma
            mu = cfg.am_index
            eta = (mu ** 2 * p_m) / (1.0 + mu ** 2 * p_m)
            snr_linear = eta * gamma_lin
            # Threshold penalty below 10 dB CNR in 2*W
            cnr = gamma_lin * (plan.msg_bw_effective / max(1.0, plan.occupied_bw))
            if cnr < 10.0:
                snr_linear *= max(0.01, cnr / 10.0)
            return 10.0 * math.log10(max(1e-3, snr_linear))
            
        elif mod == 'FM':
            # Wideband FM with practical discriminator & IF filtering
            w_eff = max(1.0, plan.msg_bw_effective)
            beta_eff = max(0.3, (plan.occupied_bw / (2.0 * w_eff)) - 1.0)
            cnr_in = 10.0 ** (cfg.snr_db / 10.0)
            snr_linear = 3.0 * (beta_eff ** 2) * p_m * cnr_in
            if cnr_in < 10.0:
                threshold_drop = math.exp(-0.5 * (10.0 - cnr_in))
                snr_linear *= max(0.001, threshold_drop)
            return min(50.0, 10.0 * math.log10(max(1e-3, snr_linear)))
            
        return 0.0

    @staticmethod
    def calculate_pcm_snr(pcm_bits: int, ber: float) -> float:
        """Compute analog output SNR when digitized via PCM with channel bit error rate."""
        n = pcm_bits
        q_snr_lin = 10.0 ** ((6.02 * n + 1.76) / 10.0)
        denom = 1.0 + 4.0 * (2 ** (2 * n) - 1) * max(0.0, ber)
        total_snr_lin = q_snr_lin / denom
        return 10.0 * math.log10(max(1e-3, total_snr_lin))

    @staticmethod
    def shannon_capacity(alloc_bw: float, snr_db: float) -> float:
        """Shannon-Hartley channel capacity in bits per second."""
        snr_lin = 10.0 ** (snr_db / 10.0)
        return float(alloc_bw * math.log2(1.0 + snr_lin))
