import zmq
import numpy as np
import time
import sys
import urllib.request
import json

def add_noise(sig, snr_db=20):
    # Convert SNR from dB to linear scale
    snr_linear = 10 ** (snr_db / 10)
    sig_power = np.mean(sig**2)
    noise_power = sig_power / snr_linear
    noise = np.random.normal(0, np.sqrt(noise_power), len(sig))
    return (sig + noise).astype(np.float32)

def generate_am(fs, duration, bw, snr):
    t = np.arange(0, duration, 1/fs)
    msg = np.cos(2 * np.pi * (bw/2) * t)
    sig = (1 + 0.8 * msg) * np.cos(2 * np.pi * 10000 * t)
    return add_noise(sig * 0.4, snr)

def generate_fm(fs, duration, bw, snr):
    t = np.arange(0, duration, 1/fs)
    msg = np.cumsum(np.cos(2 * np.pi * (bw/2) * t)) / fs
    sig = np.cos(2 * np.pi * 10000 * t + 2 * np.pi * bw * msg)
    return add_noise(sig * 0.5, snr)

def generate_ask(fs, duration, bw, snr):
    t = np.arange(0, duration, 1/fs)
    data = (np.sign(np.cos(2 * np.pi * (bw/2) * t)) > 0).astype(float)
    sig = data * np.cos(2 * np.pi * 10000 * t)
    return add_noise(sig * 0.5, snr)

def generate_fsk(fs, duration, bw, snr):
    t = np.arange(0, duration, 1/fs)
    data = np.sign(np.cos(2 * np.pi * (bw/2) * t))
    inst_freq = 10000 + (bw/2) * data
    phase = np.cumsum(inst_freq) / fs
    sig = np.cos(2 * np.pi * phase)
    return add_noise(sig * 0.5, snr)

def generate_bpsk(fs, duration, bw, snr):
    t = np.arange(0, duration, 1/fs)
    data = np.sign(np.cos(2 * np.pi * (bw/2) * t))
    sig = data * np.cos(2 * np.pi * 10000 * t)
    return add_noise(sig * 0.5, snr)

def generate_qpsk(fs, duration, bw, snr):
    t = np.arange(0, duration, 1/fs)
    i_sym = np.sign(np.cos(2 * np.pi * (bw/2) * t))
    q_sym = np.sign(np.sin(2 * np.pi * (bw/2) * t))
    sig = (i_sym * np.cos(2 * np.pi * 10000 * t) - q_sym * np.sin(2 * np.pi * 10000 * t)) / np.sqrt(2)
    return add_noise(sig * 0.5, snr)

def generate_fdi(fs, duration, bw, snr):
    # FDI Attack: High Power White Noise
    t = np.arange(0, duration, 1/fs)
    sig = np.random.normal(0, 0.5, len(t)) + 0.8 * np.cos(2 * np.pi * 50000 * t)
    return np.clip(sig, -0.99, 0.99).astype(np.float32)

def main():
    print("============================================================")
    print("   Digital Twin AI — Dynamic Scenario Simulator")
    print("============================================================")
    
    hitl_mode = "--hitl" in sys.argv
    
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    
    if hitl_mode:
        print("[HARDWARE MODE] Pushing to GNU Radio Pluto SDR Sink on tcp://127.0.0.1:5556")
        socket.bind("tcp://127.0.0.1:5556")
    else:
        print("[SOFTWARE MODE] Connecting directly to Dashboard on tcp://127.0.0.1:5555")
        socket.connect("tcp://127.0.0.1:5555")
    
    fs = 100000
    chunk = 0.1
    
    funcs = {
        "AM_DSBSC": generate_am,
        "AM_DSBTC": generate_am,
        "FM": generate_fm,
        "ASK": generate_ask,
        "FSK": generate_fsk,
        "BPSK": generate_bpsk,
        "QPSK": generate_qpsk,
        "FDI": generate_fdi
    }
    
    print("Streaming dynamic realistic RF Scenarios (Controlled by Web Dashboard)...")
    try:
        last_config = None
        while True:
            try:
                req = urllib.request.urlopen('http://127.0.0.1:5000/api/tx_config')
                config = json.loads(req.read().decode())
            except Exception as e:
                config = {"modulation": "BPSK", "snr": 20, "bandwidth": 1000, "is_fdi": False}
                
            mod = config.get("modulation") or "BPSK"
            
            raw_bw = config.get("bandwidth")
            bw = int(raw_bw) if raw_bw is not None else 1000
            
            raw_snr = config.get("snr")
            snr = int(raw_snr) if raw_snr is not None else 20
            
            if config.get("is_fdi", False):
                mod = "FDI"
                
            current_conf = f"{mod}_{bw}_{snr}"
            if current_conf != last_config:
                print(f"\n---> Transmitting: {mod} | BW: {bw}Hz | SNR: {snr}dB")
                last_config = current_conf
                
            func = funcs.get(mod, generate_bpsk)
            signal = func(fs, chunk, bw, snr)
            
            if hitl_mode:
                signal = (signal + 0j).astype(np.complex64)
            else:
                signal = signal.astype(np.float32)
                
            socket.send(signal.tobytes())
            time.sleep(chunk)
    except KeyboardInterrupt:
        print("\nScenario Simulator Stopped.")

if __name__ == "__main__":
    main()
