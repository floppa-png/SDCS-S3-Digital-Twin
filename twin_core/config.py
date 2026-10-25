import math
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Tuple, List, Optional
import numpy as np

MODULATIONS = ['BPSK', 'QPSK', 'ASK', 'FSK', 'AM_DSBSC', 'AM_DSBTC', 'FM']
DIGITAL_MODS = {'BPSK', 'QPSK', 'ASK', 'FSK'}
ANALOG_MODS = {'AM_DSBSC', 'AM_DSBTC', 'FM'}
CHANNELS = ['awgn', 'rayleigh', 'rician']
PROFILES = ['balanced', 'reliability', 'throughput', 'low_power']
SOURCES = ['digital', 'analog']

PARAM_SPEC = {
    'modulation': {'type': str, 'enum': MODULATIONS, 'default': 'BPSK'},
    'source_type': {'type': str, 'enum': SOURCES, 'default': 'digital'},
    'data_rate': {'type': int, 'min': 1000, 'max': 400000, 'default': 50000},
    'msg_bw': {'type': int, 'min': 300, 'max': 20000, 'default': 5000},
    'pcm_bits': {'type': int, 'min': 4, 'max': 12, 'default': 8},
    'alloc_bw': {'type': int, 'min': 5000, 'max': 400000, 'default': 60000},
    'rolloff': {'type': float, 'min': 0.10, 'max': 1.00, 'default': 0.35},
    'center_freq': {'type': float, 'min': 325e6, 'max': 3.8e9, 'default': 2.4e9},
    'snr_db': {'type': float, 'min': -5.0, 'max': 35.0, 'default': 12.0},
    'channel': {'type': str, 'enum': CHANNELS, 'default': 'awgn'},
    'k_factor_db': {'type': float, 'min': -10.0, 'max': 20.0, 'default': 6.0},
    'doppler_hz': {'type': float, 'min': 0.0, 'max': 2000.0, 'default': 0.0},
    'cfo_hz': {'type': float, 'min': -5000.0, 'max': 5000.0, 'default': 0.0},
    'phase_noise_deg': {'type': float, 'min': 0.0, 'max': 20.0, 'default': 0.0},
    'am_index': {'type': float, 'min': 0.1, 'max': 1.0, 'default': 0.8},
    'fm_beta': {'type': float, 'min': 0.5, 'max': 10.0, 'default': 5.0},
    'fsk_h': {'type': float, 'min': 0.5, 'max': 2.0, 'default': 1.0},
    'target_ber': {'type': float, 'min': 1e-7, 'max': 1e-2, 'default': 1e-5},
    'target_snr_out': {'type': float, 'min': 10.0, 'max': 50.0, 'default': 30.0},
    'packet_bits': {'type': int, 'min': 64, 'max': 4096, 'default': 1024},
    'profile': {'type': str, 'enum': PROFILES, 'default': 'balanced'},
    'tx_atten_db': {'type': float, 'min': 0.0, 'max': 89.75, 'default': 30.0},
    'rx_gain_db': {'type': float, 'min': 0.0, 'max': 73.0, 'default': 40.0},
    'fdia_active': {'type': bool, 'default': False},
}

