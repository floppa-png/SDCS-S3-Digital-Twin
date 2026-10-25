import zmq
import numpy as np
import struct
import time
import math

def generate_synthetic_am_dsb_tc(fs, duration, fc, fm, mod_index):
    t = np.arange(0, duration, 1/fs)
    msg = np.cos(2 * np.pi * fm * t)
    tx_signal = (1 + mod_index * msg) * np.cos(2 * np.pi * fc * t)
    # Add noise for SNR=20dB
    sig_power = np.mean(tx_signal**2)
    noise_power = sig_power / (10**(20/10))
    noise = np.random.normal(0, np.sqrt(noise_power), len(t))
    return tx_signal + noise

def main():
    print("============================================================")
    print("   Digital Twin AI — Synthetic ZMQ Transmitter (Mocks GR)")
    print("============================================================")
    
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    
    # In ZeroMQ, one side binds, the other connects. 
    # Since our receiver BINDs to 5555, the transmitter must CONNECT.
    # (GNU Radio ZMQ PUSH Sink can act as connect or bind, usually we set GR to Connect if Python Binds)
    socket.connect("tcp://127.0.0.1:5555")
    
    print("Connected to tcp://127.0.0.1:5555")
    print("Streaming synthetic AM-DSB-TC signals (simulating GNU Radio)...")
    
    fs = 100000
    duration = 0.1 # 10000 samples
    
    frame_count = 0
    try:
        while True:
            # Generate a new random AM_DSBTC frame
            fm = np.random.uniform(500, 2000)
            fc = 10000
            signal = generate_synthetic_am_dsb_tc(fs, duration, fc, fm, 0.8)
            
            # Convert to float32 bytes exactly as GNU Radio does
            # Ensure it's 32-bit float
            signal = signal.astype(np.float32)
            raw_bytes = signal.tobytes()
            
            socket.send(raw_bytes)
            frame_count += 1
            print(f"Sent Frame {frame_count:04d} (AM_DSBTC)")
            
            # Simulate real-time streaming
            time.sleep(duration)
            
    except KeyboardInterrupt:
        print("\nTransmission stopped.")

if __name__ == "__main__":
    main()
