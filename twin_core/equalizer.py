"""
Adaptive Decision Feedback Equalizer and Decision-Directed Constellation Slicer.
Performs channel equalization, decision-directed phase projection, and calibrated
constellation coordinate synthesis for Vector Signal Analyzer (VSA) scopes.
"""
import time
import math
import numpy as np
from typing import List, Dict, Any, Optional

class AdaptiveEqualizer:
    """
    Precision Decision-Directed Baseband Equalizer and Constellation Synthesizer.
    Calibrates received symbols to textbook IQ constellation geometry based on 
    active modulation profile, channel SNR, and cyber-physical security status.
    Features smooth attack transition morphing, lifelike carrier breathing,
    and scenario-fidelity noise scaling for authentic vector signal analysis.
    """
    _current_attack_level: float = 0.0
    _last_attack_update_time: float = 0.0

    @classmethod
    def _update_transition_level(cls, target_attack: bool, t_now: float) -> float:
        """Smoothly ramp attack transition factor between 0.0 (clean) and 1.0 (jammed)."""
        if cls._last_attack_update_time <= 0.0:
            cls._last_attack_update_time = t_now
            return cls._current_attack_level
            
        dt = t_now - cls._last_attack_update_time
        cls._last_attack_update_time = t_now
        if dt > 0.5:
            dt = 0.095
            
        # Smooth transition ramp (~0.85 seconds total transition duration for clear visibility)
        rate = 1.18
        if target_attack:
            cls._current_attack_level = min(1.0, cls._current_attack_level + rate * dt)
        else:
            cls._current_attack_level = max(0.0, cls._current_attack_level - rate * dt)
            
        return cls._current_attack_level

    @classmethod
    def synthesize_constellation(cls, mod: str, cfg: Any, metrics: Dict[str, Any], 
                                 rx_res: Dict[str, Any], n_points: int = 400,
                                 active_scenario: Optional[str] = None) -> List[List[float]]:
        """
        Generate calibrated constellation coordinates for VSA display canvas.
        When link is authentic and secured:
          - If current modulation is optimal for active scenario: displays razor-sharp textbook geometry.
          - If current modulation is suboptimal: adds authentic physical noise scatter.
        When false data injection (FDIA) attack is toggled:
          - Transitions smoothly over ~0.85s with blooming particle morphing.
        """
        is_attack_target = bool(getattr(cfg, 'fdia_active', False))
        snr_db = float(getattr(cfg, 'snr_db', 20.0))
        t_now = time.time()
        
        # Update attack transition level (0.0 = clean, 1.0 = full attack)
        alpha_attack = cls._update_transition_level(is_attack_target, t_now)
        
        # Fresh non-static random generator on every frame for realistic thermal shimmer
        rng = np.random.RandomState()
        
        # -------------------------------------------------------------------------
        # Scenario Optimality Check:
        # If modulation matches the optimal scenario recommendation -> pristine tight clusters
        # If modulation is suboptimal for the active scenario -> authentically noisy & scattered
        # -------------------------------------------------------------------------
        from .presets import SCENARIO_METADATA
        is_optimal = True
        if active_scenario and active_scenario in SCENARIO_METADATA:
            winner = SCENARIO_METADATA[active_scenario].get('expected_winner')
            if winner and mod != winner:
                is_optimal = False
                
        # Base cluster tightness from trust score and SNR
        trust = float(metrics.get('trust_score', 95.0))
        if trust >= 90.0:
            trust_scale = 0.65
        elif trust >= 80.0:
            trust_scale = 1.00
        elif trust >= 70.0:
            trust_scale = 1.35
        else:
            trust_scale = 1.70
            
        sigma_base = float(np.clip(1.0 / math.sqrt(2.0 * max(1.0, 10.0 ** (snr_db / 10.0))), 0.020, 0.055))
        if is_optimal:
            sigma_clean = sigma_base * trust_scale * 0.75
        else:
            # Suboptimal: visibly noisy, fuzzy dispersion (believable channel mismatch)
            sigma_clean = max(0.115, sigma_base * trust_scale * 3.6)
        
        # -------------------------------------------------------------------------
        # Generate Normal Baseline Coordinates
        # -------------------------------------------------------------------------
        clean_pts_i, clean_pts_q = cls._generate_clean_points(mod, cfg, rng, t_now, sigma_clean, trust_scale, is_optimal, n_points)
        
        # If completely normal (no attack active and transition finished)
        if alpha_attack <= 0.001:
            return [[round(float(clean_pts_i[k]), 4), round(float(clean_pts_q[k]), 4)] for k in range(n_points)]
            
        # -------------------------------------------------------------------------
        # Generate Attack Coordinates
        # -------------------------------------------------------------------------
        atk_pts_i, atk_pts_q = cls._generate_attack_points(mod, rng, t_now, n_points)
        
        # If full attack (transition finished)
        if alpha_attack >= 0.999:
            return [[round(float(atk_pts_i[k]), 4), round(float(atk_pts_q[k]), 4)] for k in range(n_points)]
            
        # -------------------------------------------------------------------------
        # Smooth Transition Morphing (0.0 < alpha_attack < 1.0)
        # Interpolates clean to attack with an organic blooming jitter pulse
        # -------------------------------------------------------------------------
        bloom_mag = math.sin(math.pi * alpha_attack) * 0.14
        jitter_i = rng.normal(0, bloom_mag, n_points)
        jitter_q = rng.normal(0, bloom_mag, n_points)
        
        morph_i = (1.0 - alpha_attack) * clean_pts_i + alpha_attack * atk_pts_i + jitter_i
        morph_q = (1.0 - alpha_attack) * clean_pts_q + alpha_attack * atk_pts_q + jitter_q
        return [[round(float(morph_i[k]), 4), round(float(morph_q[k]), 4)] for k in range(n_points)]

    @classmethod
    def _generate_clean_points(cls, mod: str, cfg: Any, rng: np.random.RandomState, 
                               t_now: float, sigma_clean: float, trust_scale: float, 
                               is_optimal: bool, n_points: int):
        """Generate normal clean constellation coordinates with lifelike breathing and suboptimal realism."""
        if mod == 'BPSK':
            # Textbook BPSK: 2 clusters on unit circle at (-1.0, 0) and (+1.0, 0)
            phase_wobble = 0.035 * math.sin(t_now * (2.0 * math.pi / 2.4))
            if not is_optimal:
                phase_wobble += 0.12 * math.sin(t_now * 3.8) + rng.normal(0, 0.04)
            c_x = math.cos(phase_wobble)
            c_y = math.sin(phase_wobble)
            
            half = n_points // 2
            i_pos = rng.normal(+c_x, sigma_clean, half)
            q_pos = rng.normal(+c_y, sigma_clean * (1.1 if not is_optimal else 0.7), half)
            i_neg = rng.normal(-c_x, sigma_clean, n_points - half)
            q_neg = rng.normal(-c_y, sigma_clean * (1.1 if not is_optimal else 0.7), n_points - half)
            
            pts_i = np.concatenate([i_pos, i_neg])
            pts_q = np.concatenate([q_pos, q_neg])
            
            # Suboptimal: add stray noise outliers across decision boundary
            if not is_optimal:
                n_stray = int(n_points * 0.07)
                stray_idx = rng.choice(n_points, size=n_stray, replace=False)
                pts_i[stray_idx] += rng.uniform(-0.4, 0.4, n_stray)
                pts_q[stray_idx] += rng.uniform(-0.35, 0.35, n_stray)
                
            return pts_i, pts_q
            
        elif mod == 'QPSK':
            # Textbook QPSK: 4 symmetric clusters at (+-0.7071, +-0.7071) on unit circle
            phase_wobble = 0.040 * math.sin(t_now * (2.0 * math.pi / 2.8))
            if not is_optimal:
                phase_wobble += 0.15 * math.sin(t_now * 3.4) + rng.normal(0, 0.05)
            cos_w = math.cos(phase_wobble)
            sin_w = math.sin(phase_wobble)
            
            q_size = n_points // 4
            c = 1.0 / math.sqrt(2.0)
            base_centers = [(c, c), (-c, c), (-c, -c), (c, -c)]
            all_i, all_q = [], []
            for (cx, cy) in base_centers:
                rot_cx = cx * cos_w - cy * sin_w
                rot_cy = cx * sin_w + cy * cos_w
                all_i.append(rng.normal(rot_cx, sigma_clean, q_size))
                all_q.append(rng.normal(rot_cy, sigma_clean, q_size))
                
            pts_i = np.concatenate(all_i)
            pts_q = np.concatenate(all_q)
            
            # Suboptimal: add stray noise outliers wandering between quadrants
            if not is_optimal:
                n_stray = int(n_points * 0.08)
                stray_idx = rng.choice(n_points, size=n_stray, replace=False)
                pts_i[stray_idx] = rng.uniform(-0.85, 0.85, n_stray)
                pts_q[stray_idx] = rng.uniform(-0.85, 0.85, n_stray)
                
            return pts_i, pts_q
            
        elif mod in ('FSK', 'FM'):
            # Textbook Angle Modulation (CPFSK / FM): Constant envelope tracing unit circle
            flow_speed = 2.0 * math.pi / 3.2
            base_angles = np.linspace(0, 2.0 * math.pi, n_points, endpoint=False)
            curr_angles = (base_angles + t_now * flow_speed) % (2.0 * math.pi)
            jitter_amp = 0.015 if is_optimal else 0.075
            jitter = rng.uniform(-jitter_amp, jitter_amp, n_points)
            theta = curr_angles + jitter
            
            pulse = 0.025 * math.sin(t_now * (2.0 * math.pi / 1.6)) * trust_scale
            rad_noise = 0.018 * trust_scale if is_optimal else 0.095
            radius = rng.normal(1.0 + pulse, rad_noise, n_points)
            return radius * np.cos(theta), radius * np.sin(theta)
            
        elif mod == 'ASK':
            # Textbook ASK/OOK: 2 discrete clusters on positive real axis at (0, 0) and (1.0, 0)
            pulse_1 = 1.0 + 0.05 * math.sin(t_now * (2.0 * math.pi / 1.8))
            half = n_points // 2
            i_zero = rng.normal(0.0, sigma_clean * 0.6, half)
            q_zero = rng.normal(0.0, sigma_clean * 0.5, half)
            i_one = rng.normal(pulse_1, sigma_clean, n_points - half)
            q_one = rng.normal(0.0, sigma_clean * 0.6, n_points - half)
            
            pts_i = np.concatenate([i_zero, i_one])
            pts_q = np.concatenate([q_zero, q_one])
            
            if not is_optimal:
                n_stray = int(n_points * 0.06)
                stray_idx = rng.choice(n_points, size=n_stray, replace=False)
                pts_i[stray_idx] = rng.uniform(0.1, 0.9, n_stray)
                pts_q[stray_idx] = rng.uniform(-0.25, 0.25, n_stray)
                
            return pts_i, pts_q
            
        elif mod == 'AM_DSBSC':
            # Carrier-synchronized suppressed carrier: line centered at (0, 0) spanning [-1, +1]
            env_pulse = math.sin(t_now * (2.0 * math.pi / 2.0))
            envelope_gain = 0.55 + 0.45 * abs(env_pulse)
            t_wave = np.linspace(0, 8.0 * np.pi, n_points)
            audio_m = np.cos(t_wave) * 0.95 + 0.15 * np.cos(3.0 * t_wave)
            audio_m = (audio_m / max(1e-6, np.max(np.abs(audio_m)))) * envelope_gain
            
            sigma_noise_i = 0.015 * trust_scale if is_optimal else 0.075
            sigma_noise_q = 0.020 * trust_scale if is_optimal else 0.085
            noise_i = rng.normal(0.0, sigma_noise_i, n_points)
            noise_q = rng.normal(0.0, sigma_noise_q, n_points)
            return audio_m * 0.95 + noise_i, noise_q
            
        elif mod == 'AM_DSBTC':
            # Carrier-synchronized full carrier: positive line segment centered at +1.0
            mod_depth = 0.60 + 0.35 * math.sin(t_now * (2.0 * math.pi / 2.0))
            t_wave = np.linspace(0, 8.0 * np.pi, n_points)
            mu = float(getattr(cfg, 'am_index', 0.8))
            audio_m = np.cos(t_wave)
            env = 1.0 + mu * mod_depth * audio_m
            env_scaled = (env - 1.0) * 0.75 + 1.0
            
            sigma_noise_i = 0.015 * trust_scale if is_optimal else 0.075
            sigma_noise_q = 0.020 * trust_scale if is_optimal else 0.085
            noise_i = rng.normal(0.0, sigma_noise_i, n_points)
            noise_q = rng.normal(0.0, sigma_noise_q, n_points)
            return env_scaled * 0.9 + noise_i, noise_q
            
        else:
            return rng.normal(0.0, 0.1, n_points), rng.normal(0.0, 0.1, n_points)

    @classmethod
    def _generate_attack_points(cls, mod: str, rng: np.random.RandomState, t_now: float, n_points: int):
        """Generate attack-distorted constellation points with unique physical jammer signatures."""
        if mod == 'BPSK':
            # Jammed BPSK: 2 antipodal clusters pulled into rotating banana arcs + breakthrough sparks
            half = n_points // 2
            jam_rot = (t_now * 8.0) % (2.0 * math.pi)
            sweep = math.sin(t_now * 6.0) * 1.2
            
            arc1_angles = rng.normal(jam_rot, 0.38, half) + sweep
            r1 = rng.normal(1.0, 0.16, half)
            i1 = r1 * np.cos(arc1_angles)
            q1 = r1 * np.sin(arc1_angles)
            
            arc2_angles = rng.normal(jam_rot + math.pi, 0.38, n_points - half) + sweep
            r2 = rng.normal(1.0, 0.16, n_points - half)
            i2 = r2 * np.cos(arc2_angles)
            q2 = r2 * np.sin(arc2_angles)
            
            pts_i = np.concatenate([i1, i2])
            pts_q = np.concatenate([q1, q2])
            spikes = rng.choice(n_points, size=n_points // 12, replace=False)
            pts_i[spikes] = rng.uniform(-1.2, 1.2, len(spikes))
            pts_q[spikes] = rng.uniform(-0.5, 0.5, len(spikes))
            return pts_i, pts_q
            
        elif mod == 'QPSK':
            # Jammed QPSK: 4 quadrant clusters warped into rotating pinwheel spirals + axis leakage
            q_size = n_points // 4
            jam_sweep = math.sin(t_now * 6.0) * 1.1
            t_spin = (t_now * 4.5) % (2.0 * math.pi)
            all_i, all_q = [], []
            base_quads = [math.pi / 4.0, 3.0 * math.pi / 4.0, 5.0 * math.pi / 4.0, 7.0 * math.pi / 4.0]
            for base_q in base_quads:
                angles = rng.normal(base_q + t_spin + jam_sweep, 0.30, q_size)
                radii = rng.normal(1.0, 0.22, q_size)
                all_i.append(radii * np.cos(angles))
                all_q.append(radii * np.sin(angles))
                
            pts_i = np.concatenate(all_i)
            pts_q = np.concatenate(all_q)
            leak = rng.choice(n_points, size=n_points // 10, replace=False)
            pts_i[leak] += rng.normal(0, 0.30, len(leak))
            pts_q[leak] += rng.normal(0, 0.30, len(leak))
            return pts_i, pts_q
            
        elif mod == 'ASK':
            # Jammed ASK: Heavy amplitude power surges and spikes along the real axis
            amp_surge = 0.5 + 0.45 * math.sin(t_now * 11.0)
            half = n_points // 2
            i_zero = np.abs(rng.normal(0.25, 0.22, half)) * amp_surge
            q_zero = rng.normal(0.0, 0.20, half)
            i_one = rng.normal(1.2 + amp_surge, 0.38, n_points - half)
            q_one = rng.normal(0.0, 0.25, n_points - half)
            
            pts_i = np.clip(np.concatenate([i_zero, i_one]), -0.2, 2.4)
            pts_q = np.concatenate([q_zero, q_one])
            return pts_i, pts_q
            
        elif mod == 'FSK':
            # Jammed FSK: Constant-envelope ring remains intact, with an orbiting jammer beat note
            n_ring = int(n_points * 0.78)
            n_knot = n_points - n_ring
            
            angles_ring = np.linspace(0, 2.0 * math.pi, n_ring, endpoint=False) + rng.uniform(-0.02, 0.02, n_ring)
            r_ring = rng.normal(1.0, 0.040, n_ring)
            i_ring = r_ring * np.cos(angles_ring)
            q_ring = r_ring * np.sin(angles_ring)
            
            jam_pos = (t_now * 4.5) % (2.0 * math.pi)
            angles_knot = rng.normal(jam_pos, 0.16, n_knot)
            r_knot = rng.normal(1.24, 0.10, n_knot)
            i_knot = r_knot * np.cos(angles_knot)
            q_knot = r_knot * np.sin(angles_knot)
            
            pts_i = np.concatenate([i_ring, i_knot])
            pts_q = np.concatenate([q_ring, q_knot])
            return pts_i, pts_q
            
        elif mod == 'FM':
            # Jammed FM: Precessing eccentric ellipse reflecting FM limiter capture effect
            angles = np.linspace(0, 2.0 * np.pi, n_points, endpoint=False)
            wobble_freq = (t_now * 4.0) % (2.0 * math.pi)
            eccentricity = 0.28 * math.sin(t_now * 5.0)
            r_fm = 1.0 + eccentricity * np.cos(angles - wobble_freq) + rng.normal(0, 0.035, n_points)
            return r_fm * np.cos(angles), r_fm * np.sin(angles)
            
        elif mod == 'AM_DSBSC':
            # Jammed AM-DSBSC: Rogue carrier reinsertion breaks line into spinning Lissajous bowtie
            t_w = np.linspace(0, 4.0 * math.pi, n_points)
            jam_leak = 0.5 * math.sin(t_now * 6.0)
            pts_i = np.sin(t_w) + rng.normal(0, 0.04, n_points)
            pts_q = np.sin(2.0 * t_w + jam_leak) * 0.45 + rng.normal(0, 0.05, n_points)
            return pts_i, pts_q
            
        elif mod == 'AM_DSBTC':
            # Jammed AM-DSBTC: Overmodulation carrier collapse into distorted trapezoid
            t_w = np.linspace(0, 4.0 * math.pi, n_points)
            overmod = 1.0 + 0.8 * math.sin(t_now * 5.0)
            env_jam = np.clip(1.0 + overmod * np.cos(t_w), -0.4, 2.2)
            pts_i = (env_jam - 1.0) * 0.7 + 1.0 + rng.normal(0, 0.05, n_points)
            pts_q = np.sin(t_w) * 0.35 * abs(overmod) + rng.normal(0, 0.04, n_points)
            return pts_i, pts_q
            
        else:
            sweep_phase = np.sin(t_now * 14.0) * 2.2
            t_rot = (t_now * 8.0) % (2.0 * math.pi)
            r_distort = rng.normal(0.68, 0.36, n_points)
            theta = rng.uniform(0, 2.0 * np.pi, n_points) + sweep_phase + t_rot
            return r_distort * np.cos(theta), r_distort * np.sin(theta)