@dataclass
class TxConfig:
    modulation: str = 'BPSK'
    source_type: str = 'digital'
    data_rate: int = 50000
    msg_bw: int = 5000
    pcm_bits: int = 8
    alloc_bw: int = 60000
    rolloff: float = 0.35
    center_freq: float = 2.4e9
    snr_db: float = 12.0
    channel: str = 'awgn'
    k_factor_db: float = 6.0
    doppler_hz: float = 0.0
    cfo_hz: float = 0.0
    phase_noise_deg: float = 0.0
    am_index: float = 0.8
    fm_beta: float = 5.0
    fsk_h: float = 1.0
    target_ber: float = 1e-5
    target_snr_out: float = 30.0
    packet_bits: int = 1024
    profile: str = 'balanced'
    tx_atten_db: float = 30.0
    rx_gain_db: float = 40.0
    fdia_active: bool = False
    fs: int = 1000000  # Fixed 1 MSPS Pluto-safe baseband rate

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def validate_config(updates: Dict[str, Any], allow_modulation: bool = False) -> Tuple[Dict[str, Any], Dict[str, str]]:
    clean = {}
    errors = {}
    
    if not isinstance(updates, dict):
        return {}, {'body': 'Expected JSON object'}
        
    for k, v in updates.items():
        if k == 'fs':
            continue  # fs is fixed
        if k == 'modulation' and not allow_modulation:
            errors[k] = 'Modulation cannot be modified via general config endpoint'
            continue
        if k not in PARAM_SPEC:
            errors[k] = f'Unknown parameter: {k}'
            continue
            
        spec = PARAM_SPEC[k]
        target_type = spec['type']
        
        try:
            if target_type == int:
                val = int(v)
            elif target_type == float:
                val = float(v)
            elif target_type == str:
                val = str(v)
            else:
                val = v
        except (ValueError, TypeError):
            errors[k] = f'Invalid type for {k}, expected {target_type.__name__}'
            continue
            
        if 'enum' in spec and val not in spec['enum']:
            errors[k] = f'Value {val} not in allowed options: {spec["enum"]}'
            continue
            
        if 'min' in spec and val < spec['min']:
            errors[k] = f'Value {val} below minimum {spec["min"]}'
            continue
            
        if 'max' in spec and val > spec['max']:
            errors[k] = f'Value {val} above maximum {spec["max"]}'
            continue
            
        clean[k] = val
        
    return clean, errors

validate_params = validate_config

@dataclass
class LinkPlan:
    modulation: str
    is_digital: bool
    applicable: bool
    fits: bool
    bits_per_symbol: int
    symbol_rate: float
    samples_per_symbol: int
    bit_rate: float
    occupied_bw: float
    c_over_n0_db: float
    ebn0_db: float
    esn0_db: float
    snr_occ_db: float
    gamma_analog_db: float
    msg_bw_effective: float
    fidelity_factor: float
    notes: List[str] = field(default_factory=list)

