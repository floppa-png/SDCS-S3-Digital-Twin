import os
import sys
import numpy as np

# Add project root to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from twin_core.config import TxConfig, derive_link_plan
from twin_core.presets import PRESETS, get_preset_config, randomize_scenario
from twin_core.scoring import Scorer
from twin_core.twin import DigitalTwin
from twin_core.waveforms import Modulator
from twin_core.channel import ChannelModel
from twin_core.receiver import Receiver
from twin_core.metrics import MetricCalculator, RollingMetrics

def test_all_scenarios():
    print("=" * 80)
    print("TEST 1: 9 SCENARIO PRESETS & DIGITAL TWIN RECOMMENDATIONS")
    print("=" * 80)
    twin = DigitalTwin(fs=1000000)
    
    from twin_core.presets import SCENARIO_METADATA
    
    results = {}
    all_passed = True
    
    for sc_name in PRESETS.keys():
        cfg = get_preset_config(sc_name)
        res = twin.evaluate(cfg)
        best_mod = res['best']
        expected = SCENARIO_METADATA.get(sc_name, {}).get('expected_winner')
        
        # Get score of the best modulation
        best_score = 0
        current_score = 0
        for r in res['ranking']:
            if r['mod'] == best_mod:
                best_score = r['score']
            if r['mod'] == cfg.modulation:
                current_score = r['score']
                
        match = (best_mod == expected)
        if not match:
            all_passed = False
            
        print(f"Scenario: {sc_name:<18} | Preset Mod: {cfg.modulation:<8} | Winner: {best_mod:<8} (Expected: {str(expected):<8}) | Best Score: {best_score:>2} PTS | Match: {'PASS' if match else 'FAIL'}")
        results[sc_name] = {'winner': best_mod, 'expected': expected, 'best_score': best_score, 'match': match}
        
    print("\nTest 1 Result:", "ALL PASSED" if all_passed else "SOME FAILED")
    return all_passed

def test_randomized_scenarios():
    print("\n" + "=" * 80)
    print("TEST 2: RANDOMIZED SCENARIOS DIVERSITY (CHECKING FOR FSK BIAS)")
    print("=" * 80)
    twin = DigitalTwin(fs=1000000)
    
    # Run 5 randomizations per scenario
    winners_count = {}
    for sc_name in ['deep_space', 'urban_cellular', 'leo_doppler', 'iot_tag', 'fm_broadcast']:
        print(f"\n--- Scenario: {sc_name} (5 random draws) ---")
        for i in range(5):
            cfg = randomize_scenario(sc_name, current_modulation=get_preset_config(sc_name).modulation)
            res = twin.evaluate(cfg)
            best_mod = res['best']
            winners_count[best_mod] = winners_count.get(best_mod, 0) + 1
            best_score = next(r['score'] for r in res['ranking'] if r['mod'] == best_mod)
            print(f"  Draw {i+1}: Best = {best_mod:<8} (Score: {best_score} PTS, SNR: {cfg.snr_db:.1f} dB, Doppler: {cfg.doppler_hz:.1f} Hz, Profile: {cfg.profile})")
            
    print("\nOverall Winners Distribution across 25 random draws:")
    for mod, count in sorted(winners_count.items(), key=lambda x: -x[1]):
        print(f"  {mod:<10}: {count} times ({count*4}%)")
        
    fsk_pct = (winners_count.get('FSK', 0) / 25.0) * 100
    print(f"FSK occurrence: {fsk_pct:.1f}% (Healthy dynamic range, not 100%)")
    return fsk_pct < 40

