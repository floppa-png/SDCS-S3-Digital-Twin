import os
import sys

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from twin_core.config import TxConfig, DIGITAL_MODS, ANALOG_MODS
from twin_core.presets import PRESETS, get_preset_config, randomize_scenario, SCENARIO_METADATA
from twin_core.twin import DigitalTwin
from twin_core.engine import Engine

def test_domain_applicability_and_winners():
    print("=" * 80)
    print("VERIFYING DOMAIN SEGREGATION ACROSS ALL 9 PRESETS")
    print("=" * 80)
    twin = DigitalTwin(fs=1000000)
    
    all_ok = True
    for sc_name, sc_data in PRESETS.items():
        meta = SCENARIO_METADATA[sc_name]
        cat = meta['category']
        cfg = get_preset_config(sc_name)
        res = twin.evaluate(cfg, scenario_preset=sc_name)
        winner = res['best']
        
        # Check winner domain
        if cat == 'analog':
            winner_ok = winner in ANALOG_MODS
            expected_applicable = ANALOG_MODS
            expected_inapplicable = DIGITAL_MODS
        else:
            winner_ok = winner in DIGITAL_MODS
            expected_applicable = DIGITAL_MODS
            expected_inapplicable = ANALOG_MODS
            
        if not winner_ok:
            all_ok = False
            print(f"FAILED: Scenario {sc_name} ({cat}) picked winner {winner} from wrong domain!")
            
        # Check ranking items
        for r in res['ranking']:
            mod = r['mod']
            if mod in expected_applicable:
                if not r['applicable']:
                    all_ok = False
                    print(f"FAILED: {sc_name} -> {mod} should be applicable=True")
                if r['score'] <= 0:
                    all_ok = False
                    print(f"FAILED: {sc_name} -> {mod} applicable score is 0")
            else:
                if r['applicable']:
                    all_ok = False
                    print(f"FAILED: {sc_name} -> {mod} should be applicable=False")
                if r['score'] != 0 or r['grade'] != 'N/A':
                    all_ok = False
                    print(f"FAILED: {sc_name} -> {mod} inapplicable should have score=0, grade='N/A'")
                    
        app_list = [r['mod'] for r in res['ranking'] if r['applicable']]
        inapp_list = [r['mod'] for r in res['ranking'] if not r['applicable']]
        print(f"Scenario: {sc_name:<18} ({cat:<7}) | Winner: {winner:<8} | Applicable: {app_list} | Inapplicable: {len(inapp_list)} mods")
        
    print("\nDomain Applicability Test:", "ALL PASSED" if all_ok else "FAILED")
    assert all_ok

def test_engine_cross_domain_protection():
    print("\n" + "=" * 80)
    print("VERIFYING ENGINE CROSS-DOMAIN REJECTION & RANDOMIZATION")
    print("=" * 80)
    engine = Engine(fs=1000000)
    
    # 1. Analog scenario should reject digital modulation selection
    engine.set_preset('am_broadcast')
    assert engine.config.modulation == 'AM_DSBTC'
    ok, msg = engine.set_modulation('ASK')
    assert not ok, "Engine must reject digital mod 'ASK' in analog scenario 'am_broadcast'"
    assert engine.config.modulation == 'AM_DSBTC'
    print("PASS: Rejected digital 'ASK' in analog 'am_broadcast'")
    
    # Can switch to valid analog mod in analog scenario
    ok, msg = engine.set_modulation('AM_DSBSC')
    assert ok
    assert engine.config.modulation == 'AM_DSBSC'
    print("PASS: Allowed analog 'AM_DSBSC' in analog 'am_broadcast'")
    
    # 2. Digital scenario should reject analog modulation selection
    engine.set_preset('deep_space')
    assert engine.config.modulation == 'BPSK'
    ok, msg = engine.set_modulation('FM')
    assert not ok, "Engine must reject analog mod 'FM' in digital scenario 'deep_space'"
    assert engine.config.modulation == 'BPSK'
    print("PASS: Rejected analog 'FM' in digital 'deep_space'")
    
    # 3. Randomize scenario preserves domain integrity
    for sc in ['am_broadcast', 'fm_broadcast', 'coherent_voice']:
        for _ in range(5):
            rand_cfg = randomize_scenario(sc, current_modulation='ASK')
            assert rand_cfg.modulation in ANALOG_MODS, f"Randomized {sc} modulation crossed domain to {rand_cfg.modulation}"
    print("PASS: randomize_scenario on analog presets rejects digital current_modulation")
    
    for sc in ['deep_space', 'urban_cellular', 'leo_doppler']:
        for _ in range(5):
            rand_cfg = randomize_scenario(sc, current_modulation='FM')
            assert rand_cfg.modulation in DIGITAL_MODS, f"Randomized {sc} modulation crossed domain to {rand_cfg.modulation}"
    print("PASS: randomize_scenario on digital presets rejects analog current_modulation")

if __name__ == '__main__':
    test_domain_applicability_and_winners()
    test_engine_cross_domain_protection()
    print("\n" + "=" * 80)
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)