def derive_link_plan(cfg: TxConfig, mod: Optional[str] = None) -> LinkPlan:
    if mod is None:
        mod = cfg.modulation
        
    fs = cfg.fs
    alloc_bw = cfg.alloc_bw
    c_over_n0_db = cfg.snr_db + 10.0 * math.log10(max(1.0, float(alloc_bw)))
    
    k_bits = {'BPSK': 1, 'QPSK': 2, 'ASK': 1, 'FSK': 1}.get(mod, 1)
    is_digital = mod in DIGITAL_MODS
    notes = []
    

    if cfg.source_type == 'digital' and is_digital:
        rb_req = float(cfg.data_rate)
        alpha = cfg.rolloff
        
        if mod == 'FSK':
            occ_factor = (cfg.fsk_h + 1.0 + alpha)
        else:
            occ_factor = (1.0 + alpha)
            
        rs_max_by_bw = alloc_bw / occ_factor
        rs_desired = rb_req / k_bits
        rs_target = min(rs_desired, rs_max_by_bw)
        
        sps = int(round(fs / rs_target))
        sps = max(4, min(1000, sps))
        rs_actual = fs / sps
        rb_actual = rs_actual * k_bits
        b_occ = rs_actual * occ_factor
        
        fits = (b_occ <= alloc_bw * 1.02)
        if rb_actual < rb_req * 0.98:
            notes.append(f'Data rate throttled from {rb_req/1e3:.1f}k to {rb_actual/1e3:.1f}k to fit {alloc_bw/1e3:.1f}kHz channel.')
            
        ebn0_db = c_over_n0_db - 10.0 * math.log10(max(1.0, rb_actual))
        esn0_db = ebn0_db + 10.0 * math.log10(float(k_bits))
        snr_occ_db = c_over_n0_db - 10.0 * math.log10(max(1.0, b_occ))
        
        return LinkPlan(
            modulation=mod,
            is_digital=True,
            applicable=True,
            fits=fits,
            bits_per_symbol=k_bits,
            symbol_rate=rs_actual,
            samples_per_symbol=sps,
            bit_rate=rb_actual,
            occupied_bw=b_occ,
            c_over_n0_db=c_over_n0_db,
            ebn0_db=ebn0_db,
            esn0_db=esn0_db,
            snr_occ_db=snr_occ_db,
            gamma_analog_db=0.0,
            msg_bw_effective=0.0,
            fidelity_factor=min(1.0, rb_actual / rb_req),
            notes=notes
        )
        
    if cfg.source_type == 'analog' and is_digital:
        # Analog source transmitted via PCM digitisation over digital modulation
        w_orig = float(cfg.msg_bw)
        alpha = cfg.rolloff
        occ_factor = (cfg.fsk_h + 1.0 + alpha) if mod == 'FSK' else (1.0 + alpha)
        rs_max_by_bw = alloc_bw / occ_factor
        rb_max = rs_max_by_bw * k_bits
        
        # Try configured pcm_bits, fallback to lower down to 4
        pcm_bits = cfg.pcm_bits
        fs_pcm = 2.5 * w_orig
        rb_req = pcm_bits * fs_pcm
        
        w_eff = w_orig
        if rb_req > rb_max:
            # Try reducing PCM bits first
            for b_cand in range(pcm_bits, 3, -1):
                if b_cand * fs_pcm <= rb_max:
                    pcm_bits = b_cand
                    rb_req = pcm_bits * fs_pcm
                    break
            else:
                # Still exceeds: reduce bandwidth of analog message W
                pcm_bits = 4
                fs_pcm_max = rb_max / pcm_bits
                w_eff = max(300.0, fs_pcm_max / 2.5)
                rb_req = pcm_bits * 2.5 * w_eff
                notes.append(f'Message LPF cutoff reduced to {w_eff:.0f}Hz to fit PCM in channel.')
                
        rs_target = min(rb_req / k_bits, rs_max_by_bw)
        sps = int(round(fs / rs_target))
        sps = max(4, min(1000, sps))
        rs_actual = fs / sps
        rb_actual = rs_actual * k_bits
        b_occ = rs_actual * occ_factor
        
        ebn0_db = c_over_n0_db - 10.0 * math.log10(max(1.0, rb_actual))
        esn0_db = ebn0_db + 10.0 * math.log10(float(k_bits))
        snr_occ_db = c_over_n0_db - 10.0 * math.log10(max(1.0, b_occ))
        fidelity = (w_eff / w_orig) * (pcm_bits / max(4.0, float(cfg.pcm_bits)))
        
        return LinkPlan(
            modulation=mod,
            is_digital=True,
            applicable=True,
            fits=True,
            bits_per_symbol=k_bits,
            symbol_rate=rs_actual,
            samples_per_symbol=sps,
            bit_rate=rb_actual,
            occupied_bw=b_occ,
            c_over_n0_db=c_over_n0_db,
            ebn0_db=ebn0_db,
            esn0_db=esn0_db,
            snr_occ_db=snr_occ_db,
            gamma_analog_db=c_over_n0_db - 10.0 * math.log10(max(1.0, w_eff)),
            msg_bw_effective=w_eff,
            fidelity_factor=fidelity,
            notes=notes
        )
        
    if not is_digital:
        w_orig = float(getattr(cfg, 'msg_bw', 5000.0))
        if w_orig <= 0.0:
            w_orig = min(15000.0, max(3000.0, alloc_bw / 4.0))
        
        if mod in ('AM_DSBSC', 'AM_DSBTC'):
            # AM occupied BW is 2 * W
            b_req = 2.0 * w_orig
            if b_req > alloc_bw:
                w_eff = max(300.0, alloc_bw / 2.0)
                b_occ = 2.0 * w_eff
                notes.append(f'Message bandlimited to {w_eff:.0f}Hz to prevent spectral overflow.')
            else:
                w_eff = w_orig
                b_occ = b_req
                
            fidelity = w_eff / w_orig
            if cfg.source_type == 'digital':
                fidelity = min(fidelity, (4.0 * w_eff) / max(1.0, float(cfg.data_rate)))
            gamma_db = c_over_n0_db - 10.0 * math.log10(max(1.0, w_eff))
            
            return LinkPlan(
                modulation=mod,
                is_digital=False,
                applicable=True,
                fits=True,
                bits_per_symbol=0,
                symbol_rate=0.0,
                samples_per_symbol=0,
                bit_rate=0.0,
                occupied_bw=b_occ,
                c_over_n0_db=c_over_n0_db,
                ebn0_db=0.0,
                esn0_db=0.0,
                snr_occ_db=c_over_n0_db - 10.0 * math.log10(max(1.0, b_occ)),
                gamma_analog_db=gamma_db,
                msg_bw_effective=w_eff,
                fidelity_factor=fidelity,
                notes=notes
            )
            
        if mod == 'FM':
            # Carson's Bandwidth = 2 * (beta + 1) * W
            beta_req = cfg.fm_beta
            b_req = 2.0 * (beta_req + 1.0) * w_orig
            w_eff = w_orig
            
            if b_req > alloc_bw:
                # Reduce beta down to 0.3 (narrowband FM)
                beta_eff = (alloc_bw / (2.0 * w_orig)) - 1.0
                if beta_eff < 0.3:
                    beta_eff = 0.3
                    w_eff = max(300.0, alloc_bw / (2.0 * 1.3))
                    notes.append(f'FM index reduced to {beta_eff:.2f} and bandwidth to {w_eff:.0f}Hz to fit channel.')
                else:
                    notes.append(f'FM index reduced from {beta_req:.1f} to {beta_eff:.2f} to fit channel.')
            else:
                beta_eff = beta_req
                
            b_occ = 2.0 * (beta_eff + 1.0) * w_eff
            fidelity = (w_eff / w_orig) * min(1.0, beta_eff / beta_req)
            if cfg.source_type == 'digital':
                fidelity = min(fidelity, (4.0 * w_eff) / max(1.0, float(cfg.data_rate)))
            gamma_db = c_over_n0_db - 10.0 * math.log10(max(1.0, w_eff))
            
            return LinkPlan(
                modulation='FM',
                is_digital=False,
                applicable=True,
                fits=True,
                bits_per_symbol=0,
                symbol_rate=0.0,
                samples_per_symbol=0,
                bit_rate=0.0,
                occupied_bw=b_occ,
                c_over_n0_db=c_over_n0_db,
                ebn0_db=0.0,
                esn0_db=0.0,
                snr_occ_db=c_over_n0_db - 10.0 * math.log10(max(1.0, b_occ)),
                gamma_analog_db=gamma_db,
                msg_bw_effective=w_eff,
                fidelity_factor=fidelity,
                notes=notes
            )

    return LinkPlan(
        modulation=mod,
        is_digital=is_digital,
        applicable=False,
        fits=False,
        bits_per_symbol=0,
        symbol_rate=0.0,
        samples_per_symbol=0,
        bit_rate=0.0,
        occupied_bw=0.0,
        c_over_n0_db=c_over_n0_db,
        ebn0_db=0.0,
        esn0_db=0.0,
        snr_occ_db=0.0,
        gamma_analog_db=0.0,
        msg_bw_effective=0.0,
        fidelity_factor=0.0,
        notes=['Unhandled modulation / source combination']
    )