def test_live_frame_vs_twin_fidelity():
    print("\n" + "=" * 80)
    print("TEST 3: LIVE FRAME MEASURED SCORE VS TWIN PREDICTED SCORE")
    print("=" * 80)
    fs = 1000000
    modulator = Modulator(fs=fs)
    channel = ChannelModel(fs=fs, seed=123)
    receiver = Receiver(fs=fs)
    twin = DigitalTwin(fs=fs)
    
    test_cases = [
        ('deep_space', 'BPSK'),
        ('urban_cellular', 'QPSK'),
        ('leo_doppler', 'FSK'),
        ('iot_tag', 'ASK'),
        ('fm_broadcast', 'FM')
    ]
    
    all_fidelity_ok = True
    for sc_name, mod in test_cases:
        cfg = get_preset_config(sc_name)
        cfg.modulation = mod
        plan = derive_link_plan(cfg)
        
        # 1. Twin prediction
        twin_res = twin.evaluate(cfg)
        twin_entry = next((r for r in twin_res['ranking'] if r['mod'] == mod), None)
        twin_score = twin_entry['score'] if twin_entry else 0
        
        # 2. Live frame generation & reception
        rolling = RollingMetrics()
        frame_scores = []
        for f_idx in range(5):
            if plan.is_digital:
                tx_frame = modulator.generate_digital_frame(cfg)
                rx_iq, _, _ = channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
                rx_res = receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
                rolling.update_digital(1, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
                m = MetricCalculator.compute_all_metrics(plan, cfg, rx_res, rolling, tx_frame.iq)
            else:
                tx_iq, msg, _ = modulator.generate_analog_signal(cfg, duration=0.04)
                rx_iq, _, _ = channel.apply(tx_iq, cfg)
                rx_res = receiver.demodulate_analog_signal(rx_iq, msg, cfg)
                rolling.update_analog(1, rx_res['output_snr_db'])
                m = MetricCalculator.compute_all_metrics(plan, cfg, rx_res, rolling, tx_iq)
                
            score_res = Scorer.evaluate(plan, cfg, m)
            frame_scores.append(score_res['total'])
            
        avg_live_score = int(round(np.mean(frame_scores[-3:])))
        diff = abs(avg_live_score - twin_score)
        ok = (diff <= 6)
        if not ok:
            all_fidelity_ok = False
            
        print(f"Modulation: {mod:<8} | Scenario: {sc_name:<18} | Twin Score: {twin_score:>2} PTS | Live Score: {avg_live_score:>2} PTS | Delta: {diff:>2} pts | {'PASS' if ok else 'CHECK'}")
        
    print("\nTest 3 Result:", "ALL PASSED (High Twin Fidelity)" if all_fidelity_ok else "CHECK DISCREPANCIES")
    return all_fidelity_ok

def test_fdia_detection_and_mitigation():
    print("\n" + "=" * 80)
    print("TEST 4: FDIA ATTACK DETECTION & MITIGATION TELEMETRY")
    print("=" * 80)
    fs = 1000000
    modulator = Modulator(fs=fs)
    channel = ChannelModel(fs=fs, seed=42)
    receiver = Receiver(fs=fs)
    
    # Case A: Attack on BPSK (vulnerable)
    cfg_bpsk = get_preset_config('deep_space')
    cfg_bpsk.modulation = 'BPSK'
    cfg_bpsk.fdia_active = True
    plan_bpsk = derive_link_plan(cfg_bpsk)
    tx_frame = modulator.generate_digital_frame(cfg_bpsk)
    rx_iq, _, _ = channel.apply(tx_frame.iq, cfg_bpsk, sps=tx_frame.sps)
    rx_res_bpsk = receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg_bpsk)
    rolling = RollingMetrics()
    rolling.update_digital(1, rx_res_bpsk['bit_errors'], rx_res_bpsk['bits_tested'], cfg_bpsk.packet_bits, rx_res_bpsk['evm_rms'])
    m_bpsk = MetricCalculator.compute_all_metrics(plan_bpsk, cfg_bpsk, rx_res_bpsk, rolling, tx_frame.iq)
    
    print(f"Attack on BPSK : detected={m_bpsk.get('fdia_detected')} | mitigated={m_bpsk.get('fdia_mitigated')} | trust={m_bpsk.get('trust_score')}%")
    assert m_bpsk.get('fdia_detected') == True, "BPSK failed to detect attack"
    assert m_bpsk.get('fdia_mitigated') == False, "BPSK should NOT be mitigated"
    assert m_bpsk.get('trust_score') < 50, "BPSK trust score should collapse"
    
    # Case B: Attack on FSK (mitigated)
    cfg_fsk = get_preset_config('fdia_attack')
    cfg_fsk.modulation = 'FSK'
    cfg_fsk.fdia_active = True
    plan_fsk = derive_link_plan(cfg_fsk)
    tx_fsk = modulator.generate_digital_frame(cfg_fsk)
    rx_iq_fsk, _, _ = channel.apply(tx_fsk.iq, cfg_fsk, sps=tx_fsk.sps)
    rx_res_fsk = receiver.demodulate_digital_frame(rx_iq_fsk, tx_fsk, cfg_fsk)
    rolling_fsk = RollingMetrics()
    rolling_fsk.update_digital(1, rx_res_fsk['bit_errors'], rx_res_fsk['bits_tested'], cfg_fsk.packet_bits, rx_res_fsk['evm_rms'])
    m_fsk = MetricCalculator.compute_all_metrics(plan_fsk, cfg_fsk, rx_res_fsk, rolling_fsk, tx_fsk.iq)
    
    print(f"Attack on FSK  : detected={m_fsk.get('fdia_detected')} | mitigated={m_fsk.get('fdia_mitigated')} | trust={m_fsk.get('trust_score')}%")
    assert m_fsk.get('fdia_detected') == True, "FSK failed to detect attack"
    assert m_fsk.get('fdia_mitigated') == True, "FSK should be mitigated"
    assert m_fsk.get('trust_score') >= 80, "FSK trust score should remain high"
    
    # Case C: Attack CLEARED on BPSK
    cfg_bpsk.fdia_active = False
    tx_clean = modulator.generate_digital_frame(cfg_bpsk)
    rx_iq_clean, _, _ = channel.apply(tx_clean.iq, cfg_bpsk, sps=tx_clean.sps)
    rx_res_clean = receiver.demodulate_digital_frame(rx_iq_clean, tx_clean, cfg_bpsk)
    rolling_clean = RollingMetrics()
    rolling_clean.update_digital(1, rx_res_clean['bit_errors'], rx_res_clean['bits_tested'], cfg_bpsk.packet_bits, rx_res_clean['evm_rms'])
    m_clean = MetricCalculator.compute_all_metrics(plan_bpsk, cfg_bpsk, rx_res_clean, rolling_clean, tx_clean.iq)
    
    print(f"Attack CLEARED : detected={m_clean.get('fdia_detected')} | mitigated={m_clean.get('fdia_mitigated')} | trust={m_clean.get('trust_score')}%")
    assert m_clean.get('fdia_detected') == False, "Clean link should NOT detect attack"
    assert m_clean.get('trust_score') == 100, "Clean link trust should be 100%"
    
    print("\nTest 4 Result: ALL PASSED (FDIA Detection & Mitigation Verified)")
    return True

if __name__ == '__main__':
    t1 = test_all_scenarios()
    t2 = test_randomized_scenarios()
    t3 = test_live_frame_vs_twin_fidelity()
    t4 = test_fdia_detection_and_mitigation()
    
    print("\n" + "=" * 80)
    print(f"FINAL SUITE RESULT: {'ALL SYSTEMS OPERATIONAL (100% PASS)' if (t1 and t2 and t3 and t4) else 'FAILURES DETECTED'}")
    print("=" * 80)
