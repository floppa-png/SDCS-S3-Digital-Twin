import sys
import os
import time
import socket
import threading
import xmlrpc.client
from typing import Optional, Tuple, Dict, Any
import numpy as np
import zmq
from scipy.signal import butter, lfilter, lfilter_zi
from .config import TxConfig

class PlutoBridge:
    """
    Hardware bridge connecting Python backend to GNU Radio Companion (GRC) flowgraph and Pluto SDR.
    Uses ZeroMQ PUSH/PULL for high-rate complex IQ and XML-RPC for RF parameter tuning.
    Applies 150 kHz Digital IF offset to keep signal away from Pluto DC/LO leakage.
    """
    
    def __init__(self, fs: int = 1000000, f_if: float = 150000.0, xmlrpc_url: str = "http://127.0.0.1:8090"):
        self.fs = fs
        self.f_if = f_if
        self.xmlrpc_url = xmlrpc_url
        self._bridge_proc = None
        
        self.running = False
        self._tx_phase = 0.0
        self._rx_phase = 0.0
        
        # Ring buffer for 2 seconds of complex64 IQ
        self.buf_size = int(fs * 2.0)
        self.ring_buf = np.zeros(self.buf_size, dtype=np.complex64)
        self.buf_idx = 0
        self.buf_lock = threading.Lock()
        
        # Link state tracking
        self.samples_received_window = 0
        self.last_rate_check = time.time()
        self.rx_rate_sps = 0.0
        self.link_up = False
        
        # ZMQ setup
        self.ctx = zmq.Context()
        self.tx_sock = self.ctx.socket(zmq.PUSH)
        self.tx_sock.setsockopt(zmq.SNDHWM, 4)
        try:
            self.tx_sock.bind("tcp://127.0.0.1:5556")
        except zmq.ZMQError as e:
            print(f"[PlutoBridge] Warning: TX bind 5556: {e}")
            
        self.rx_sock = self.ctx.socket(zmq.PULL)
        self.rx_sock.setsockopt(zmq.RCVHWM, 16)
        self.rx_sock.setsockopt(zmq.RCVTIMEO, 100) # 100ms timeout
        try:
            self.rx_sock.bind("tcp://127.0.0.1:5555")
        except zmq.ZMQError as e:
            print(f"[PlutoBridge] Warning: RX bind 5555: {e}")
            
        # Lowpass filter for removing IF image and out-of-band noise after downshift
        # Cutoff at 200 kHz (passes up to 400 kHz allocated BW)
        b, a = butter(4, 200000.0 / (fs / 2.0), btype='low')
        self.lpf_b = b.astype(np.float64)
        self.lpf_a = a.astype(np.float64)
        self._rx_filter_zi = np.zeros(max(len(self.lpf_a), len(self.lpf_b)) - 1, dtype=np.complex64)
        
        # XML-RPC client with 0.5s timeout
        self.rpc_client: Optional[xmlrpc.client.ServerProxy] = None
        self._init_rpc()
        
        # Background worker thread for RX ring buffer
        self.rx_thread: Optional[threading.Thread] = None
        self.start()

    def _init_rpc(self):
        try:
            # Set socket default timeout temporarily for proxy setup
            orig_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(0.5)
            self.rpc_client = xmlrpc.client.ServerProxy(self.xmlrpc_url, allow_none=True)
            socket.setdefaulttimeout(orig_timeout)
        except Exception as e:
            print(f"[PlutoBridge] XML-RPC init notice: {e}")
            self.rpc_client = None

    def start(self):
        """Start background receiver thread."""
        if self.running:
            return
        self.running = True
        self.rx_thread = threading.Thread(target=self._rx_worker, daemon=True, name="PlutoRxWorker")
        self.rx_thread.start()

    def stop(self):
        """Stop background receiver and close sockets."""
        self.running = False
        if self.rx_thread and self.rx_thread.is_alive():
            self.rx_thread.join(timeout=0.5)
        try:
            self.tx_sock.close(linger=0)
            self.rx_sock.close(linger=0)
            self.ctx.term()
        except Exception:
            pass
        if self._bridge_proc and self._bridge_proc.poll() is None:
            try:
                self._bridge_proc.terminate()
            except Exception:
                pass

    def ensure_bridge_running(self) -> bool:
        """Ensure pluto_native_bridge.py background process is running."""
        if self.link_up:
            return True
        if os.environ.get("PLUTO_BRIDGE_MANAGED") == "1":
            return True
        try:
            with socket.create_connection(('127.0.0.1', 8090), timeout=0.2):
                return True
        except Exception:
            pass
        try:
            with socket.create_connection(('127.0.0.1', 8099), timeout=0.2):
                return True
        except Exception:
            pass
            
        import subprocess
        radioconda_python = r"C:\Users\vmj07\radioconda\python.exe"
        py_exe = radioconda_python if os.path.exists(radioconda_python) else sys.executable
        bridge_script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pluto_native_bridge.py")
        if os.path.exists(bridge_script):
            try:
                print(f"[PlutoBridge] Auto-starting Pluto native bridge via {py_exe}...", flush=True)
                self._bridge_proc = subprocess.Popen([py_exe, bridge_script])
                return True
            except Exception as e:
                print(f"[PlutoBridge] Failed to auto-start bridge: {e}", flush=True)
        return False

    def _rx_worker(self):
        """Continuous background thread draining ZMQ PULL socket into circular buffer."""
        while self.running:
            try:
                raw_bytes = self.rx_sock.recv()
                if not raw_bytes:
                    continue
                # Raw IQ from GRC is complex64 (float32 I, float32 Q)
                raw_iq = np.frombuffer(raw_bytes, dtype=np.complex64)
                n = len(raw_iq)
                if n == 0:
                    continue
                    
                # Down-convert from Digital IF (-150 kHz)
                t = np.arange(n) / float(self.fs)
                down_rot = np.exp(-1j * (2.0 * np.pi * self.f_if * t + self._rx_phase))
                self._rx_phase = (self._rx_phase + 2.0 * np.pi * self.f_if * n / float(self.fs)) % (2.0 * np.pi)
                baseband_iq = raw_iq * down_rot
                
                # Baseband low-pass filter with continuous state across chunks
                filtered_iq, self._rx_filter_zi = lfilter(self.lpf_b, self.lpf_a, baseband_iq, zi=self._rx_filter_zi)
                filtered_iq = filtered_iq.astype(np.complex64)
                
                # Insert into circular buffer
                with self.buf_lock:
                    if self.buf_idx + n <= self.buf_size:
                        self.ring_buf[self.buf_idx : self.buf_idx + n] = filtered_iq
                        self.buf_idx = (self.buf_idx + n) % self.buf_size
                    else:
                        first_chunk = self.buf_size - self.buf_idx
                        self.ring_buf[self.buf_idx :] = filtered_iq[:first_chunk]
                        second_chunk = n - first_chunk
                        self.ring_buf[:second_chunk] = filtered_iq[first_chunk:]
                        self.buf_idx = second_chunk
                        
                    self.samples_received_window += n
                    
            except zmq.Again:
                # Socket timeout, normal when GRC is paused/not running
                pass
            except Exception as e:
                if self.running:
                    time.sleep(0.01)
                    
            # Check link status once per second
            now = time.time()
            if now - self.last_rate_check >= 1.0:
                dt = now - self.last_rate_check
                self.rx_rate_sps = self.samples_received_window / dt
                self.link_up = self.rx_rate_sps > 50000.0  # Link active if receiving samples
                self.samples_received_window = 0
                self.last_rate_check = now

    def send_tx(self, iq: np.ndarray, peak_target: float = 0.7) -> bool:
        """
        Apply IF offset (+150 kHz) and send burst/frame to GRC PUSH socket.
        Normalizes peak amplitude to peak_target (<= 0.7) to avoid DAC clipping.
        """
        if len(iq) == 0:
            return False
            
        # Peak normalization
        max_val = float(np.max(np.abs(iq)))
        if max_val > 1e-6:
            tx_norm = (iq / max_val) * min(0.7, peak_target)
        else:
            tx_norm = iq
            
        # Sustained burst: tile frame to >= 32768 samples (~32.7 ms)
        # Prevents Pluto DAC buffer starvation/underflow during 10 Hz frame loop
        if len(tx_norm) < 32768:
            reps = int(np.ceil(32768 / len(tx_norm)))
            tx_norm = np.tile(tx_norm, reps)
            
        n = len(tx_norm)
        t = np.arange(n) / float(self.fs)
        up_rot = np.exp(1j * (2.0 * np.pi * self.f_if * t + self._tx_phase))
        self._tx_phase = (self._tx_phase + 2.0 * np.pi * self.f_if * n / float(self.fs)) % (2.0 * np.pi)
        
        tx_if = (tx_norm * up_rot).astype(np.complex64)
        
        try:
            self.tx_sock.send(tx_if.tobytes(), flags=zmq.NOBLOCK)
            return True
        except zmq.Again:
            # Drop frame if GRC is backpressured
            return False
        except Exception:
            return False

    def get_recent_rx(self, num_samples: int) -> np.ndarray:
        """Fetch the most recent num_samples from the circular buffer."""
        num_samples = min(num_samples, self.buf_size)
        with self.buf_lock:
            if self.buf_idx >= num_samples:
                return self.ring_buf[self.buf_idx - num_samples : self.buf_idx].copy()
            else:
                need_from_end = num_samples - self.buf_idx
                return np.concatenate((
                    self.ring_buf[self.buf_size - need_from_end :],
                    self.ring_buf[: self.buf_idx]
                )).copy()

    def flush(self):
        """Flush the circular buffer on modulation or configuration changes."""
        with self.buf_lock:
            self.ring_buf.fill(0)
            self.buf_idx = 0
            self.samples_received_window = 0

    def set_rf_params(self, center_freq: float, tx_atten: float, rx_gain: float) -> Tuple[bool, Optional[str]]:
        """Push tuned RF parameters to GRC via XML-RPC. Never crashes on connection failure."""
        if not self.rpc_client:
            self._init_rpc()
        if not self.rpc_client:
            return False, "XML-RPC client not initialized"
            
        try:
            # Standard GRC XML-RPC setter names
            self.rpc_client.set_center_freq(float(center_freq))
            self.rpc_client.set_tx_atten(float(tx_atten))
            self.rpc_client.set_rx_gain(float(rx_gain))
            return True, None
        except Exception as e:
            return False, f"Hardware RPC error: {e}"
            
    def get_status(self) -> Dict[str, Any]:
        """Telemetry status for hardware bridge."""
        return {
            'link_up': self.link_up,
            'rx_rate_sps': round(self.rx_rate_sps, 1),
            'f_if_hz': self.f_if,
            'fs': self.fs
        }
