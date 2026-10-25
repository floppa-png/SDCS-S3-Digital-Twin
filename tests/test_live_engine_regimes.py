import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twin_core.engine import Engine
from twin_core.presets import PRESETS, EXPECTED_WINNERS, get_preset_config
from twin_core.config import derive_link_plan
from twin_core.metrics import MetricCalculator
from twin_core.scoring import Scorer

def test_live_engine_regimes():
    print("==================================================")
    print("   RUNNING LIVE ENGINE CLOSED-LOOP VERIFICATION   ")
    print("==================================================")

    engine = Engine()
    # Test without starting background threads so we can step frame-by-frame
    engine.running = True

    # 1. Test deep_space preset and apply_best()
    print("\n--- Test 1: Deep Space Scenario (QPSK drift -> BPSK recommendation) ---")
    engine.set_preset('deep_space')
    # Force suboptimal QPSK to simulate channel drift / human selection
    engine.set_modulation('QPSK')
    assert engine.config.modulation == 'QPSK', f"Expected QPSK, got {engine.config.modulation}"
    
    # Run 5 frames on suboptimal QPSK under phase noise
    scores_sub = []
    bers_sub = []
    for _ in range(5):
        # generate frame
        cfg = engine.config
        plan = engine.twin.evaluate(cfg)
        tx_frame = engine.modulator.generate_digital_frame(cfg)
        rx_iq, _, _ = engine.channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
        rx_res = engine.receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
        engine.rolling.update_digital(engine.cfg_version, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
        metrics = MetricCalculator.compute_all_metrics(derive_link_plan(cfg), cfg, rx_res, engine.rolling, tx_frame.iq)
        score_res = Scorer.evaluate(derive_link_plan(cfg), cfg, metrics)
        scores_sub.append(score_res['total'])
        bers_sub.append(metrics['ber'])

    mean_sub_score = sum(scores_sub) / len(scores_sub)
    mean_sub_ber = sum(bers_sub) / len(bers_sub)
    print(f"Suboptimal QPSK: Mean Score = {mean_sub_score:.1f}, Mean BER = {mean_sub_ber:.4f}")

    # Evaluate twin
    twin_res = engine.twin.evaluate(engine.config)
    engine.last_twin_payload = twin_res
    print(f"Twin Recommendation: {twin_res['best']} (Predicted Score: {twin_res['ranking'][0]['score']})")
    assert twin_res['best'] == 'BPSK', f"Expected BPSK recommendation, got {twin_res['best']}"

    # Apply Twin Recommendation
    ok, apply_data = engine.apply_best()
    assert ok, f"apply_best failed: {apply_data}"
    assert engine.config.modulation == 'BPSK', f"Modulation not switched to BPSK: {engine.config.modulation}"
    print(f"Applied Twin: {apply_data['from']} -> {apply_data['to']} (Target: {apply_data['target_score']} pts)")

    # Run 5 frames on optimal BPSK
    scores_opt = []
    bers_opt = []
    for _ in range(5):
        cfg = engine.config
        tx_frame = engine.modulator.generate_digital_frame(cfg)
        rx_iq, _, _ = engine.channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
        rx_res = engine.receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
        engine.rolling.update_digital(engine.cfg_version, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
        metrics = MetricCalculator.compute_all_metrics(derive_link_plan(cfg), cfg, rx_res, engine.rolling, tx_frame.iq)
        score_res = Scorer.evaluate(derive_link_plan(cfg), cfg, metrics)
        scores_opt.append(score_res['total'])
        bers_opt.append(metrics['ber'])

    mean_opt_score = sum(scores_opt) / len(scores_opt)
    mean_opt_ber = sum(bers_opt) / len(bers_opt)
    print(f"Optimal BPSK: Mean Score = {mean_opt_score:.1f}, Mean BER = {mean_opt_ber:.4f}")
    assert mean_opt_score >= mean_sub_score, f"Score did not increase! Sub: {mean_sub_score}, Opt: {mean_opt_score}"
    assert mean_opt_ber <= 0.01, f"BER too high for optimal BPSK: {mean_opt_ber}"
    print(">>> Deep Space Recommendation PASSED: Score increased dramatically with low BER!")

    # 2. Test LEO Doppler scenario (3000 Hz CFO, 250 Hz Doppler)
    print("\n--- Test 2: LEO Doppler Scenario ---")
    engine.set_preset('leo_doppler')
    engine.set_modulation('QPSK')
    assert engine.config.modulation == 'QPSK', f"Expected QPSK initial, got {engine.config.modulation}"
    twin_res = engine.twin.evaluate(engine.config)
    engine.last_twin_payload = twin_res
    assert twin_res['best'] == 'FSK', f"Expected FSK recommendation for LEO, got {twin_res['best']}"
    ok, _ = engine.apply_best()
    assert ok and engine.config.modulation == 'FSK'
    
    # Run 5 frames on FSK
    fsk_scores = []
    for _ in range(5):
        cfg = engine.config
        tx_frame = engine.modulator.generate_digital_frame(cfg)
        rx_iq, _, _ = engine.channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
        rx_res = engine.receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
        engine.rolling.update_digital(engine.cfg_version, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
        metrics = MetricCalculator.compute_all_metrics(derive_link_plan(cfg), cfg, rx_res, engine.rolling, tx_frame.iq)
        score_res = Scorer.evaluate(derive_link_plan(cfg), cfg, metrics)
        fsk_scores.append(score_res['total'])

    mean_fsk_score = sum(fsk_scores) / len(fsk_scores)
    print(f"Optimal FSK under 3 kHz CFO: Mean Score = {mean_fsk_score:.1f}")
    assert mean_fsk_score >= 45, f"FSK score too low under Doppler/CFO: {mean_fsk_score}"
    print(">>> LEO Doppler FSK PASSED!")

    # 3. Test Analog Modulation Auto-switch
    print("\n--- Test 3: Source Type Auto-switching ---")
    engine.active_scenario = None
    engine.set_modulation('FM')
    assert engine.config.source_type == 'analog', f"Source type not switched to analog for FM: {engine.config.source_type}"
    engine.set_modulation('QPSK')
    assert engine.config.source_type == 'digital', f"Source type not switched to digital for QPSK: {engine.config.source_type}"
    print(">>> Source Type Auto-switching PASSED!")

    print("\n==================================================")
    print("   ALL LIVE ENGINE SCENARIOS PASSED VERIFICATION  ")
    print("==================================================")

if __name__ == '__main__':
    test_live_engine_regimes()
