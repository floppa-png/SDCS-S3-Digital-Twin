import math
import numpy as np
from typing import Tuple, List, Optional
from dataclasses import dataclass
from .config import TxConfig, LinkPlan, derive_link_plan

def generate_m_sequence_63() -> np.ndarray:
    """Generate length 63 maximal length sequence using x^6 + x^5 + 1 polynomial."""
    state = 0b111111
    seq = []
    for _ in range(63):
        out = state & 1
        seq.append(out)
        feedback = ((state >> 0) ^ (state >> 1)) & 1
        state = (state >> 1) | (feedback << 5)
    return np.array(seq, dtype=np.int32)

PREAMBLE_BITS = generate_m_sequence_63()
PREAMBLE_BPSK = 2.0 * PREAMBLE_BITS - 1.0  # Length 63

def crc8(data_bytes: bytes) -> int:
    """Compute standard robust CRC-8 with polynomial 0x07, init 0xFF, final XOR 0xFF."""
    crc = 0xFF
    for byte in data_bytes:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc ^ 0xFF

def rrc_taps(sps: int, span: int, alpha: float) -> np.ndarray:
    """Design Root-Raised-Cosine (RRC) filter taps."""
    N = span * sps
    t = np.arange(-N // 2, N // 2 + 1) / float(sps)
    h = np.zeros(len(t), dtype=np.float64)
    
    alpha = max(1e-4, min(1.0, float(alpha)))
    
    for i, ti in enumerate(t):
        if abs(ti) < 1e-8:
            h[i] = 1.0 - alpha + (4.0 * alpha / np.pi)
        elif abs(abs(4.0 * alpha * ti) - 1.0) < 1e-6:
            term1 = (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * alpha))
            term2 = (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * alpha))
            h[i] = (alpha / np.sqrt(2.0)) * (term1 + term2)
        else:
            num = np.sin(np.pi * ti * (1.0 - alpha)) + 4.0 * alpha * ti * np.cos(np.pi * ti * (1.0 + alpha))
            den = np.pi * ti * (1.0 - (4.0 * alpha * ti) ** 2)
            h[i] = num / den
            
    # Normalize unit energy
    energy = np.sum(h ** 2)
    if energy > 0:
        h = h / np.sqrt(energy)
    return h.astype(np.float32)

@dataclass
class TxFrame:
    iq: np.ndarray              # Complex baseband samples at fs
    raw_bits: np.ndarray        # Payload bits
    frame_id: int               # Frame ID (uint16)
    cfg_version: int            # Config version (uint8)
    mod: str                    # Modulation scheme
    sps: int                    # Samples per symbol
    num_symbols: int            # Payload symbols count
    preamble_start: int         # Sample index of preamble start
    payload_start: int          # Sample index of payload start
    payload_end: int            # Sample index of payload end
    plan: LinkPlan              # Associated link plan
    analog_msg: Optional[np.ndarray] = None  # Original analog message if analog source

