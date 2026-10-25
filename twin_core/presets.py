import random
from typing import Dict, Any, List, Optional
from .config import TxConfig, DIGITAL_MODS, ANALOG_MODS

SCENARIO_METADATA: Dict[str, Dict[str, Any]] = {
    'deep_space': {
        'name': 'Deep Space Probe (NASA DSN Downlink)',
        'category': 'digital',
        'type_label': 'DIGITAL · POWER-CONSTRAINED',
        'description': 'Extreme link distance, power-constrained deep space AWGN channel with oscillator phase noise. Requires maximum sensitivity.',
        'expected_winner': 'BPSK',
        'badge_color': '#22d3ee'
    },
    'urban_cellular': {
        'name': 'Urban Tactical Mobile (4G/5G Microcell)',
        'category': 'digital',
        'type_label': 'DIGITAL · MULTIPATH FADING',
        'description': 'Non-LOS dense urban environment with Rayleigh multipath fading and vehicle-induced Doppler spread.',
        'expected_winner': 'QPSK',
        'badge_color': '#8b5cf6'
    },
    'leo_doppler': {
        'name': 'LEO Orbit Doppler Satellite (Starlink / CubeSat)',
        'category': 'digital',
        'type_label': 'DIGITAL · HIGH DOPPLER DYNAMICS',
        'description': 'High-velocity low-earth-orbit pass with severe carrier frequency offset and dynamic Doppler shifts.',
        'expected_winner': 'FSK',
        'badge_color': '#10b981'
    },
    'iot_tag': {
        'name': 'Ultra-Low Power IoT Sensor (Sub-GHz Smart Meter)',
        'category': 'digital',
        'type_label': 'DIGITAL · ENERGY-CRITICAL',
        'description': 'Minimal receiver energy budget. Requires low-complexity non-coherent detection for multi-year battery life.',
        'expected_winner': 'ASK',
        'badge_color': '#f59e0b'
    },
    'fm_broadcast': {
        'name': 'High-Fidelity Stereo Broadcast (Commercial FM)',
        'category': 'analog',
        'type_label': 'ANALOG · WIDEBAND ANGLE',
        'description': 'Wideband high-fidelity audio transmission with wide channel allocation and FM capture effect.',
        'expected_winner': 'FM',
        'badge_color': '#06b6d4'
    },
    'am_broadcast': {
        'name': 'Aviation & Ground Tower Comms (AM-DSBTC)',
        'category': 'analog',
        'type_label': 'ANALOG · ENVELOPE BROADCAST',
        'description': 'Full-carrier double-sideband amplitude modulation for legacy avionics envelope detectors.',
        'expected_winner': 'AM_DSBTC',
        'badge_color': '#ec4899'
    },
    'coherent_voice': {
        'name': 'Maritime Tactical Audio (AM-DSBSC)',
        'category': 'analog',
        'type_label': 'ANALOG · SUPPRESSED CARRIER',
        'description': '100% power-efficient suppressed-carrier voice transmission for power-limited marine transceivers.',
        'expected_winner': 'AM_DSBSC',
        'badge_color': '#a855f7'
    },
    'fdia_attack': {
        'name': 'Electronic Warfare (FDIA Jamming & Spoofing)',
        'category': 'security',
        'type_label': 'CYBER-PHYSICAL · ADVERSARIAL ATTACK',
        'description': 'False Data Injection Attack with adversarial in-band noise bursts and pilot spoofing.',
        'expected_winner': 'FSK',
        'badge_color': '#ef4444'
    }
}

