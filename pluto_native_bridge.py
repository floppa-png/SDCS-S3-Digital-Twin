#!/usr/bin/env python3
"""
Pluto SDR Native High-Performance HITL Transceiver Bridge
Direct libiio / pyadi-iio implementation replacing fragile GRC subprocess.
Exposes:
- ZeroMQ PUSH socket tcp://127.0.0.1:5555 (streaming complex64 RX IQ to engine)
- ZeroMQ PULL socket tcp://127.0.0.1:5556 (receiving complex64 TX IQ from engine)
- XML-RPC server http://127.0.0.1:8090 (RF parameter tuning)
"""
import sys
import os
import time
import signal
import atexit
import threading
from xmlrpc.server import SimpleXMLRPCServer
import numpy as np
import zmq

# Ensure libiio DLL is in PATH and DLL search directory
if sys.platform == 'win32':
    dll_dir = r"C:\Users\vmj07\radioconda\Library\bin"
    if os.path.exists(dll_dir):
        os.environ['PATH'] = dll_dir + ';' + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(dll_dir)

import adi

class PlutoNativeBridge:
    def __init__(self, uri=None, fs=1000000, fc=2400000000, rx_gain=60, tx_atten=5):
        # Single-instance process lock on port 8099: prevent duplicate bridge collision
        import socket
        self._lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._lock_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._lock_sock.bind(('127.0.0.1', 8099))
            self._lock_sock.listen(1)
        except Exception:
            print("[PlutoNative] Notice: Another Pluto bridge process is already running. Exiting duplicate process.", flush=True)
            sys.exit(0)

        self.samp_rate = int(fs)
        self.center_freq = int(fc)
        self.rx_gain = int(rx_gain)
        self.tx_atten = int(tx_atten)
        self.rf_bw = int(1500000)
        self.running = False
        self.sdr_lock = threading.RLock()
        
        # XML-RPC server on 8090 initialized immediately so listeners can verify bridge presence
        try:
            self.rpc_server = SimpleXMLRPCServer(('127.0.0.1', 8090), allow_none=True, logRequests=False)
            self.rpc_server.register_instance(self)
            self.rpc_thread = threading.Thread(target=self.rpc_server.serve_forever, daemon=True, name="PlutoRPC")
            self.rpc_thread.start()
        except Exception as e:
            print(f"[PlutoNative] XML-RPC server bind notice: {e}", flush=True)
            self.rpc_server = None

        # ZeroMQ sockets
        self.ctx = zmq.Context()
        self.push_sock = self.ctx.socket(zmq.PUSH)
        self.push_sock.setsockopt(zmq.SNDHWM, 16)
        self.push_sock.connect("tcp://127.0.0.1:5555")
        
        self.pull_sock = self.ctx.socket(zmq.PULL)
        self.pull_sock.setsockopt(zmq.RCVHWM, 8)
        self.pull_sock.setsockopt(zmq.RCVTIMEO, 50)
        self.pull_sock.connect("tcp://127.0.0.1:5556")

        # Candidate connection URIs (priority to Ethernet-over-USB IP)
        self.candidate_uris = []
        if uri:
            self.candidate_uris.append(uri)
        self.candidate_uris.extend(["ip:192.168.2.1", "ip:pluto.local", "default"])
        
        self.sdr = None
        self.uri = None
        self._connect_sdr()

    def _connect_sdr(self):
        """Thread-safe connection and configuration of the ADALM-PLUTO device."""
        with self.sdr_lock:
            for candidate in self.candidate_uris:
                print(f"[PlutoNative] Connecting to Pluto SDR ({candidate})...", flush=True)
                try:
                    if candidate == "default":
                        self.sdr = adi.Pluto()
                    else:
                        self.sdr = adi.Pluto(candidate)
                    self.uri = candidate
                    print(f"[PlutoNative] Connected successfully via {candidate}!", flush=True)
                    self._configure_sdr()
                    return True
                except Exception as e:
                    print(f"[PlutoNative] Connection to {candidate} failed: {e}", flush=True)
            return False

    def _configure_sdr(self):
        """Set sample rates, LO frequencies, gains, and initialize cyclic buffer."""
        if self.sdr is None:
            return
        print("[PlutoNative] Configuring RF parameters...", flush=True)
        self.sdr.sample_rate = self.samp_rate
        self.sdr.rx_lo = self.center_freq
        self.sdr.tx_lo = self.center_freq
        self.sdr.rx_rf_bandwidth = self.rf_bw
        self.sdr.tx_rf_bandwidth = self.rf_bw
        self.sdr.rx_hardwaregain_chan0 = self.rx_gain
        self.sdr.tx_hardwaregain_chan0 = -self.tx_atten
        self.sdr.rx_buffer_size = 32768
        try:
            self.sdr.loopback = 0
        except Exception:
            pass
        self.sdr.tx_cyclic_buffer = True
        
        # Initial cyclic burst so RX always sees RF activity immediately
        t = np.arange(32768) / float(self.samp_rate)
        init_tx = 0.5 * np.exp(1j * 2.0 * np.pi * 150000.0 * t).astype(np.complex64)
        dac_scale = (init_tx * (2**14)).astype(np.complex64)
        try:
            self.sdr.tx(dac_scale)
            print("[PlutoNative] Initialized hardware with cyclic carrier burst.", flush=True)
        except Exception as e:
            print(f"[PlutoNative] Notice during initial TX burst: {e}", flush=True)

    def _reconnect_sdr(self):
        """Handle socket disconnect / -10054 cleanly with backoff and reconnection."""
        with self.sdr_lock:
            try:
                if self.sdr is not None:
                    try:
                        self.sdr.tx_destroy_buffer()
                    except Exception:
                        pass
                    try:
                        self.sdr.rx_destroy_buffer()
                    except Exception:
                        pass
                    del self.sdr
                    self.sdr = None
            except Exception:
                pass
        time.sleep(1.0)
        return self._connect_sdr()

    # XML-RPC Interface getters & setters matching GRC
    def get_center_freq(self):
        return self.center_freq

    def set_center_freq(self, freq):
        self.center_freq = int(freq)
        with self.sdr_lock:
            if self.sdr is not None:
                try:
                    self.sdr.rx_lo = self.center_freq
                    self.sdr.tx_lo = self.center_freq
                except Exception as e:
                    print(f"[PlutoNative] Error setting center_freq: {e}", flush=True)
        return True

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, sr):
        self.samp_rate = int(sr)
        with self.sdr_lock:
            if self.sdr is not None:
                try:
                    self.sdr.sample_rate = self.samp_rate
                except Exception as e:
                    print(f"[PlutoNative] Error setting sample_rate: {e}", flush=True)
        return True

    def get_rx_gain(self):
        return self.rx_gain

    def set_rx_gain(self, gain):
        self.rx_gain = int(gain)
        with self.sdr_lock:
            if self.sdr is not None:
                try:
                    self.sdr.rx_hardwaregain_chan0 = self.rx_gain
                except Exception as e:
                    print(f"[PlutoNative] Error setting rx_gain: {e}", flush=True)
        return True

    def get_tx_atten(self):
        return self.tx_atten

    def set_tx_atten(self, atten):
        self.tx_atten = int(atten)
        with self.sdr_lock:
            if self.sdr is not None:
                try:
                    self.sdr.tx_hardwaregain_chan0 = -self.tx_atten
                except Exception as e:
                    print(f"[PlutoNative] Error setting tx_atten: {e}", flush=True)
        return True

    def get_rf_bw(self):
        return self.rf_bw

    def set_rf_bw(self, bw):
        self.rf_bw = int(bw)
        with self.sdr_lock:
            if self.sdr is not None:
                try:
                    self.sdr.rx_rf_bandwidth = self.rf_bw
                    self.sdr.tx_rf_bandwidth = self.rf_bw
                except Exception as e:
                    print(f"[PlutoNative] Error setting rf_bw: {e}", flush=True)
        return True

    def is_ready(self):
        """XML-RPC readiness check: returns True when SDR is connected and streaming loops are active."""
        return bool(self.sdr is not None and self.running)

    def start(self):
        self.running = True
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True, name="PlutoNativeRx")
        self.tx_thread = threading.Thread(target=self._tx_loop, daemon=True, name="PlutoNativeTx")
        self.rx_thread.start()
        self.tx_thread.start()
        print("[PlutoNative] RX and TX streaming loops active!", flush=True)

    def _tx_loop(self):
        last_tx_hash = None
        while self.running:
            try:
                raw_bytes = self.pull_sock.recv()
                if not raw_bytes:
                    continue
                tx_iq = np.frombuffer(raw_bytes, dtype=np.complex64)
                if len(tx_iq) > 0:
                    tx_hash = hash(raw_bytes[:min(len(raw_bytes), 512)])
                    if tx_hash != last_tx_hash:
                        last_tx_hash = tx_hash
                        # Pluto DAC requires scaled amplitude (~2**14)
                        dac_iq = (tx_iq * (2**14)).astype(np.complex64)
                        with self.sdr_lock:
                            if self.sdr is not None:
                                try:
                                    self.sdr.tx(dac_iq)
                                except Exception:
                                    try:
                                        self.sdr.tx_destroy_buffer()
                                        time.sleep(0.01)
                                        self.sdr.tx_cyclic_buffer = True
                                        self.sdr.tx(dac_iq)
                                    except Exception:
                                        pass
            except zmq.Again:
                pass
            except Exception as e:
                time.sleep(0.02)

    def _rx_loop(self):
        consecutive_errors = 0
        while self.running:
            try:
                with self.sdr_lock:
                    if self.sdr is None:
                        time.sleep(0.5)
                        continue
                    rx_data = self.sdr.rx()
                if len(rx_data) > 0:
                    consecutive_errors = 0
                    # Normalize Pluto ADC integer values (~2**11 - 2**12) to unit float32
                    norm_iq = (rx_data / 2048.0).astype(np.complex64)
                    try:
                        self.push_sock.send(norm_iq.tobytes(), flags=zmq.NOBLOCK)
                    except zmq.Again:
                        pass
            except zmq.Again:
                pass
            except Exception as e:
                consecutive_errors += 1
                time.sleep(0.01)
                if consecutive_errors > 5:
                    print(f"[PlutoNative] SDR connection lost ({e}). Reconnecting...", flush=True)
                    self._reconnect_sdr()
                    consecutive_errors = 0

    def stop(self):
        self.running = False
        with self.sdr_lock:
            if self.sdr is not None:
                try:
                    self.sdr.tx_destroy_buffer()
                except Exception:
                    pass
                try:
                    self.sdr.rx_destroy_buffer()
                except Exception:
                    pass
        if self.rpc_server:
            try:
                threading.Thread(target=self.rpc_server.shutdown, daemon=True).start()
            except Exception:
                pass
        if hasattr(self, '_lock_sock') and self._lock_sock:
            try:
                self._lock_sock.close()
            except Exception:
                pass
        try:
            self.push_sock.close(linger=0)
            self.pull_sock.close(linger=0)
            self.ctx.term()
        except Exception:
            pass

def main():
    bridge = PlutoNativeBridge()
    bridge.start()
    
    def cleanup():
        bridge.stop()
    atexit.register(cleanup)
    
    print("[PlutoNative] Hardware bridge running continuously. Press Ctrl+C to terminate.", flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[PlutoNative] Terminating bridge...", flush=True)
        bridge.stop()

if __name__ == '__main__':
    main()
