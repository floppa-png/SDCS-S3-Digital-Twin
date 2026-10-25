import math
import numpy as np
from typing import Dict, Any, Tuple
from .config import TxConfig, LinkPlan

COMPLEXITY_SCORES: Dict[str, float] = {
    'ASK': 0.95,
    'AM_DSBTC': 0.95,
    'BPSK': 0.80,
    'FM': 0.82,
    'FSK': 0.72,
    'QPSK': 0.70,
    'AM_DSBSC': 0.80
}

PROFILE_WEIGHTS: Dict[str, Dict[str, float]] = {
    'balanced': {
        'rel': 0.35, 'rate': 0.25, 'bw': 0.10, 'pwr': 0.15, 'cplx': 0.10, 'papr': 0.05
    },
    'reliability': {
        'rel': 0.55, 'rate': 0.10, 'bw': 0.05, 'pwr': 0.20, 'cplx': 0.05, 'papr': 0.05
    },
    'throughput': {
        'rel': 0.25, 'rate': 0.45, 'bw': 0.15, 'pwr': 0.10, 'cplx': 0.03, 'papr': 0.02
    },
    'low_power': {
        'rel': 0.25, 'rate': 0.15, 'bw': 0.05, 'pwr': 0.15, 'cplx': 0.30, 'papr': 0.10
    }
}

class Scorer:
    """Calculates multi-dimensional communication performance scores and grades."""
    
    @staticmethod
    def compute_sub_scores(plan: LinkPlan, cfg: TxConfig, metrics: Dict[str, Any]) -> Dict[str, float]:
        """Compute the 6 normalized sub-scores in range [0, 1]."""
        mod = plan.modulation
        is_digital = metrics.get('is_digital', plan.is_digital)
        
        # 1. Reliability (S_rel)
        if is_digital:
            ber = metrics.get('ber', 0.0)
            target_ber = max(1e-9, float(cfg.target_ber))
            # With forward error correction (FEC), raw channel BER < 0.01 decodes cleanly
            if ber <= target_ber:
                s_rel = 1.0
            elif ber <= 0.005:
                s_rel = float(np.clip(1.0 - (ber - target_ber) * 15.0, 0.88, 1.0))
            elif ber <= 0.025:
                s_rel = float(np.clip(0.88 - (ber - 0.005) * 10.0, 0.65, 0.88))
            else:
                log_ber = -math.log10(max(1e-9, float(ber)))
                log_target = -math.log10(target_ber)
                s_rel = float(np.clip(log_ber / log_target, 0.35, 1.0))
        else:
            snr_out = metrics.get('output_snr_db', 0.0)
            target_snr = max(1.0, float(getattr(cfg, 'target_snr_out', 20.0)))
            ratio = snr_out / target_snr
            # Generous mapping: ratio >= 0.85 or within 3 dB of target -> s_rel = 1.0
            if ratio >= 0.85 or (target_snr - snr_out) <= 3.0:
                s_rel = 1.0
            elif ratio >= 0.70:
                s_rel = float(np.clip(0.85 + 1.0 * (ratio - 0.70), 0.85, 1.0))
            else:
                s_rel = float(np.clip(0.40 + (ratio / 0.70) * 0.45, 0.35, 0.85))
            
        # Cyber-Physical Trust weighting (under FDIA attack, trust discounts reliability)
        trust = metrics.get('trust_score')
        if trust is not None and trust < 90:
            trust_norm = float(np.clip(trust / 100.0, 0.0, 1.0))
            if mod == 'FSK':
                s_rel = float(s_rel * (0.85 + 0.15 * trust_norm))
            else:
                s_rel = float(s_rel * (0.65 + 0.35 * trust_norm))

        # 2. Rate Achievement (S_rate)
        if not is_digital:
            fid = float(getattr(plan, 'fidelity_factor', 1.0))
            if fid >= 0.85:
                s_rate = float(np.clip(0.95 + 0.333 * (fid - 0.85), 0.95, 1.0))
            else:
                s_rate = float(np.clip(0.45 + 0.50 * (fid / 0.85), 0.35, 0.95))
        else:
            goodput = metrics.get('goodput_bps', 0.0)
            req_rate = max(1.0, float(cfg.data_rate))
            ratio = goodput / req_rate
            if ratio >= 0.90:
                s_rate = 1.0
            else:
                s_rate = float(np.clip(0.35 + 0.65 * ratio, 0.25, 1.0))
            
        # 3. Spectral Fit (S_bw)
        alloc_bw = max(1.0, float(cfg.alloc_bw))
        obw = metrics.get('obw_99', plan.occupied_bw)
        if obw <= alloc_bw:
            # Reward spectral efficiency when bandwidth is conserved
            s_bw = float(np.clip(1.0 - 0.15 * (obw / alloc_bw), 0.75, 1.0))
        else:
            s_bw = float(np.clip(math.exp(-2.0 * (obw / alloc_bw - 1.0)), 0.35, 1.0))
        
        # 4. Power / Margin (S_pwr)
        link_margin = metrics.get('link_margin_db', 0.0)
        # Sigmoid centered at 0 dB margin, scale 3 dB for more responsive reward
        s_pwr = float(1.0 / (1.0 + math.exp(-np.clip(link_margin / 3.0, -8.0, 8.0))))
        s_pwr = float(np.clip(s_pwr, 0.25, 1.0))
        
        # 5. Receiver Complexity (S_cplx)
        s_cplx = COMPLEXITY_SCORES.get(mod, 0.50)
        
        # 6. Peak-to-Average Power Ratio (S_papr)
        papr_db = metrics.get('papr_db', 0.0)
        s_papr = float(np.clip(1.0 - (papr_db - 0.0) / 10.0, 0.0, 1.0))
        
        return {
            'rel': s_rel,
            'rate': s_rate,
            'bw': s_bw,
            'pwr': s_pwr,
            'cplx': s_cplx,
            'papr': s_papr
        }

    @classmethod
    def calculate_total_score(cls, sub_scores: Dict[str, float], profile: str = 'balanced') -> Tuple[int, str]:
        """Compute weighted total score (0-100) and letter grade."""
        weights = PROFILE_WEIGHTS.get(profile, PROFILE_WEIGHTS['balanced'])
        
        weighted_sum = sum(weights[k] * sub_scores[k] for k in weights)
        total = int(round(100.0 * np.clip(weighted_sum, 0.0, 1.0)))
        
        if total >= 90:
            grade = 'A+'
        elif total >= 80:
            grade = 'A'
        elif total >= 65:
            grade = 'B'
        elif total >= 50:
            grade = 'C'
        elif total >= 35:
            grade = 'D'
        else:
            grade = 'F'
            
        return total, grade

    @classmethod
    def evaluate(cls, plan: LinkPlan, cfg: TxConfig, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate full scoring payload."""
        subs = cls.compute_sub_scores(plan, cfg, metrics)
        profile = getattr(cfg, 'profile', 'balanced')
        weights = PROFILE_WEIGHTS.get(profile, PROFILE_WEIGHTS['balanced'])
        weighted_sum = sum(weights[k] * subs[k] for k in weights)
        score_float = float(100.0 * np.clip(weighted_sum, 0.0, 1.0))
        total, grade = cls.calculate_total_score(subs, profile)
        
        return {
            'total': total,
            'score_float': score_float,
            'grade': grade,
            'profile': profile,
            'subs': subs
        }