PRESETS: Dict[str, Dict[str, Any]] = {
    'deep_space': {
        'modulation': 'BPSK',
        'source_type': 'digital',
        'data_rate': 10000,
        'alloc_bw': 180000,
        'snr_db': 6.0,
        'channel': 'awgn',
        'phase_noise_deg': 3.0,
        'cfo_hz': 0.0,
        'doppler_hz': 0.0,
        'profile': 'reliability',
        'target_ber': 1e-4
    },
    'urban_cellular': {
        'modulation': 'QPSK',
        'source_type': 'digital',
        'data_rate': 80000,
        'alloc_bw': 85000,
        'snr_db': 20.0,
        'channel': 'rayleigh',
        'doppler_hz': 25.0,
        'cfo_hz': 150.0,
        'profile': 'throughput',
        'target_ber': 1e-4
    },
    'leo_doppler': {
        'modulation': 'FSK',
        'source_type': 'digital',
        'data_rate': 20000,
        'alloc_bw': 120000,
        'snr_db': 18.0,
        'channel': 'rayleigh',
        'doppler_hz': 550.0,
        'cfo_hz': 2800.0,
        'fsk_h': 1.0,
        'profile': 'reliability',
        'target_ber': 1e-3
    },
    'iot_tag': {
        'modulation': 'ASK',
        'source_type': 'digital',
        'data_rate': 20000,
        'alloc_bw': 35000,
        'snr_db': 22.0,
        'cfo_hz': 400.0,
        'doppler_hz': 0.0,
        'channel': 'awgn',
        'profile': 'low_power',
        'target_ber': 1e-4
    },
    'fm_broadcast': {
        'modulation': 'FM',
        'source_type': 'analog',
        'msg_bw': 15000,
        'alloc_bw': 180000,
        'snr_db': 22.0,
        'channel': 'rayleigh',
        'doppler_hz': 40.0,
        'cfo_hz': 0.0,
        'fm_beta': 5.0,
        'profile': 'balanced',
        'target_snr_out': 20.0
    },
    'am_broadcast': {
        'modulation': 'AM_DSBTC',
        'source_type': 'analog',
        'msg_bw': 5000,
        'alloc_bw': 12000,
        'snr_db': 28.0,
        'channel': 'awgn',
        'cfo_hz': 300.0,
        'phase_noise_deg': 4.0,
        'am_index': 0.85,
        'profile': 'low_power',
        'target_snr_out': 16.0
    },
    'coherent_voice': {
        'modulation': 'AM_DSBSC',
        'source_type': 'analog',
        'msg_bw': 5000,
        'alloc_bw': 12000,
        'snr_db': 18.0,
        'channel': 'awgn',
        'cfo_hz': 0.0,
        'phase_noise_deg': 2.0,
        'profile': 'balanced',
        'target_snr_out': 14.0
    },
    'fdia_attack': {
        'modulation': 'FSK',
        'source_type': 'digital',
        'data_rate': 25000,
        'alloc_bw': 100000,
        'snr_db': 18.0,
        'channel': 'awgn',
        'doppler_hz': 0.0,
        'cfo_hz': 500.0,
        'fdia_active': True,
        'profile': 'reliability',
        'target_ber': 1e-3
    }
}

EXPECTED_WINNERS: Dict[str, str] = {
    k: v['expected_winner'] for k, v in SCENARIO_METADATA.items()
}

def list_presets() -> List[str]:
    """Return all available preset names."""
    return list(PRESETS.keys())

def get_preset_config(preset_name: str, keep_modulation: Optional[str] = None) -> TxConfig:
    """Retrieve TxConfig for the given preset scenario with optional modulation override."""
    if preset_name not in PRESETS:
        preset_name = 'deep_space'
    data = PRESETS[preset_name].copy()
    sc_source = data.get('source_type', 'digital')
    if keep_modulation:
        if sc_source == 'analog' and keep_modulation in ANALOG_MODS:
            data['modulation'] = keep_modulation
        elif sc_source == 'digital' and keep_modulation in DIGITAL_MODS:
            data['modulation'] = keep_modulation
    return TxConfig(**data)

