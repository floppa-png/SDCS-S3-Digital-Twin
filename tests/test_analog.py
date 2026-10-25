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

def test_analog_demodulation():
    print("==================================================")
    print("   RUNNING PHASE 1: ANALOG DEMODULATION TESTS")
    print("==================================================")
    modulator = Modulator()
    channel = ChannelModel(seed=42)
    receiver = Receiver()
    
    # 1. AM DSB-SC Test: SNR_out should approximately equal gamma
    cfg_sc = TxConfig(
        modulation='AM_DSBSC',
        source_type='analog',
        msg_bw=5000,
        alloc_bw=12000,
        snr_db=15.0,
        channel='awgn',
        cfo_hz=0.0
    )
    plan_sc = derive_link_plan(cfg_sc, 'AM_DSBSC')
    tx_iq, msg, _ = modulator.generate_analog_signal(cfg_sc, duration=0.1)
    rx_iq, _, _ = channel.apply(tx_iq, cfg_sc)
    res_sc = receiver.demodulate_analog_signal(rx_iq, msg, cfg_sc)
    
    theory_sc = TheoreticalCalculator.calculate_analog_snr('AM_DSBSC', plan_sc, cfg_sc)
    print(f"AM_DSBSC -> Measured SNR_o: {res_sc['output_snr_db']:.2f} dB | Theory (gamma): {theory_sc:.2f} dB")
    assert abs(res_sc['output_snr_db'] - theory_sc) < 2.0, "AM_DSBSC SNR mismatch!"
    
    # 2. AM DSB-TC Test
    cfg_tc = TxConfig(
        modulation='AM_DSBTC',
        source_type='analog',
        msg_bw=5000,
        alloc_bw=12000,
        snr_db=25.0,
        am_index=0.8,
        channel='awgn',
        cfo_hz=0.0
    )
    plan_tc = derive_link_plan(cfg_tc, 'AM_DSBTC')
    tx_iq, msg, _ = modulator.generate_analog_signal(cfg_tc, duration=0.1)
    rx_iq, _, _ = channel.apply(tx_iq, cfg_tc)
    res_tc = receiver.demodulate_analog_signal(rx_iq, msg, cfg_tc)
    
    theory_tc = TheoreticalCalculator.calculate_analog_snr('AM_DSBTC', plan_tc, cfg_tc)
    print(f"AM_DSBTC -> Measured SNR_o: {res_tc['output_snr_db']:.2f} dB | Theory: {theory_tc:.2f} dB")
    assert abs(res_tc['output_snr_db'] - theory_tc) < 3.0, "AM_DSBTC SNR mismatch!"
    
    # 3. FM Test (above threshold)
    cfg_fm = TxConfig(
        modulation='FM',
        source_type='analog',
        msg_bw=5000,
        alloc_bw=60000,
        snr_db=25.0,
        fm_beta=4.0,
        channel='awgn',
        cfo_hz=0.0
    )
    plan_fm = derive_link_plan(cfg_fm, 'FM')
    tx_iq, msg, _ = modulator.generate_analog_signal(cfg_fm, duration=0.1)
    rx_iq, _, _ = channel.apply(tx_iq, cfg_fm)
    res_fm = receiver.demodulate_analog_signal(rx_iq, msg, cfg_fm)
    
    theory_fm = TheoreticalCalculator.calculate_analog_snr('FM', plan_fm, cfg_fm)
    print(f"FM       -> Measured SNR_o: {res_fm['output_snr_db']:.2f} dB | Theory: {theory_fm:.2f} dB")
    assert abs(res_fm['output_snr_db'] - theory_fm) < 3.5, "FM SNR mismatch!"
    
    print("\nALL ANALOG DEMODULATION TESTS PASSED!")

def test_frame_sync_with_cfo():
    print("\n==================================================")
    print("   TESTING FRAME SYNC WITH CARRIER FREQ OFFSET (CFO)")
    print("==================================================")
    modulator = Modulator()
    channel = ChannelModel(seed=42)
    receiver = Receiver()
    
    cfg = TxConfig(
        modulation='BPSK',
        source_type='digital',
        alloc_bw=60000,
        snr_db=20.0,
        cfo_hz=2500.0,  # 2.5 kHz CFO
        channel='awgn'
    )
    tx_frame = modulator.generate_digital_frame(cfg, cfg_version=1)
    rx_iq, _, _ = channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
    rx_res = receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
    
    print(f"Injected CFO: 2500 Hz | Estimated CFO: {rx_res['cfo_est_hz']:.1f} Hz")
    print(f"Header Valid: {rx_res['header_valid']} | Frame ID: {rx_res['frame_id']}")
    print(f"Bit Errors: {rx_res['bit_errors']} / {rx_res['bits_tested']} | BER: {rx_res['ber']}")
    
    assert rx_res['header_valid'] == True, "Frame header CRC failed under 2.5 kHz CFO!"
    assert rx_res['ber'] < 0.01, f"BPSK BER too high under CFO: {rx_res['ber']}"
    assert abs(rx_res['cfo_est_hz'] - 2500.0) < 300.0, "CFO estimation error too large!"
    print("FRAME SYNC UNDER CFO TEST PASSED!")

if __name__ == '__main__':
    test_analog_demodulation()
    test_frame_sync_with_cfo()
