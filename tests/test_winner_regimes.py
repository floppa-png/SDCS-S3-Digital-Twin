import sys
import os
import time

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twin_core.presets import PRESETS, EXPECTED_WINNERS, get_preset_config
from twin_core.twin import DigitalTwin

def test_winner_regimes():
    print("==================================================")
    print("   RUNNING PHASE 2: WINNER REGIMES VERIFICATION   ")
    print("==================================================")
    
    twin = DigitalTwin()
    all_passed = True
    
    for preset_name, expected_winner in EXPECTED_WINNERS.items():
        cfg = get_preset_config(preset_name)
        
        t0 = time.perf_counter()
        res = twin.evaluate(cfg)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        
        ranking = res['ranking']
        actual_winner = res['best']
        top_score = ranking[0]['score']
        second_score = ranking[1]['score'] if len(ranking) > 1 else 0
        
        status = "PASSED" if actual_winner == expected_winner else "FAILED"
        print(f"Preset: {preset_name:<18} | Expected: {expected_winner:<9} | Actual: {actual_winner:<9} "
              f"| Scores: #1={top_score} vs #2={second_score} | Time: {dt_ms:.1f}ms | {status}")
              
        if actual_winner != expected_winner:
            all_passed = False
            print(f"   --> Full Ranking for {preset_name}:")
            for rank_idx, r in enumerate(ranking[:4]):
                print(f"       #{rank_idx+1}: {r['mod']:<9} (Score: {r['score']}, Rel: {r['subs']['rel']:.2f}, Rate: {r['subs']['rate']:.2f}, Margin: {r.get('metrics', {}).get('link_margin_db', 0):.1f}dB)")
                
        assert dt_ms < 1000.0, f"Preset {preset_name} evaluation exceeded 1s: {dt_ms:.1f}ms"
        
    assert all_passed, "Not all presets produced the expected winner!"
    print("\nALL 8 PRESET WINNER REGIMES VERIFIED SUCCESSFULLY!")

if __name__ == '__main__':
    test_winner_regimes()
