import math
import time
import numpy as np
from typing import Dict, Any, List, Optional
from .config import TxConfig, LinkPlan, derive_link_plan, MODULATIONS, DIGITAL_MODS, ANALOG_MODS
from .waveforms import Modulator
from .channel import ChannelModel
from .receiver import Receiver
from .theory import TheoreticalCalculator
from .metrics import MetricCalculator, RollingMetrics
from .scoring import Scorer

class DigitalTwin:
    """
    Evaluates, ranks, and predicts optimal modulation across physical link trade-offs.
    Combines analytical theory and fast Monte-Carlo channel simulation.
    """
    
    def __init__(self, fs: int = 1000000):
        self.fs = fs
        self.modulator = Modulator(fs=fs)
        self.receiver = Receiver(fs=fs)
        self._cache: Dict[str, Dict[str, Any]] = {}
        
    def _config_hash(self, cfg: TxConfig, ch_state: Optional[Dict[str, Any]] = None) -> str:
        ch_str = str(sorted(ch_state.items())) if ch_state else ""
        return (f"{cfg.source_type}:{cfg.data_rate}:{cfg.msg_bw}:{cfg.pcm_bits}:"
                f"{cfg.alloc_bw}:{cfg.rolloff}:{cfg.snr_db}:{cfg.channel}:"
                f"{cfg.k_factor_db}:{cfg.doppler_hz}:{cfg.cfo_hz}:{cfg.phase_noise_deg}:"
                f"{cfg.am_index}:{cfg.fm_beta}:{cfg.fsk_h}:{cfg.profile}:{cfg.target_ber}:"
                f"{cfg.target_snr_out}:{getattr(cfg, 'fdia_active', False)}:{ch_str}")

    def evaluate(self, cfg: TxConfig, channel_state: Optional[Dict[str, Any]] = None,
                 scenario_preset: Optional[str] = None) -> Dict[str, Any]:
        """
        Evaluate and rank all 8 modulations for the given configuration.
        Returns ranking, best recommendation, confidence %, and BER curves.
        """
        eval_cfg = TxConfig(**cfg.to_dict())
        if scenario_preset:
            from .presets import PRESETS
            if scenario_preset in PRESETS:
                eval_cfg.source_type = PRESETS[scenario_preset].get('source_type', eval_cfg.source_type)

        cfg_key = self._config_hash(eval_cfg, channel_state)
        if cfg_key in self._cache:
            return self._cache[cfg_key]
            
        t_start = time.perf_counter()
        results: List[Dict[str, Any]] = []
        if channel_state:
            if 'snr_db' in channel_state:
                eval_cfg.snr_db = channel_state['snr_db']
            if 'cfo_hz' in channel_state:
                eval_cfg.cfo_hz = channel_state['cfo_hz']
            if 'fading_var' in channel_state and channel_state['fading_var'] > 0.1:
                eval_cfg.channel = 'rayleigh'
                
        has_impairments = (abs(eval_cfg.cfo_hz) > 50.0 or
                           eval_cfg.doppler_hz > 5.0 or
                           eval_cfg.phase_noise_deg > 1.0 or
                           eval_cfg.channel.lower() != 'awgn')
                           
        for mod in MODULATIONS:
            mod_cfg = TxConfig(**eval_cfg.to_dict())
            mod_cfg.modulation = mod
            if not getattr(mod_cfg, 'msg_bw', None) or mod_cfg.msg_bw <= 0:
                mod_cfg.msg_bw = min(15000.0, max(3000.0, float(eval_cfg.alloc_bw) / 4.0))
            if not getattr(mod_cfg, 'data_rate', None) or mod_cfg.data_rate <= 0:
                mod_cfg.data_rate = 20000.0
                    
            plan = derive_link_plan(mod_cfg, mod)
                
            res = self._evaluate_analytic(mod, plan, mod_cfg, eval_cfg)
            results.append(res)
            
        # Rank applicable modulations by score descending (tie-breaking with score_float)
        applicable = [r for r in results if r['applicable']]
        applicable.sort(key=lambda x: (x.get('score_float', float(x['score'])), x['score']), reverse=True)
        
        inapplicable = [r for r in results if not r['applicable']]
        ranking = applicable + inapplicable
        
        best = applicable[0]['mod'] if applicable else eval_cfg.modulation
        
        # Confidence margin
        if len(applicable) >= 2:
            score_diff = applicable[0]['score'] - applicable[1]['score']
            confidence = int(np.clip(round(score_diff * 2.5 + 40), 10, 99))
        else:
            confidence = 95
            
        # BER vs Eb/N0 curves for digital mods
        curves = self._generate_ber_curves(eval_cfg)
        
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0

        # Physical Rationale synthesis for recommendation
        rationale = self._synthesize_rationale(eval_cfg, best, ranking, scenario_preset)
        for r in ranking:
            r['rationale'] = self._candidate_rationale(r['mod'], eval_cfg, is_best=(r['mod'] == best))

        payload = {
            'cfg_version': getattr(cfg, 'cfg_version', 1),
            'ranking': ranking,
            'best': best,
            'confidence': confidence,
            'rationale': rationale,
            'eval_time_ms': round(elapsed_ms, 1),
            'curves': curves
        }
        
        # Cache result
        if len(self._cache) > 200:
            self._cache.clear()
        self._cache[cfg_key] = payload
        
        return payload

    def _synthesize_rationale(self, cfg: TxConfig, best: str, ranking: List[Dict[str, Any]], scenario_preset: Optional[str]) -> str:
        """Derive an explainable physical rationale for the top-ranked recommendation."""
        is_fdia = getattr(cfg, 'fdia_active', False)
        if is_fdia:
            if best == 'FSK':
                return "Cyber Jamming / FDIA Detected: Dual-tone non-coherent FSK envelope detection bypasses Costas PLL pull-off and ignores pilot phase spoofing."
            elif best == 'FM':
                return "In-band Jamming Active: Wideband FM limiter discards swept-carrier amplitude distortion and recovers audio subcarrier."
            else:
                return "In-band Attack Active: Autonomous defense selecting orthogonal signal trajectory to preserve link availability."

        # Scenario-specific physical rationales
        if scenario_preset == 'deep_space':
            if best == 'BPSK':
                return "Deep Space AWGN Limit: Antipodal 180° phase separation maximizes Euclidean distance (d_min = 2√Eb) under extreme power-starved thermal noise."
            elif best == 'QPSK':
                return "Thermal Noise Margin: Quadrature phase tracking balances 2.0 b/s/Hz spectral efficiency within acceptable bit error bounds."
        elif scenario_preset == 'urban_cellular':
            if best == 'QPSK':
                return "Rayleigh Multipath Channel: Constant-modulus QPSK with RRC Nyquist filtering maintains robust symbol decisions against selective fading nulls."
            elif best == 'BPSK':
                return "Severe Fading Fallback: BPSK maximizes antipodal noise margin against heavy multipath phase dispersion."
        elif scenario_preset == 'tactical_ew':
            if best == 'FSK':
                return "Electronic Warfare: Orthogonal tone spacing evades swept-carrier jamming; non-coherent detector requires zero carrier phase synchronization."
        elif scenario_preset == 'leo_satellite':
            if best in ('BPSK', 'QPSK'):
                return f"LEO Orbital Dynamics: Wide AFC tracking bandwidth accommodates high Doppler shift ({cfg.doppler_hz:.0f} Hz) without carrier cycle slips."
        elif scenario_preset == 'hf_skywave':
            if best in ('8-PSK', 'QPSK', 'BPSK'):
                return "Ionospheric Coherence Limit: Symbol rate matched to multipath spread to mitigate inter-symbol interference (ISI)."
        elif scenario_preset == 'broadcast_audio':
            if best == 'FM':
                return "Hi-Fi Audio Fidelity: Wideband angle modulation achieves 20 Hz–15 kHz flat audio bandwidth with FM capture effect quieting."
        elif scenario_preset == 'tactical_am':
            if best == 'AM':
                return "Tactical AM Interoperability: Standard double-sideband envelope demodulation enables low-complexity legacy avionics recovery."

        # General physics heuristics based on physical channel impairments:
        if cfg.channel.lower() == 'rayleigh':
            return f"Multipath Rayleigh Fading: {best} provides optimal trade-off between symbol constellation Euclidean distance and channel coherence."
        elif cfg.snr_db < 5.0:
            return f"Power-Limited Link ({cfg.snr_db:.1f} dB SNR): {best} antipodal signaling minimizes required Eb/N0 to maintain packet lock."
        elif abs(cfg.cfo_hz) > 1000.0:
            return f"High Doppler / CFO ({cfg.cfo_hz:+.0f} Hz): {best} receiver loop maintains stable synchronization without phase ambiguity."
        else:
            return f"Spectral Efficiency Trade-off: {best} maximizes data rate while respecting {cfg.alloc_bw/1000:.0f} kHz allocated channel bandwidth."

    def _candidate_rationale(self, mod: str, cfg: TxConfig, is_best: bool = False) -> str:
        """Physical suitability rationale for each modulation candidate."""
        is_fdia = getattr(cfg, 'fdia_active', False)
        if is_fdia:
            if mod == 'FSK':
                return "Non-coherent energy detection immune to phase perturbation & swept jamming"
            elif mod == 'FM':
                return "Receiver limiter strips envelope amplitude modulation distortion"
            else:
                return "Vulnerable to swept-carrier jamming and carrier loop phase pull-off"
        
        rationales = {
            'BPSK': "Antipodal 180° geometry yields maximum Euclidean distance (d_min=2√Eb) under AWGN",
            'QPSK': "Quadrature 4-phase constellation balances 2.0 b/s/Hz spectral fit and Rayleigh multipath resilience",
            'ASK': "Non-coherent envelope detection with low hardware power consumption",
            'FSK': "Dual-tone orthogonal signaling with high phase jitter tolerance",
            'AM_DSBSC': "Suppressed carrier transmission maximizing power efficiency for voice links",
            'AM_DSBTC': "Full carrier envelope modulation for legacy low-complexity envelope detectors",
            'FM': "Wideband angle modulation with high audio fidelity and noise capture effect"
        }
        return rationales.get(mod, "Standard communication profile")

    def _evaluate_analytic(self, mod: str, plan: LinkPlan, cfg: TxConfig, scenario_cfg: Optional[TxConfig] = None) -> Dict[str, Any]:
        """Closed-form analytical evaluation incorporating physical link trade-offs and impairment limits."""
        cfo = abs(float(cfg.cfo_hz))
        pn = float(cfg.phase_noise_deg)
        fd = float(cfg.doppler_hz)
        is_fdia = getattr(cfg, 'fdia_active', False)
        
        if plan.is_digital:
            rs = max(1.0, float(plan.symbol_rate))
            if cfg.channel.lower() == 'rayleigh':
                base_ber = TheoreticalCalculator.ber_rayleigh(mod, plan.ebn0_db)
            elif cfg.channel.lower() == 'rician':
                base_ber = TheoreticalCalculator.ber_rician(mod, plan.ebn0_db, cfg.k_factor_db)
            else:
                base_ber = TheoreticalCalculator.ber_awgn(mod, plan.ebn0_db)
                
            ber = base_ber
            if mod in ('BPSK', 'QPSK'):
                alpha_pll = 0.20 if mod == 'BPSK' else 0.12
                # 2-stage AFC coarse acquisition + Costas tracking
                residual_cfo = max(0.0, cfo - 0.04 * rs)
                if residual_cfo > 0.0:
                    cfo_penalty_db = min(12.0, 6.0 * (residual_cfo / (0.12 * rs))**2)
                    eff_ebn0 = max(1.0, plan.ebn0_db - cfo_penalty_db)
                    if cfg.channel.lower() == 'rayleigh':
                        ber = max(ber, TheoreticalCalculator.ber_rayleigh(mod, eff_ebn0))
                    elif cfg.channel.lower() == 'rician':
                        ber = max(ber, TheoreticalCalculator.ber_rician(mod, eff_ebn0, cfg.k_factor_db))
                    else:
                        ber = max(ber, TheoreticalCalculator.ber_awgn(mod, eff_ebn0))
                    
                # Angular decision region error floor from phase noise tracking jitter
                thresh_deg = {'BPSK': 90.0, 'QPSK': 45.0}[mod]
                if pn > 0.1:
                    std_rad = np.radians(pn)
                    sigma_track_rad = np.sqrt((std_rad ** 2) / (2.0 * alpha_pll))
                    th_rad = np.radians(thresh_deg)
                    z = th_rad / (np.sqrt(2.0) * max(1e-6, sigma_track_rad))
                    floor_pn = 0.5 * math.erfc(min(6.0, z))
                    ber = max(ber, min(0.08, floor_pn))
                    
                # Doppler tracking degradation under fast fading
                if fd > 5.0 and cfg.channel.lower() in ('rayleigh', 'rician'):
                    floor_dop = 0.5 * (np.pi * fd / rs) ** 2
                    ber = max(ber, min(0.05, floor_dop))
            elif mod == 'FSK':
                # Non-coherent energy detector: immune to phase noise and Doppler floor
                cfo_loss_db = abs(20.0 * np.log10(max(0.1, np.sinc(cfo / rs))))
                eff_ebn0 = plan.ebn0_db - cfo_loss_db
                if cfg.channel.lower() == 'rayleigh':
                    ber = TheoreticalCalculator.ber_rayleigh(mod, eff_ebn0)
                else:
                    ber = TheoreticalCalculator.ber_awgn(mod, eff_ebn0)
                    
            if is_fdia:
                if mod == 'FSK':
                    # FSK uses dual-tone energy detection orthogonal to carrier swept jamming
                    jamming_loss_db = 1.0
                    eff_ebn0 = max(1.0, plan.ebn0_db - jamming_loss_db)
                    if cfg.channel.lower() == 'rayleigh':
                        ber = max(ber, TheoreticalCalculator.ber_rayleigh(mod, eff_ebn0))
                    elif cfg.channel.lower() == 'rician':
                        ber = max(ber, TheoreticalCalculator.ber_rician(mod, eff_ebn0, cfg.k_factor_db))
                    else:
                        ber = max(ber, TheoreticalCalculator.ber_awgn(mod, eff_ebn0))
                else:
                    # Non-mitigated carrier modulations suffer Costas cycle slips, preamble collapse and CRC loss
                    ber = 0.45
                    
            ber = float(np.clip(ber, 1e-9, 0.5))
            # Coded packet error rate modeling with FEC
            if is_fdia and mod != 'FSK':
                per = 1.0
                goodput = 0.0
                rate_achieve = 0.0
            else:
                if ber <= 0.001:
                    per = 0.0
                elif ber <= 0.025:
                    per = float(np.clip((ber - 0.001) / 0.04, 0.0, 0.60))
                else:
                    per = float(np.clip(0.60 + (ber - 0.025) / 0.05, 0.60, 1.0))
                goodput = plan.bit_rate * (1.0 - per) * 0.90
                rate_achieve = min(1.0, goodput / max(1.0, float(cfg.data_rate)))
                
            spec_eff = plan.bit_rate / max(1.0, plan.occupied_bw)
            ebn0_req = MetricCalculator._find_required_ebn0(mod, cfg.target_ber, cfg.channel)
            link_margin = plan.ebn0_db - ebn0_req
            papr = {'BPSK': 3.5, 'QPSK': 4.0, 'ASK': 3.0, 'FSK': 0.5}.get(mod, 3.5)
            
            metrics = {
                'is_digital': True,
                'ber': ber,
                'theory_ber': ber,
                'per': per,
                'goodput_bps': goodput,
                'spectral_efficiency': spec_eff,
                'rate_achievement': rate_achieve,
                'link_margin_db': link_margin,
                'papr_db': papr,
                'obw_99': plan.occupied_bw,
                'fdia_detected': is_fdia and (mod != 'FSK')
            }
            if is_fdia:
                metrics['trust_score'] = 94 if mod == 'FSK' else 25
        else:
            snr_out = TheoreticalCalculator.calculate_analog_snr(mod, plan, cfg)
            if mod == 'AM_DSBSC' and cfo > 50.0:
                cfo_loss_db = min(4.0, (cfo / 150.0)**1.5)
                snr_out = max(5.0, snr_out - cfo_loss_db)
            if mod == 'AM_DSBSC' and fd > 5.0 and cfg.channel.lower() in ('rayleigh', 'rician'):
                dop_loss_db = min(3.0, 1.5 * (fd / 40.0))
                snr_out = max(5.0, snr_out - dop_loss_db)
            link_margin = snr_out - getattr(cfg, 'target_snr_out', 20.0)
            papr = {'AM_DSBSC': 4.5, 'AM_DSBTC': 4.0, 'FM': 0.1}.get(mod, 3.0)
            
            metrics = {
                'is_digital': False,
                'output_snr_db': float(snr_out),
                'theory_snr_db': float(snr_out),
                'link_margin_db': float(link_margin),
                'fidelity_factor': float(plan.fidelity_factor),
                'papr_db': float(papr),
                'obw_99': float(plan.occupied_bw),
                'fdia_detected': is_fdia
            }
            if is_fdia:
                if mod == 'FM':
                    metrics['trust_score'] = 85
                    metrics['fdia_detected'] = False
                else:
                    snr_out = 5.0
                    metrics['output_snr_db'] = 5.0
                    metrics['theory_snr_db'] = 5.0
                    metrics['trust_score'] = 25
                    metrics['fdia_detected'] = True
            
        scoring = Scorer.evaluate(plan, scenario_cfg or cfg, metrics)
        
        scenario_source = getattr(scenario_cfg or cfg, 'source_type', 'digital')
        is_mod_digital = (mod in DIGITAL_MODS)
        if scenario_source == 'analog':
            applicable = not is_mod_digital
            reason = None if applicable else "Digital modulation - not applicable for analog source"
        else:
            applicable = is_mod_digital
            reason = None if applicable else "Analog modulation - not applicable for digital source"
            
        return {
            'mod': mod,
            'score': scoring['total'] if applicable else 0,
            'score_float': scoring.get('score_float', float(scoring['total'])) if applicable else 0.0,
            'grade': scoring['grade'] if applicable else 'N/A',
            'applicable': applicable,
            'reason': reason,
            'source': 'theory',
            'metrics': metrics,
            'subs': scoring['subs']
        }

    def _evaluate_monte_carlo(self, mod: str, plan: LinkPlan, cfg: TxConfig, scenario_cfg: Optional[TxConfig] = None) -> Dict[str, Any]:
        """Fast Monte-Carlo simulation to capture impairment effects (CFO, phase noise, fading)."""
        channel = ChannelModel(fs=self.fs, seed=42)
        rolling = RollingMetrics()
        
        if plan.is_digital:
            test_cfg = TxConfig(**cfg.to_dict())
            test_cfg.modulation = mod
            test_cfg.source_type = 'digital'
            if not getattr(test_cfg, 'data_rate', None) or test_cfg.data_rate <= 0:
                test_cfg.data_rate = 20000.0
            
            tx_frame = self.modulator.generate_digital_frame(test_cfg)
            rx_iq, _, _ = channel.apply(tx_frame.iq, test_cfg, sps=tx_frame.sps)
            rx_res = self.receiver.demodulate_digital_frame(rx_iq, tx_frame, test_cfg)
            
            rolling.update_digital(1, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
            metrics = MetricCalculator.compute_all_metrics(plan, test_cfg, rx_res, rolling, tx_frame.iq)
        else:
            test_cfg = TxConfig(**cfg.to_dict())
            test_cfg.modulation = mod
            test_cfg.source_type = 'analog'
            if not getattr(test_cfg, 'msg_bw', None) or test_cfg.msg_bw <= 0:
                test_cfg.msg_bw = min(15000.0, max(3000.0, float(cfg.alloc_bw) / 4.0))
            
            tx_iq, msg, _ = self.modulator.generate_analog_signal(test_cfg, duration=0.04)
            rx_iq, _, _ = channel.apply(tx_iq, test_cfg)
            rx_res = self.receiver.demodulate_analog_signal(rx_iq, msg, test_cfg)
            
            if mod == 'AM_DSBSC' and abs(cfg.cfo_hz) > 100.0:
                cfo_loss = min(4.0, abs(cfg.cfo_hz) / 100.0)
                rx_res['output_snr_db'] = max(5.0, rx_res['output_snr_db'] - cfo_loss)
                
            rolling.update_analog(1, rx_res['output_snr_db'])
            metrics = MetricCalculator.compute_all_metrics(plan, test_cfg, rx_res, rolling, tx_iq)
            
        scoring = Scorer.evaluate(plan, scenario_cfg or cfg, metrics)
        
        scenario_source = getattr(scenario_cfg or cfg, 'source_type', 'digital')
        is_mod_digital = (mod in DIGITAL_MODS)
        if scenario_source == 'analog':
            applicable = not is_mod_digital
            reason = None if applicable else "Digital modulation - not applicable for analog source"
        else:
            applicable = is_mod_digital
            reason = None if applicable else "Analog modulation - not applicable for digital source"
            
        return {
            'mod': mod,
            'score': scoring['total'] if applicable else 0,
            'score_float': scoring.get('score_float', float(scoring['total'])) if applicable else 0.0,
            'grade': scoring['grade'] if applicable else 'N/A',
            'applicable': applicable,
            'reason': reason,
            'source': 'sim',
            'metrics': metrics,
            'subs': scoring['subs']
        }

    def _generate_ber_curves(self, cfg: TxConfig) -> Dict[str, Any]:
        """Generate BER vs Eb/N0 curves for digital modulations for frontend charts."""
        ebn0_range = list(range(-2, 17))  # -2 dB to 16 dB
        mods_data: Dict[str, List[float]] = {}
        
        for mod in DIGITAL_MODS:
            pts: List[float] = []
            for ebn0 in ebn0_range:
                if cfg.channel.lower() == 'rayleigh':
                    ber = TheoreticalCalculator.ber_rayleigh(mod, float(ebn0))
                elif cfg.channel.lower() == 'rician':
                    ber = TheoreticalCalculator.ber_rician(mod, float(ebn0), cfg.k_factor_db)
                else:
                    ber = TheoreticalCalculator.ber_awgn(mod, float(ebn0))
                pts.append(max(1e-7, float(ber)))
            mods_data[mod] = pts
            
        return {
            'ebn0_db': ebn0_range,
            'mods': mods_data
        }
