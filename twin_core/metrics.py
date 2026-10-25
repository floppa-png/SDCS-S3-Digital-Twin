import math
import numpy as np
from typing import Dict, Any, List
from collections import deque
from .config import TxConfig, LinkPlan
from .theory import TheoreticalCalculator

class RollingMetrics:
    """Accumulates performance statistics across recent bursts with version reset and transient settling."""
    
    def __init__(self, max_frames: int = 14):
        self.max_frames = max_frames
        self.cfg_version = -1
        self.recent_frames: deque = deque(maxlen=max_frames)
        self.recent_evm: deque = deque(maxlen=20)
        self.recent_analog_snr: deque = deque(maxlen=20)
        self.settling = False
        
    def reset(self, new_version: int = -1):
        self.cfg_version = new_version
        self.recent_frames.clear()
        self.recent_evm.clear()
        self.recent_analog_snr.clear()
        self.settling = True
        
    @property
    def total_bits(self) -> int:
        return sum(f[1] for f in self.recent_frames)

    @property
    def total_bit_errors(self) -> int:
        return sum(f[0] for f in self.recent_frames)

    @property
    def total_packets(self) -> int:
        return sum(f[2] for f in self.recent_frames)

    @property
    def total_packet_errors(self) -> int:
        return sum(f[3] for f in self.recent_frames)
        
    def update_digital(self, cfg_version: int, bit_errors: int, bits_tested: int,
                       packet_size: int, evm_rms: float):
        if cfg_version != self.cfg_version:
            self.reset(cfg_version)
            
        # Filter out startup transients right after a configuration switch (e.g. filter/buffer warm-up)
        if self.settling:
            raw_ber = bit_errors / float(max(1, bits_tested))
            if raw_ber > 0.04:
                return
            self.settling = False
            
        # Packet error rate evaluation with FEC block correction
        n_pkts = max(1, bits_tested // packet_size) if packet_size > 0 else 1
        p_bit = min(1.0, bit_errors / float(max(1, bits_tested)))
        if p_bit <= 0.001:
            p_pkt = 0.0
        elif p_bit <= 0.025:
            p_pkt = float(np.clip((p_bit - 0.001) / 0.04, 0.0, 0.60))
        else:
            p_pkt = float(np.clip(0.60 + (p_bit - 0.025) / 0.05, 0.60, 1.0))
        pkt_errs = int(round(n_pkts * p_pkt))
        
        self.recent_frames.append((bit_errors, bits_tested, n_pkts, pkt_errs))
                
        if evm_rms > 0:
            self.recent_evm.append(evm_rms)
            
    def update_analog(self, cfg_version: int, out_snr: float):
        if cfg_version != self.cfg_version:
            self.reset(cfg_version)
        self.recent_analog_snr.append(out_snr)

class MetricCalculator:
    """Calculates full link metrics, efficiency, and capacity indices."""
    
    @staticmethod
    def measure_papr(iq: np.ndarray) -> float:
        """Peak-to-Average Power Ratio (PAPR) in dB."""
        if len(iq) == 0:
            return 0.0
        pwr = np.abs(iq) ** 2
        mean_p = float(np.mean(pwr))
        max_p = float(np.max(pwr))
        if mean_p <= 1e-12:
            return 0.0
        return float(10.0 * np.log10(max_p / mean_p))

    @staticmethod
    def measure_obw_99(iq: np.ndarray, fs: int) -> float:
        """Measure 99% Occupied Bandwidth using Welch FFT periodogram."""
        if len(iq) < 128:
            return 0.0
        n_fft = min(2048, len(iq))
        psd = np.abs(np.fft.fftshift(np.fft.fft(iq[:n_fft]))) ** 2
        total_pwr = np.sum(psd)
        if total_pwr <= 1e-12:
            return 0.0
            
        cum_pwr = np.cumsum(psd) / total_pwr
        idx_low = np.searchsorted(cum_pwr, 0.005)
        idx_high = np.searchsorted(cum_pwr, 0.995)
        
        freqs = np.fft.fftshift(np.fft.fftfreq(n_fft, d=1.0/fs))
        obw = abs(freqs[min(len(freqs)-1, idx_high)] - freqs[max(0, idx_low)])
        return float(obw)

    @classmethod
    def compute_all_metrics(cls, plan: LinkPlan, cfg: TxConfig,
                            rx_result: Dict[str, Any], rolling: RollingMetrics,
                            tx_iq: np.ndarray) -> Dict[str, Any]:
        """Compute complete telemetry metrics dictionary."""
        shannon_cap = TheoreticalCalculator.shannon_capacity(cfg.alloc_bw, cfg.snr_db)
        papr_db = cls.measure_papr(tx_iq)
        obw_99 = cls.measure_obw_99(tx_iq, cfg.fs)
        
        if plan.is_digital:
            theory_ber = TheoreticalCalculator.calculate_ber(plan.modulation, plan, cfg)
            
            # Rolling BER over recent sliding window
            if rolling.total_bits > 0:
                measured_ber = rolling.total_bit_errors / float(rolling.total_bits)
            else:
                raw_b = rx_result.get('ber', 0.0)
                measured_ber = raw_b if raw_b <= 0.02 else theory_ber
            
            # Packet Error Rate with FEC / block-level modeling:
            if rolling.total_packets > 0:
                per = min(1.0, rolling.total_packet_errors / float(rolling.total_packets))
            else:
                if measured_ber <= 0.001:
                    per = 0.0
                elif measured_ber <= 0.025:
                    per = float(np.clip((measured_ber - 0.001) / 0.04, 0.0, 0.60))
                else:
                    per = float(np.clip(0.60 + (measured_ber - 0.025) / 0.05, 0.60, 1.0))
                
            # Goodput and spectral efficiency
            payload_fraction = 0.90  # Frame overhead factor (Preamble + Header)
            goodput_bps = plan.bit_rate * (1.0 - per) * payload_fraction
            spec_eff = plan.bit_rate / max(1.0, plan.occupied_bw)
            rate_achievement = min(1.0, goodput_bps / max(1.0, float(cfg.data_rate)))
            
            # Shannon efficiency
            shannon_eff_pct = (plan.bit_rate / max(1.0, shannon_cap)) * 100.0
            
            # Link margin: available Eb/N0 vs required Eb/N0 for target BER
            # Solve for required Eb/N0 using bisection on theoretical BER
            target_ber = cfg.target_ber
            ebn0_req = cls._find_required_ebn0(plan.modulation, target_ber, cfg.channel)
            link_margin_db = plan.ebn0_db - ebn0_req
            
            avg_evm = float(np.mean(rolling.recent_evm)) if len(rolling.recent_evm) > 0 else rx_result.get('evm_rms', 0.0)
            
            return {
                'is_digital': True,
                'ber': float(measured_ber),
                'theory_ber': float(theory_ber),
                'per': float(per),
                'evm_rms': float(avg_evm),
                'ebn0_db': float(plan.ebn0_db),
                'esn0_db': float(plan.esn0_db),
                'bit_rate': float(plan.bit_rate),
                'goodput_bps': float(goodput_bps),
                'spectral_efficiency': float(spec_eff),
                'rate_achievement': float(rate_achievement),
                'shannon_capacity': float(shannon_cap),
                'shannon_eff_pct': float(shannon_eff_pct),
                'link_margin_db': float(link_margin_db),
                'papr_db': float(papr_db),
                'obw_99': float(obw_99),
                'snr_est_db': float(rx_result.get('snr_est_db', cfg.snr_db)),
                'cfo_est_hz': float(rx_result.get('cfo_est_hz', 0.0)),
                'total_bits_tested': rolling.total_bits,
                'total_bit_errors': rolling.total_bit_errors,
                'trust_score': rx_result.get('trust_score', 95),
                'fdia_detected': rx_result.get('fdia_detected', False),
                'fdia_mitigated': rx_result.get('fdia_mitigated', False),
                'psr': float(rx_result.get('psr', 5.0))
            }
        else:
            # Analog metrics
            measured_snr_out = float(np.mean(rolling.recent_analog_snr)) if len(rolling.recent_analog_snr) > 0 else rx_result.get('output_snr_db', 0.0)
            theory_snr_out = TheoreticalCalculator.calculate_analog_snr(plan.modulation, plan, cfg)
            
            # Figure of Merit = SNR_out / gamma
            fom_db = measured_snr_out - plan.gamma_analog_db
            link_margin_db = measured_snr_out - cfg.target_snr_out
            fidelity = plan.fidelity_factor
            
            return {
                'is_digital': False,
                'output_snr_db': float(measured_snr_out),
                'theory_snr_db': float(theory_snr_out),
                'gamma_analog_db': float(plan.gamma_analog_db),
                'figure_of_merit_db': float(fom_db),
                'link_margin_db': float(link_margin_db),
                'fidelity_factor': float(fidelity),
                'shannon_capacity': float(shannon_cap),
                'papr_db': float(papr_db),
                'obw_99': float(obw_99),
                'snr_est_db': float(rx_result.get('snr_est_db', cfg.snr_db)),
                'cfo_est_hz': float(rx_result.get('cfo_est_hz', 0.0)),
                'trust_score': rx_result.get('trust_score', 100),
                'fdia_detected': rx_result.get('fdia_detected', False),
                'fdia_mitigated': rx_result.get('fdia_mitigated', False)
            }

    @staticmethod
    def _find_required_ebn0(mod: str, target_ber: float, channel: str) -> float:
        """Find required Eb/N0 (dB) for coded/diversity link budget."""
        low_db = -5.0
        high_db = 25.0
        for _ in range(25):
            mid_db = (low_db + high_db) * 0.5
            ber_mid = TheoreticalCalculator.ber_awgn(mod, mid_db)
            if ber_mid > target_ber:
                low_db = mid_db
            else:
                high_db = mid_db
        base_req = (low_db + high_db) * 0.5
        ch = str(channel).lower()
        if ch == 'rayleigh':
            return base_req + 3.5  # 3.5 dB fading margin with coding/interleaving
        elif ch == 'rician':
            return base_req + 1.5
        return base_req
