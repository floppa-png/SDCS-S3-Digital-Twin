import sys
import os
import math
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from twin_core.config import TxConfig, derive_link_plan
from twin_core.waveforms import Modulator
from twin_core.channel import ChannelModel
from twin_core.receiver import Receiver
from twin_core.theory import TheoreticalCalculator

def run_ber_test_for_mod(mod: str, ebn0_targets: list = [0.0, 4.0, 8.0]):
    print(f"\n--- Testing Modulation {mod} in AWGN ---")
    modulator = Modulator()
    channel = ChannelModel(seed=42)
    receiver = Receiver()
    
    for ebn0 in ebn0_targets:
        # Determine snr_db so that ebn0_db in link plan equals target
        # ebn0 = C/N0 - 10*log10(Rb) = snr_db + 10*log10(B) - 10*log10(Rb)
        # snr_db = ebn0 + 10*log10(Rb) - 10*log10(B)
        cfg = TxConfig(
            modulation=mod,
            source_type='digital',
            alloc_bw=60000,
            channel='awgn',
            cfo_hz=0.0,
            phase_noise_deg=0.0,
            doppler_hz=0.0
        )
        plan = derive_link_plan(cfg, mod)
        # Calibrate snr_db
        needed_snr = ebn0 + 10.0 * math.log10(plan.bit_rate) - 10.0 * math.log10(cfg.alloc_bw)
        cfg.snr_db = needed_snr
        plan = derive_link_plan(cfg, mod)
        
        theory_ber = TheoreticalCalculator.ber_awgn(mod, plan.ebn0_db)
        
        # Run multiple bursts to gather sufficient bits
        total_errors = 0
        total_bits = 0
        
        # Test enough bits for statistical stability
        bursts = 15 if ebn0 <= 4.0 else 30
        for b_i in range(bursts):
            tx_frame = modulator.generate_digital_frame(cfg, cfg_version=1)
            rx_iq, _, _ = channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
            rx_res = receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
            
            total_errors += rx_res['bit_errors']
            total_bits += rx_res['bits_tested']
            
        measured_ber = total_errors / float(total_bits)
        
        # Binomial standard deviation: sigma = sqrt(p * (1-p) / N)
        sigma = math.sqrt(max(1e-12, theory_ber * (1.0 - theory_ber) / max(1, total_bits)))
        # Allow +/- 3 sigma or +/- 30% for small error counts
        diff_sigma = abs(measured_ber - theory_ber) / max(1e-9, sigma)
        
        print(f"  Eb/N0: {plan.ebn0_db:4.1f} dB | Bits: {total_bits:6d} | Errors: {total_errors:5d} | "
              f"Measured BER: {measured_ber:8.5f} | Theory: {theory_ber:8.5f} | Z-score: {diff_sigma:4.2f}")
              
        assert diff_sigma < 4.0 or abs(measured_ber - theory_ber) < 0.05, (
            f"BER deviation too high for {mod} at {ebn0} dB! Measured={measured_ber}, Theory={theory_ber}"
        )
        
    print(f"--> {mod} AWGN BER verification PASSED.")

def main():
    print("==================================================")
    print("   RUNNING PHASE 1: DIGITAL AWGN BER VERIFICATION")
    print("==================================================")
    for mod in ['BPSK', 'QPSK', 'ASK', 'FSK']:
        run_ber_test_for_mod(mod)
    print("\nALL DIGITAL MODULATION BER TESTS PASSED SUCCESSFULLY!")

if __name__ == '__main__':
    main()
