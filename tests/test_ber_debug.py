import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twin_core.config import TxConfig, derive_link_plan, DIGITAL_MODS
from twin_core.waveforms import Modulator
from twin_core.channel import ChannelModel
from twin_core.receiver import Receiver
from twin_core.presets import PRESETS, get_preset_config
from twin_core.scoring import Scorer
from twin_core.metrics import MetricCalculator, RollingMetrics

modulator = Modulator()
channel = ChannelModel()
receiver = Receiver()

print("=" * 80)
print("TESTING ALL DIGITAL MODULATIONS ACROSS EACH DIGITAL PRESET")
print("=" * 80)

for name in ['deep_space', 'urban_cellular', 'leo_doppler', 'iot_tag', 'fdia_attack']:
    base_cfg = get_preset_config(name)
    print(f"\n--- Scenario: {name} ---")
    for mod in DIGITAL_MODS:
        cfg = TxConfig(**base_cfg.to_dict())
        cfg.modulation = mod
        plan = derive_link_plan(cfg)
        rolling = RollingMetrics()
        
        # Test 5 consecutive frames as in real-time engine
        scores = []
        bers = []
        hdrs = []
        for f_idx in range(5):
            tx_frame = modulator.generate_digital_frame(cfg, cfg_version=1)
            rx_iq, _, _ = channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
            rx_res = receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
            rolling.update_digital(1, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
            metrics = MetricCalculator.compute_all_metrics(plan, cfg, rx_res, rolling, tx_frame.iq)
            score_res = Scorer.evaluate(plan, cfg, metrics)
            scores.append(score_res['total'])
            bers.append(metrics['ber'])
            hdrs.append(rx_res['header_valid'])
            
        print(f"  Mod: {mod:<5} | Frame 1: BER={bers[0]:.4f}, Score={scores[0]} | Frame 5: BER={bers[-1]:.4f}, Score={scores[-1]} | HDR_valid={hdrs}")