class Modulator:
    """Complex baseband modulator with framing, pulse shaping and analog synthesis."""
    
    def __init__(self, fs: int = 1000000):
        self.fs = fs
        self._frame_seq = 0
        self._fsk_phase = 0.0
        
    def modulate_bits_to_symbols(self, bits: np.ndarray, mod: str) -> np.ndarray:
        """Map bits to constellation symbols with Gray coding."""
        if mod == 'BPSK':
            return (2.0 * bits - 1.0).astype(np.complex64)
            
        elif mod == 'QPSK':
            # 2 bits per symbol Gray: b0 -> I, b1 -> Q
            n_sym = len(bits) // 2
            b_pairs = bits[:n_sym * 2].reshape(n_sym, 2)
            i_val = 1.0 - 2.0 * b_pairs[:, 0]
            q_val = 1.0 - 2.0 * b_pairs[:, 1]
            return ((i_val + 1j * q_val) / np.sqrt(2.0)).astype(np.complex64)
            
        elif mod == 'ASK':
            # OOK / 2-ASK: 0 -> 0, 1 -> sqrt(2) so avg power is 1.0
            return (bits * np.sqrt(2.0)).astype(np.complex64)
            
        elif mod == 'FSK':
            # Returns NRZ polarity for frequency calculation
            return (2.0 * bits - 1.0).astype(np.complex64)
            
        return (2.0 * bits - 1.0).astype(np.complex64)

    def generate_digital_frame(self, cfg: TxConfig, cfg_version: int = 1,
                               fixed_bits: Optional[np.ndarray] = None) -> TxFrame:
        """Generate framed digital signal (Preamble + Header + Payload)."""
        plan = derive_link_plan(cfg, cfg.modulation)
        mod = cfg.modulation
        sps = plan.samples_per_symbol
        k_bits = plan.bits_per_symbol
        
        # Payload size: between 128 and 2048 symbols (~80-100 ms burst)
        n_symbols = int(np.clip(round(0.08 * plan.symbol_rate), 128, 2048))
        n_bits = n_symbols * k_bits
        
        self._frame_seq = (self._frame_seq + 1) & 0xFFFF
        frame_id = self._frame_seq
        
        if fixed_bits is not None and len(fixed_bits) >= n_bits:
            payload_bits = fixed_bits[:n_bits]
        else:
            # Deterministic PRBS keyed to frame_id: allows receiver to reconstruct exact
            # reference payload even with asynchronous Pluto SDR hardware buffer latencies
            prng = np.random.RandomState(seed=frame_id)
            payload_bits = prng.randint(0, 2, size=n_bits, dtype=np.int32)

        
        # Build 32-bit BPSK Header: 16-bit frame_id + 8-bit cfg_version + 8-bit CRC
        header_bytes = bytes([
            (frame_id >> 8) & 0xFF,
            frame_id & 0xFF,
            cfg_version & 0xFF
        ])
        h_crc = crc8(header_bytes)
        hdr_bits_list = []
        for b in header_bytes + bytes([h_crc]):
            for bit_i in range(7, -1, -1):
                hdr_bits_list.append((b >> bit_i) & 1)
        header_bits = np.array(hdr_bits_list, dtype=np.int32)  # 32 bits
        
        # Preamble symbols (63 BPSK) and Header symbols (32 BPSK)
        preamble_syms = (2.0 * PREAMBLE_BITS - 1.0).astype(np.complex64)
        header_syms = (2.0 * header_bits - 1.0).astype(np.complex64)
        sync_syms = np.concatenate([preamble_syms, header_syms])  # 95 symbols total
        
        # Payload symbols
        payload_syms = self.modulate_bits_to_symbols(payload_bits, mod)
        
        # Pulse shaping filter
        h_rrc = rrc_taps(sps, span=8, alpha=cfg.rolloff)
        guard_syms = 16
        
        if mod == 'FSK':
            # FSK uses CPFSK for payload, but keeps BPSK RRC for sync
            sync_upsampled = np.zeros(len(sync_syms) * sps, dtype=np.complex64)
            sync_upsampled[::sps] = sync_syms
            sync_tx = np.convolve(sync_upsampled, h_rrc, mode='same').astype(np.complex64)
            
            # CPFSK payload
            h_fsk = cfg.fsk_h
            f_dev = (h_fsk * plan.symbol_rate) / 2.0
            freq_offset = (2.0 * payload_bits - 1.0) * f_dev
            freq_samples = np.repeat(freq_offset, sps)
            
            # Continuous phase
            dphi = 2.0 * np.pi * freq_samples / float(self.fs)
            phase = np.cumsum(dphi) + self._fsk_phase
            self._fsk_phase = phase[-1] % (2.0 * np.pi)
            payload_tx = np.exp(1j * phase).astype(np.complex64)
            
            # Assemble frame
            guard_samps = np.zeros(guard_syms * sps, dtype=np.complex64)
            preamble_start = len(guard_samps)
            payload_start = preamble_start + len(sync_tx)
            payload_end = payload_start + len(payload_tx)
            
            tx_iq = np.concatenate([guard_samps, sync_tx, payload_tx, guard_samps])
        else:
            # Linear modulations: Preamble + Header + Payload all pulse shaped
            all_syms = np.concatenate([sync_syms, payload_syms])
            all_upsampled = np.zeros(len(all_syms) * sps, dtype=np.complex64)
            all_upsampled[::sps] = all_syms
            shaped = np.convolve(all_upsampled, h_rrc, mode='same')
            
            guard_samps = np.zeros(guard_syms * sps, dtype=np.complex64)
            preamble_start = len(guard_samps)
            payload_start = preamble_start + len(sync_syms) * sps
            payload_end = payload_start + len(payload_syms) * sps
            
            tx_iq = np.concatenate([guard_samps, shaped, guard_samps])
            
        return TxFrame(
            iq=tx_iq.astype(np.complex64),
            raw_bits=payload_bits,
            frame_id=frame_id,
            cfg_version=cfg_version,
            mod=mod,
            sps=sps,
            num_symbols=n_symbols,
            preamble_start=preamble_start,
            payload_start=payload_start,
            payload_end=payload_end,
            plan=plan
        )

    def generate_analog_signal(self, cfg: TxConfig, duration: float = 0.08) -> Tuple[np.ndarray, np.ndarray, LinkPlan]:
        """Generate analog passband-equivalent complex baseband signal."""
        plan = derive_link_plan(cfg, cfg.modulation)
        mod = cfg.modulation
        w_eff = max(1000.0, float(getattr(plan, 'msg_bw_effective', 0.0) or getattr(cfg, 'msg_bw', 4000.0)))
        
        n_samples = int(round(duration * self.fs))
        t = np.arange(n_samples) / float(self.fs)
        
        # Multitone baseband message signal: 0.2*W, 0.5*W, 0.85*W
        f1 = max(100.0, 0.20 * w_eff)
        f2 = max(200.0, 0.50 * w_eff)
        f3 = max(300.0, 0.85 * w_eff)
        
        msg = (0.5 * np.cos(2.0 * np.pi * f1 * t + 0.3) +
               0.35 * np.cos(2.0 * np.pi * f2 * t + 1.2) +
               0.25 * np.cos(2.0 * np.pi * f3 * t + 2.4))
        # Normalize message to peak 1.0, power ~0.5
        msg = msg / (np.max(np.abs(msg)) + 1e-12)
        
        if mod == 'AM_DSBSC':
            # Complex baseband: m(t) + 0j
            iq = msg.astype(np.complex64)
        elif mod == 'AM_DSBTC':
            # Complex baseband: (1.0 + mu * m(t)) + 0j
            mu = cfg.am_index
            iq = (1.0 + mu * msg).astype(np.complex64)
        elif mod == 'FM':
            # Complex baseband: exp(j * 2π * Delta_f * integral(m(t) dt))
            b_occ = max(w_eff * 2.0, float(getattr(plan, 'occupied_bw', 0.0) or (cfg.alloc_bw * 0.8)))
            beta_eff = max(0.3, (b_occ / (2.0 * w_eff)) - 1.0)
            delta_f = beta_eff * w_eff
            integral_m = np.cumsum(msg) / float(self.fs)
            phase = 2.0 * np.pi * delta_f * integral_m
            iq = np.exp(1j * phase).astype(np.complex64)
        else:
            iq = msg.astype(np.complex64)
            
        return iq, msg, plan

    def generate_pcm_bits(self, msg: np.ndarray, pcm_bits: int) -> np.ndarray:
        """Uniform PCM quantization of analog message into bitstream."""
        # Quantize [-1, +1] into 2^pcm_bits levels
        levels = 2 ** pcm_bits
        scaled = np.clip((msg + 1.0) * 0.5 * (levels - 1), 0, levels - 1).astype(np.int32)
        bits = []
        for val in scaled:
            for b_i in range(pcm_bits - 1, -1, -1):
                bits.append((val >> b_i) & 1)
        return np.array(bits, dtype=np.int32)

    def reconstruct_pcm(self, bits: np.ndarray, pcm_bits: int) -> np.ndarray:
        """Reconstruct analog signal from PCM bitstream."""
        n_words = len(bits) // pcm_bits
        if n_words == 0:
            return np.array([0.0], dtype=np.float32)
        b_grouped = bits[:n_words * pcm_bits].reshape(n_words, pcm_bits)
        powers = 2 ** np.arange(pcm_bits - 1, -1, -1)
        vals = np.sum(b_grouped * powers, axis=1)
        levels = 2 ** pcm_bits
        reconstructed = (vals / float(levels - 1)) * 2.0 - 1.0
        return reconstructed.astype(np.float32)