def randomize_scenario(preset_name: str, current_modulation: Optional[str] = None) -> TxConfig:
    """
    Randomize channel and operational parameters strictly within the physical bounds
    of the selected scenario. Keeps the scenario identity intact!
    """
    if preset_name not in PRESETS:
        preset_name = 'deep_space'
        
    base = PRESETS[preset_name].copy()
    sc_source = base.get('source_type', 'digital')
    mod = current_modulation if current_modulation else base['modulation']
    if sc_source == 'analog' and mod in ANALOG_MODS:
        base['modulation'] = mod
    elif sc_source == 'digital' and mod in DIGITAL_MODS:
        base['modulation'] = mod
    
    if preset_name == 'deep_space':
        base['snr_db'] = round(random.uniform(5.0, 9.0), 1)
        base['alloc_bw'] = int(round(random.uniform(160000, 220000) / 10000) * 10000)
        base['data_rate'] = int(round(random.uniform(8000, 14000) / 1000) * 1000)
        base['phase_noise_deg'] = round(random.uniform(2.0, 5.0), 1)
        base['channel'] = 'awgn'
        
    elif preset_name == 'urban_cellular':
        base['snr_db'] = round(random.uniform(20.0, 26.0), 1)
        base['alloc_bw'] = int(round(random.uniform(85000, 105000) / 5000) * 5000)
        base['data_rate'] = int(round(random.uniform(60000, 80000) / 5000) * 5000)
        base['doppler_hz'] = round(random.uniform(15.0, 35.0), 1)
        base['cfo_hz'] = round(random.uniform(-150.0, 150.0), 1)
        base['channel'] = 'rayleigh'
        
    elif preset_name == 'leo_doppler':
        base['snr_db'] = round(random.uniform(16.0, 22.0), 1)
        base['alloc_bw'] = int(round(random.uniform(110000, 140000) / 10000) * 10000)
        base['data_rate'] = int(round(random.uniform(15000, 25000) / 5000) * 5000)
        base['doppler_hz'] = round(random.uniform(300.0, 600.0), 1)
        base['cfo_hz'] = round(random.uniform(1800.0, 3200.0), 1)
        base['channel'] = 'rayleigh'
        
    elif preset_name == 'iot_tag':
        base['snr_db'] = round(random.uniform(20.0, 26.0), 1)
        base['alloc_bw'] = int(round(random.uniform(30000, 45000) / 5000) * 5000)
        base['data_rate'] = int(round(random.uniform(15000, 25000) / 5000) * 5000)
        base['cfo_hz'] = round(random.uniform(200.0, 600.0), 1)
        base['channel'] = 'awgn'
        
    elif preset_name == 'fm_broadcast':
        base['snr_db'] = round(random.uniform(20.0, 26.0), 1)
        base['alloc_bw'] = int(round(random.uniform(160000, 200000) / 10000) * 10000)
        base['msg_bw'] = int(round(random.uniform(12000, 16000) / 1000) * 1000)
        base['fm_beta'] = round(random.uniform(4.0, 6.0), 1)
        base['doppler_hz'] = round(random.uniform(20.0, 50.0), 1)
        base['channel'] = 'rayleigh'
        
    elif preset_name == 'am_broadcast':
        base['snr_db'] = round(random.uniform(26.0, 32.0), 1)
        base['alloc_bw'] = int(round(random.uniform(11000, 14000) / 1000) * 1000)
        base['msg_bw'] = int(round(random.uniform(4000, 5500) / 500) * 500)
        base['am_index'] = round(random.uniform(0.75, 0.90), 2)
        base['cfo_hz'] = round(random.uniform(100.0, 400.0), 1)
        base['phase_noise_deg'] = round(random.uniform(2.0, 5.0), 1)
        base['channel'] = 'awgn'
        
    elif preset_name == 'coherent_voice':
        base['snr_db'] = round(random.uniform(18.0, 24.0), 1)
        base['alloc_bw'] = int(round(random.uniform(11000, 14000) / 1000) * 1000)
        base['msg_bw'] = int(round(random.uniform(4000, 5500) / 500) * 500)
        base['phase_noise_deg'] = round(random.uniform(1.0, 3.0), 1)
        base['channel'] = 'awgn'
        
    elif preset_name == 'fdia_attack':
        base['snr_db'] = round(random.uniform(18.0, 24.0), 1)
        base['alloc_bw'] = int(round(random.uniform(90000, 120000) / 10000) * 10000)
        base['data_rate'] = int(round(random.uniform(20000, 30000) / 5000) * 5000)
        base['cfo_hz'] = round(random.uniform(200.0, 800.0), 1)
        base['fdia_active'] = True
        base['channel'] = 'awgn'
        
    return TxConfig(**base)
