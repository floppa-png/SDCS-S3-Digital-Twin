"""Quick validation that the fixes don't break anything and produce expected score ranges."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from twin_core.config import TxConfig, derive_link_plan
from twin_core.scoring import Scorer
from twin_core.theory import TheoreticalCalculator
from twin_core.presets import PRESETS, get_preset_config, SCENARIO_METADATA
from twin_core.twin import DigitalTwin
from twin_core.waveforms import Modulator
from twin_core.channel import ChannelModel
from twin_core.receiver import Receiver
from twin_core.metrics import MetricCalculator, RollingMetrics
import numpy as np

errors = []

# ====================================================================
# TEST 1: Analog scenario twin predictions should be >= 88
# ====================================================================
print("=" * 60)
print("TEST 1: Analog modulation-specific scenario scores (Twin)")
print("=" * 60)
twin = DigitalTwin()
for sc_name in ['fm_broadcast', 'am_broadcast', 'coherent_voice']:
    cfg = get_preset_config(sc_name)
    res = twin.evaluate(cfg, scenario_preset=sc_name)
    expected_mod = SCENARIO_METADATA[sc_name]['expected_winner']
    best = res['best']
    for r in res['ranking']:
        if r['mod'] == expected_mod:
            score = r['score']
            grade = r['grade']
            break
    else:
        score = 0
        grade = 'N/A'
    status = "PASS" if score >= 88 else "FAIL"
    if score < 88:
        errors.append(f"{sc_name}: {expected_mod} score {score} < 88")
    print(f"  {sc_name:20s} | expected={expected_mod:10s} | best={best:10s} | score={score:3d} ({grade}) | {status}")

# ====================================================================
# TEST 2: QPSK measured BER stability under urban_cellular
# ====================================================================
print()
print("=" * 60)
print("TEST 2: QPSK BER stability under urban_cellular (10 frames)")
print("=" * 60)

cfg = get_preset_config('urban_cellular')
cfg.modulation = 'QPSK'
mod = Modulator()
ch = ChannelModel(fs=1000000, seed=None)  # random seed for realistic fading
rx = Receiver()
rolling = RollingMetrics()

bers = []
scores = []
for i in range(10):
    plan = derive_link_plan(cfg)
    tx_frame = mod.generate_digital_frame(cfg)
    rx_iq, _, _ = ch.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
    rx_res = rx.demodulate_digital_frame(rx_iq, tx_frame, cfg)
    rolling.update_digital(1, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
    metrics = MetricCalculator.compute_all_metrics(plan, cfg, rx_res, rolling, tx_frame.iq)
    score_res = Scorer.evaluate(plan, cfg, metrics)
    bers.append(metrics['ber'])
    scores.append(score_res['total'])
    print(f"  Frame {i+1:2d}: BER={metrics['ber']:.5f} | Score={score_res['total']:3d} ({score_res['grade']})")

ber_std = np.std(bers)
score_std = np.std(scores)
ber_mean = np.mean(bers)
score_mean = np.mean(scores)
print(f"\n  BER:   mean={ber_mean:.5f}  std={ber_std:.5f}")
print(f"  Score: mean={score_mean:.1f}  std={score_std:.1f}")

if score_std > 15.0:
    errors.append(f"QPSK score std={score_std:.1f} > 15 (too much fluctuation)")
    print(f"  STATUS: FAIL (score std {score_std:.1f} too high)")
else:
    print(f"  STATUS: PASS (score fluctuation within bounds)")

# ====================================================================
# TEST 3: Digital scenarios still produce correct winners
# ====================================================================
print()
print("=" * 60)
print("TEST 3: Digital scenario expected winners still correct")
print("=" * 60)

for sc_name in ['deep_space', 'urban_cellular', 'leo_doppler', 'iot_tag']:
    cfg = get_preset_config(sc_name)
    res = twin.evaluate(cfg, scenario_preset=sc_name)
    expected = SCENARIO_METADATA[sc_name]['expected_winner']
    best = res['best']
    status = "PASS" if best == expected else "FAIL"
    if best != expected:
        errors.append(f"{sc_name}: expected winner {expected}, got {best}")
    # Find expected mod's score
    exp_score = 0
    for r in res['ranking']:
        if r['mod'] == expected:
            exp_score = r['score']
            break
    print(f"  {sc_name:20s} | expected={expected:6s} | best={best:6s} | score={exp_score:3d} | {status}")

# ====================================================================
# TEST 4: FDIA scenario still recommends FSK
# ====================================================================
print()
print("=" * 60)
print("TEST 4: FDIA scenario still recommends FSK")
print("=" * 60)
cfg = get_preset_config('fdia_attack')
res = twin.evaluate(cfg, scenario_preset='fdia_attack')
best = res['best']
status = "PASS" if best == 'FSK' else "FAIL"
if best != 'FSK':
    errors.append(f"fdia_attack: expected FSK, got {best}")
print(f"  fdia_attack | best={best} | {status}")

# ====================================================================
# TEST 5: Constellation optimality scatter and attack transition
# ====================================================================
print()
print("=" * 60)
print("TEST 5: Constellation fidelity (optimal vs suboptimal) & attack morphing")
print("=" * 60)
from twin_core.equalizer import AdaptiveEqualizer

# 5a. Deep space with optimal BPSK
cfg_ds = get_preset_config('deep_space')
dummy_metrics = {'trust_score': 95.0, 'evm_rms': 4.0}
dummy_rx = {}
pts_optimal = AdaptiveEqualizer.synthesize_constellation('BPSK', cfg_ds, dummy_metrics, dummy_rx, active_scenario='deep_space')
pts_opt_arr = np.array(pts_optimal)
# Check cluster std around +1 and -1
c1 = pts_opt_arr[pts_opt_arr[:, 0] > 0]
sigma_opt = float(np.std(c1[:, 0]))

# 5b. Deep space with suboptimal QPSK
pts_subopt = AdaptiveEqualizer.synthesize_constellation('QPSK', cfg_ds, dummy_metrics, dummy_rx, active_scenario='deep_space')
pts_sub_arr = np.array(pts_subopt)
q1 = pts_sub_arr[(pts_sub_arr[:, 0] > 0) & (pts_sub_arr[:, 1] > 0)]
sigma_sub = float(np.std(q1[:, 0]))

print(f"  Deep Space BPSK (optimal) std:    {sigma_opt:.4f}")
print(f"  Deep Space QPSK (suboptimal) std: {sigma_sub:.4f}")

if sigma_opt > 0.05:
    errors.append(f"Optimal BPSK constellation cluster too wide: std={sigma_opt:.4f} > 0.05")
if sigma_sub < 0.09:
    errors.append(f"Suboptimal QPSK constellation not noisy enough: std={sigma_sub:.4f} < 0.09")

# 5c. Attack transition ramp
AdaptiveEqualizer._current_attack_level = 0.0
AdaptiveEqualizer._last_attack_update_time = 0.0
levels = []
t_sim = 1000.0
for step in range(10):
    t_sim += 0.095
    lvl = AdaptiveEqualizer._update_transition_level(True, t_sim)
    levels.append(round(lvl, 3))
print(f"  Attack transition ramp (0.1s steps): {levels}")
if levels[0] >= 0.99 or levels[-1] <= 0.5:
    errors.append(f"Attack transition did not ramp smoothly: {levels}")
else:
    print(f"  Attack ramp PASS: smoothly ramps across ~0.8s")

# ====================================================================
# TEST 6: EVM stays strictly bounded [0%, 100%]
# ====================================================================
print()
print("=" * 60)
print("TEST 6: EVM bounded range check")
print("=" * 60)
evm_val = rx_res.get('evm_rms', 0.0)
print(f"  Measured QPSK EVM: {evm_val:.2f}%")
if evm_val < 0.0 or evm_val > 100.0:
    errors.append(f"EVM out of bounds: {evm_val:.2f}% (should be 0-100%)")
else:
    print(f"  EVM bounds PASS")

# ====================================================================
# SUMMARY
# ====================================================================
print()
print("=" * 60)
if errors:
    print(f"VALIDATION FAILED: {len(errors)} error(s)")
    for e in errors:
        print(f"  X {e}")
    sys.exit(1)
else:
    print("ALL VALIDATIONS PASSED")
    sys.exit(0)
