import os
import time
import math
import random
import threading
from collections import deque
from typing import Dict, Any, Optional, Callable, List, Tuple
import numpy as np
from scipy.signal import welch

from .config import (
    TxConfig, LinkPlan, derive_link_plan, validate_params,
    MODULATIONS, DIGITAL_MODS, ANALOG_MODS, PARAM_SPEC
)
from .waveforms import Modulator
from .channel import ChannelModel
from .receiver import Receiver
from .metrics import MetricCalculator, RollingMetrics
from .scoring import Scorer
from .twin import DigitalTwin
from .presets import PRESETS, get_preset_config, randomize_scenario, SCENARIO_METADATA
from .hardware import PlutoBridge
from .equalizer import AdaptiveEqualizer

class Engine:
    """
    Central orchestration engine for the SDCS Digital Twin.
    Coordinates real-time signal generation (~10 Hz), physical channel/hardware streaming,
    telemetry calculation, twin evaluation (~1 Hz), and parameter randomization.
    """
    
    def __init__(self, fs: int = 1000000):
        self.fs = fs
        self.lock = threading.RLock()
        
        # Core State
        self.config = TxConfig()
        self.cfg_version = 1
        self.mode = os.environ.get("SDCS_MODE", "sim").lower()  # 'sim' or 'pluto'
        self.active_scenario = "deep_space"
        
        # Modules
        self.modulator = Modulator(fs=fs)
        self.channel = ChannelModel(fs=fs, seed=42)
        self.receiver = Receiver(fs=fs)
        self.rolling = RollingMetrics()
        self.twin = DigitalTwin(fs=fs)
        self.bridge = PlutoBridge(fs=fs)
        self._last_hw_tx_key: Optional[Tuple[Any, ...]] = None
        
        # Autopilot & Randomizer
        self.randomizer_enabled = False
        self.randomizer_interval_s = 25.0
        self.randomizer_next_in_s = 25.0
        self.autopilot_enabled = False
        self._pending_autopilot_time: Optional[float] = None
        self.last_adaptation_time: float = 0.0
        self._last_adapted_from: Optional[str] = None
        self._last_adapted_to: Optional[str] = None
        self._suboptimal_count: int = 0
        
        # Cyber-Physical Security & FDIA Tracking
        self.boot_time: float = time.time()
        self.fdia_injected_count: int = 0
        self.fdia_detected_count: int = 0
        self.fdia_mitigated_count: int = 0
        self.random_fdia_enabled: bool = False
        self.random_fdia_next_s: float = 0.0
        self._last_terminal_fdia_report: float = 0.0
        self.random_fdia_thread: Optional[threading.Thread] = None
        
        # Operational Event Log Ring Buffer (enlarged for audit reports)
        self.event_log = deque(maxlen=300)
        
        # Telemetry & Callbacks
        self.last_frame_telemetry: Dict[str, Any] = {}
        self.last_twin_payload: Dict[str, Any] = self.twin.evaluate(self.config, scenario_preset=self.active_scenario)
        self.last_measured_score = 0
        
        self.on_frame_emit: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_twin_emit: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_config_emit: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_event_emit: Optional[Callable[[Dict[str, Any]], None]] = None
        
        # Worker Threads
        self.running = False
        self.frame_thread: Optional[threading.Thread] = None
        self.twin_thread: Optional[threading.Thread] = None
        self.randomizer_thread: Optional[threading.Thread] = None
        
        self.log_event("engine_start", "SDCS Digital Twin Engine initialized")

    def start(self):
        """Start engine background worker loops."""
        if self.running:
            return
        self.running = True
        
        if self.mode == 'pluto':
            self.bridge.ensure_bridge_running()
        
        self.frame_thread = threading.Thread(target=self._frame_loop, daemon=True, name="EngineFrameLoop")
        self.twin_thread = threading.Thread(target=self._twin_loop, daemon=True, name="EngineTwinLoop")
        self.randomizer_thread = threading.Thread(target=self._randomizer_loop, daemon=True, name="EngineRandomizerLoop")
        self.random_fdia_thread = threading.Thread(target=self._random_fdia_loop, daemon=True, name="EngineRandomFdiaLoop")
        
        self.frame_thread.start()
        self.twin_thread.start()
        self.randomizer_thread.start()
        self.random_fdia_thread.start()

    def stop(self):
        """Stop all background workers and shut down hardware bridge."""
        self.running = False
        self.bridge.stop()

    def log_event(self, ev_type: str, msg: str, data: Optional[Dict[str, Any]] = None):
        """Add event to ring buffer and notify clients."""
        ev = {
            'time': time.strftime("%H:%M:%S"),
            'timestamp': time.time(),
            'type': ev_type,
            'message': msg,
            'data': data or {}
        }
        self.event_log.appendleft(ev)
        if self.on_event_emit:
            self.on_event_emit(ev)

    def get_state(self) -> Dict[str, Any]:
        """Full system state snapshot for GET /api/state."""
        with self.lock:
            return {
                'config': self.config.to_dict(),
                'cfg_version': self.cfg_version,
                'mode': self.mode,
                'link_up': self.bridge.link_up if self.mode == 'pluto' else True,
                'rx_rate_sps': self.bridge.rx_rate_sps if self.mode == 'pluto' else self.fs,
                'randomizer': {
                    'enabled': self.randomizer_enabled,
                    'next_in_s': max(0.0, round(self.randomizer_next_in_s, 1)),
                    'interval_s': round(self.randomizer_interval_s, 1)
                },
                'random_fdia': {
                    'enabled': self.random_fdia_enabled,
                    'next_in_s': max(0.0, round(self.random_fdia_next_s, 1))
                },
                'autopilot': self.autopilot_enabled,
                'active_scenario': self.active_scenario,
                'scenarios': SCENARIO_METADATA,
                'fdia_active': getattr(self.config, 'fdia_active', False),
                'presets': list(PRESETS.keys()),
                'last_score': self.last_measured_score,
                'events': list(self.event_log)[:15]
            }

    def get_dossier(self, window: str = 'boot') -> Dict[str, Any]:
        """Compile a comprehensive physical link dossier and cyber-physical security audit report."""
        now = time.time()
        uptime_sec = round(now - self.boot_time, 1)
        
        # Filter event log by user-selected time window
        events = list(self.event_log)
        if window and window != 'boot':
            try:
                w_sec = float(window)
                events = [e for e in events if (now - e.get('timestamp', now)) <= w_sec]
            except (ValueError, TypeError):
                pass
                
        with self.lock:
            active_cfg = self.config.to_dict()
            cur_mod = self.config.modulation
            fdia_active = getattr(self.config, 'fdia_active', False)
            
        telemetry = self.last_frame_telemetry or {}
        twin_info = self.last_twin_payload
        if not twin_info:
            twin_info = self.twin.evaluate(self.config, scenario_preset=getattr(self, 'active_scenario', None))
            self.last_twin_payload = twin_info
        
        m, s = divmod(int(uptime_sec), 60)
        h, m = divmod(m, 60)
        uptime_str = f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"
        
        injected = self.fdia_injected_count
        mitigated = self.fdia_mitigated_count
        rate_pct = round((mitigated / max(1, injected)) * 100, 1) if injected > 0 else 100.0
        
        return {
            'generated_at': time.strftime("%Y-%m-%d %H:%M:%S"),
            'boot_at': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.boot_time)),
            'uptime': uptime_str,
            'uptime_seconds': uptime_sec,
            'window': window,
            'mode': self.mode.upper(),
            'link_up': self.bridge.link_up if self.mode == 'pluto' else True,
            'scenario': {
                'id': self.active_scenario,
                'name': SCENARIO_METADATA.get(self.active_scenario, {}).get('name', self.active_scenario),
                'desc': SCENARIO_METADATA.get(self.active_scenario, {}).get('desc', '')
            },
            'security': {
                'fdia_active': fdia_active,
                'status': 'COMPROMISED (ACTIVE JAMMING)' if fdia_active else 'SECURE / AUTHENTIC',
                'injected_count': injected,
                'detected_count': self.fdia_detected_count,
                'mitigated_count': mitigated,
                'mitigation_rate_pct': rate_pct
            },
            'current_link': {
                'modulation': cur_mod,
                'score': self.last_measured_score,
                'metrics': telemetry.get('metrics', {}),
                'config': active_cfg
            },
            'twin': {
                'best': twin_info.get('best', cur_mod),
                'confidence': twin_info.get('confidence', 0),
                'rationale': twin_info.get('rationale', ''),
                'fidelity': twin_info.get('fidelity', {}),
                'ranking': twin_info.get('ranking', [])
            },
            'events': events
        }

    def update_config(self, updates: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Validate and apply partial configuration updates (POST /api/config)."""
        clean, errors = validate_params(updates, allow_modulation=False)
        if errors:
            return False, errors
            
        with self.lock:
            cfg_dict = self.config.to_dict()
            cfg_dict.update(clean)
            self.config = TxConfig(**cfg_dict)
            self.cfg_version += 1
            self.rolling.reset()
            self.twin._cache.clear()
            self.bridge.flush()
            self._last_hw_tx_key = None
            
            # Sync RF parameters to Pluto if in hardware mode
            if self.mode == 'pluto':
                ok, err = self.bridge.set_rf_params(
                    self.config.center_freq, self.config.tx_atten_db, self.config.rx_gain_db
                )
                if not ok:
                    self.log_event("hw_error", f"XML-RPC RF Sync Failed: {err}")
                    
        self.log_event("config_update", f"Updated {len(clean)} parameters", clean)
        if self.on_config_emit:
            self.on_config_emit({'config': self.config.to_dict(), 'cfg_version': self.cfg_version})
            
        return True, self.config.to_dict()

    def set_modulation(self, mod: str) -> Tuple[bool, str]:
        """Update modulation scheme (POST /api/modulation)."""
        if mod not in MODULATIONS:
            return False, f"Unknown modulation: {mod}"
            
        prev_mod = self.config.modulation
        is_attack = getattr(self.config, 'fdia_active', False)
        with self.lock:
            if prev_mod == mod:
                return True, "No change"
                
            # If active scenario is set, verify modulation compatibility
            if getattr(self, 'active_scenario', None) in PRESETS:
                sc_source = PRESETS[self.active_scenario].get('source_type', 'digital')
                if sc_source == 'analog' and mod in DIGITAL_MODS:
                    return False, f"Cannot select digital modulation {mod} in analog scenario"
                if sc_source == 'digital' and mod in ANALOG_MODS:
                    return False, f"Cannot select analog modulation {mod} in digital scenario"
                    
            self.config.modulation = mod
            if mod in ANALOG_MODS and self.config.source_type == 'digital':
                self.config.source_type = 'analog'
            elif mod in DIGITAL_MODS and self.config.source_type == 'analog':
                self.config.source_type = 'digital'
            self.cfg_version += 1
            self.rolling.reset(self.cfg_version)
            self.twin._cache.clear()
            self.bridge.flush()
            self._last_hw_tx_key = None
            
        if is_attack and prev_mod != mod and mod == 'FSK':
            self.fdia_mitigated_count += 1
            self.log_event("fdia_mitigated", f"Threat Safely Diverted: Operator migration to FSK non-coherent signaling (Mitigation #{self.fdia_mitigated_count})", {
                'from': prev_mod, 'to': 'FSK', 'mitigation_count': self.fdia_mitigated_count
            })

        self.log_event("modulation_change", f"Modulation switched to {mod}")
        if self.on_config_emit:
            self.on_config_emit({'config': self.config.to_dict(), 'cfg_version': self.cfg_version})
            
        # Immediate twin evaluation on modulation switch for 0 ms UI responsiveness
        twin_res = self.twin.evaluate(self.config, scenario_preset=getattr(self, 'active_scenario', None))
        self.last_twin_payload = twin_res
        if self.on_twin_emit:
            self.on_twin_emit(twin_res)
            
        return True, "Updated"

    def apply_best(self) -> Tuple[bool, Dict[str, Any]]:
        """Apply recommended modulation from Digital Twin (POST /api/apply_best)."""
        with self.lock:
            if not self.last_twin_payload or 'best' not in self.last_twin_payload:
                res = self.twin.evaluate(self.config, scenario_preset=getattr(self, 'active_scenario', None))
                best_mod = res['best']
            else:
                best_mod = self.last_twin_payload['best']
                
            prev_mod = self.config.modulation
            if prev_mod == best_mod:
                return False, {'message': f'Already operating on optimal modulation ({best_mod})'}
                
            prev_score = self.last_measured_score
            self.config.modulation = best_mod
            if best_mod in ANALOG_MODS and self.config.source_type == 'digital':
                self.config.source_type = 'analog'
            elif best_mod in DIGITAL_MODS and self.config.source_type == 'analog':
                self.config.source_type = 'digital'
            self.cfg_version += 1
            self.rolling.reset(self.cfg_version)
            self.twin._cache.clear()
            self.bridge.flush()
            self._last_hw_tx_key = None
            
            # Find predicted score gain
            target_score = 0
            if 'ranking' in self.last_twin_payload:
                for r in self.last_twin_payload['ranking']:
                    if r['mod'] == best_mod:
                        target_score = r['score']
                        break
            predicted_gain = max(0, target_score - prev_score)
            
        data = {
            'from': prev_mod,
            'to': best_mod,
            'predicted_gain': predicted_gain,
            'prev_score': prev_score,
            'target_score': target_score
        }
        
        is_attack = getattr(self.config, 'fdia_active', False)
        if is_attack and prev_mod != best_mod and best_mod == 'FSK':
            self.fdia_mitigated_count += 1
            self.log_event("fdia_mitigated", f"Threat Safely Diverted: Autonomous migration to FSK non-coherent signaling (Mitigation #{self.fdia_mitigated_count})", {
                'from': prev_mod, 'to': 'FSK', 'mitigation_count': self.fdia_mitigated_count
            })
            
        self.log_event("apply", f"Twin Recommendation Applied: {prev_mod} -> {best_mod} (+{predicted_gain} pts)", data)
        if self.on_config_emit:
            self.on_config_emit({'config': self.config.to_dict(), 'cfg_version': self.cfg_version})
            
        return True, data

    def shuffle_params(self):
        """One-shot randomization of all 'R' parameters (POST /api/shuffle)."""
        self._randomize_step()

    def set_preset(self, preset_name: str) -> Tuple[bool, str]:
        """Apply named scenario preset (POST /api/preset)."""
        if preset_name not in PRESETS:
            return False, f"Unknown preset: {preset_name}"
            
        preset_cfg = get_preset_config(preset_name)
        with self.lock:
            self.active_scenario = preset_name
            self.config = preset_cfg
            self.cfg_version += 1
            self.rolling.reset(self.cfg_version)
            self.twin._cache.clear()
            self.bridge.flush()
            self._last_hw_tx_key = None
            
        sc_name = SCENARIO_METADATA.get(preset_name, {}).get('name', preset_name)
        self.log_event("preset", f"Scenario selected: {sc_name}")
        if self.on_config_emit:
            self.on_config_emit({
                'config': self.config.to_dict(),
                'cfg_version': self.cfg_version,
                'active_scenario': self.active_scenario
            })
            
        return True, f"Scenario {sc_name} loaded"

    def _terminal_log_fdia(self, event_type: str, details: Optional[Dict[str, Any]] = None):
        """Print prominent, formatted text logs directly to the Python console terminal."""
        details = details or {}
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        print("\n" + "=" * 76, flush=True)
        if event_type == "ATTACK_START":
            print(f" [FDIA ALERT] >>> MALICIOUS FALSE DATA INJECTION ATTACK ACTIVE <<<", flush=True)
            print(f" Timestamp    : {t_str}", flush=True)
            print(f" Trigger Type : {details.get('trigger', 'Manual Trigger')}", flush=True)
            print(f" Mechanism    : Swept Carrier Jamming (5 Hz, 1.5 kHz) + Pilot Phase Spoofing", flush=True)
            print(f" Physical Twin: Preamble PSR collapse (<1.5), CRC8 failure, Costas slips", flush=True)
        elif event_type == "ATTACK_STOP":
            print(f" [FDIA ALERT] --- FALSE DATA INJECTION ATTACK CEASED ---", flush=True)
            print(f" Timestamp    : {t_str}", flush=True)
            print(f" Trigger Type : {details.get('trigger', 'Manual Clear')}", flush=True)
            print(f" Status       : Channel restored to authentic link integrity", flush=True)
        elif event_type == "ANOMALY_DETECTED":
            print(f" [FDIA DETECTOR] >>> IN-BAND ANOMALY DETECTED IN SIGNAL STREAM <<<", flush=True)
            print(f" Timestamp    : {t_str}", flush=True)
            print(f" Modulation   : {details.get('mod')}", flush=True)
            print(f" Trust Score  : {details.get('trust', 0)}% (COLLAPSED)", flush=True)
            print(f" Telemetry    : PSR={details.get('psr', 0.0):.2f} | CRC_Valid={details.get('crc')} | EVM={details.get('evm', 0.0):.1f}% | BER={details.get('ber', 0.0):.4f}", flush=True)
        print("=" * 76 + "\n", flush=True)

    def set_fdia(self, active: bool, trigger: str = "Manual Attack Button") -> Tuple[bool, str]:
        """Toggle False Data Injection Attack (FDIA) simulation (POST /api/fdia)."""
        with self.lock:
            prev = getattr(self.config, 'fdia_active', False)
            self.config.fdia_active = bool(active)
            self.cfg_version += 1
            self.rolling.reset(self.cfg_version)
            self.twin._cache.clear()
            
        if prev != bool(active):
            if active:
                self.fdia_injected_count += 1
                self._terminal_log_fdia("ATTACK_START", {"trigger": trigger, "attack_count": self.fdia_injected_count})
                self.log_event("fdia_attack_start", f"Malicious FDIA Cyber Attack Injected ({trigger}) [Attack #{self.fdia_injected_count}]", {
                    'trigger': trigger, 'attack_count': self.fdia_injected_count
                })
            else:
                self._terminal_log_fdia("ATTACK_STOP", {"trigger": trigger})
                self.log_event("fdia_attack_stop", f"FDIA Attack Ceased ({trigger})", {'trigger': trigger})
                
        status_str = "ACTIVATED" if active else "DEACTIVATED"
        if self.on_config_emit:
            self.on_config_emit({
                'config': self.config.to_dict(),
                'cfg_version': self.cfg_version,
                'fdia_active': self.config.fdia_active
            })
            
        # Immediate twin evaluation on attack toggle so candidate scores update with 0 latency
        twin_res = self.twin.evaluate(self.config, scenario_preset=getattr(self, 'active_scenario', None))
        self.last_twin_payload = twin_res
        if self.on_twin_emit:
            self.on_twin_emit(twin_res)
            
        return True, f"FDIA {status_str}"

    def set_random_fdia(self, enabled: bool) -> Tuple[bool, str]:
        """Toggle pseudo-random interval FDIA burst injection (POST /api/fdia_random)."""
        with self.lock:
            self.random_fdia_enabled = bool(enabled)
            if not self.random_fdia_enabled and getattr(self.config, 'fdia_active', False):
                self.config.fdia_active = False
                self.cfg_version += 1
                self._terminal_log_fdia("ATTACK_STOP", {"trigger": "Random Attack Disabled"})
                
        status_str = "ENABLED" if enabled else "DISABLED"
        t_str = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[FDIA CONFIG] Random-Interval Attack Mode {status_str} at {t_str}\n", flush=True)
        self.log_event("fdia_random", f"Random Time FDIA {status_str}", {'random_fdia': self.random_fdia_enabled})
        if self.on_config_emit:
            self.on_config_emit({
                'random_fdia_enabled': self.random_fdia_enabled,
                'fdia_active': getattr(self.config, 'fdia_active', False)
            })
        return True, f"Random FDIA {status_str}"

    def set_mode(self, mode: str) -> Tuple[bool, str]:
        """Switch between 'sim' and 'pluto' (POST /api/mode)."""
        if mode not in ('sim', 'pluto'):
            return False, "Invalid mode, must be 'sim' or 'pluto'"
        with self.lock:
            self.mode = mode
            self.rolling.reset()
            self.bridge.flush()
            self._last_hw_tx_key = None
        if mode == 'pluto':
            self.bridge.ensure_bridge_running()
        self.log_event("mode_change", f"Operating mode set to {mode.upper()}")
        if self.on_config_emit:
            self.on_config_emit({'config': self.config.to_dict(), 'cfg_version': self.cfg_version, 'mode': self.mode})
        return True, f"Mode set to {mode}"

    def reset_stats(self):
        """Reset rolling metrics statistics (POST /api/reset_stats)."""
        with self.lock:
            self.rolling.reset()
        self.log_event("reset_stats", "Rolling telemetry statistics reset")

    def _randomize_step(self):
        """Randomize parameters bounded strictly within the active scenario's physical reality; keep modulation unchanged."""
        with self.lock:
            current_mod = self.config.modulation
            # Perturb physical channel bounded inside active scenario definition
            new_cfg = randomize_scenario(self.active_scenario, current_modulation=current_mod)
            # Preserve user FDIA state
            new_cfg.fdia_active = getattr(self.config, 'fdia_active', False)
            
            self.config = new_cfg
            self.cfg_version += 1
            self.rolling.reset()
            self.twin._cache.clear()
            self.bridge.flush()
            
            # Reset randomizer timer to exactly 25.0s
            self.randomizer_interval_s = 25.0
            self.randomizer_next_in_s = 25.0
            
            if self.autopilot_enabled:
                self._pending_autopilot_time = time.time() + 2.0
                
        sc_meta = SCENARIO_METADATA.get(self.active_scenario, {})
        sc_name = sc_meta.get('name', self.active_scenario)
        self.log_event("randomize", f"Signals randomized for {sc_name} (25.0s timer)", {
            'next_in_s': 25.0,
            'scenario': self.active_scenario
        })
        if self.on_config_emit:
            self.on_config_emit({
                'config': self.config.to_dict(),
                'cfg_version': self.cfg_version,
                'active_scenario': self.active_scenario
            })

    def _frame_loop(self):
        """Frame streaming loop at ~10 Hz."""
        while self.running:
            t_start = time.perf_counter()
            try:
                with self.lock:
                    cfg = TxConfig(**self.config.to_dict())
                    mode = self.mode
                    cfg_ver = self.cfg_version
                    
                plan = derive_link_plan(cfg)
                
                # Digital vs Analog execution
                if plan.is_digital:
                    tx_frame = self.modulator.generate_digital_frame(cfg)
                    rx_iq = None
                    rx_res = None
                    if mode == 'pluto' and self.bridge.link_up:
                        tx_key = (cfg.modulation, cfg.data_rate, cfg.rolloff, cfg.fsk_h, cfg.source_type, cfg.alloc_bw, getattr(cfg, 'fdia_active', False))
                        if tx_key != self._last_hw_tx_key:
                            self.bridge.send_tx(tx_frame.iq)
                            self._last_hw_tx_key = tx_key
                            time.sleep(0.04)
                            
                        rx_raw = self.bridge.get_recent_rx(max(16384, min(65536, int(len(tx_frame.iq) * 1.5))))
                        if len(rx_raw) >= 1024 and not np.all(rx_raw == 0):
                            if getattr(cfg, 'fdia_active', False):
                                rx_raw, _, _ = self.channel.apply_fdia_only(rx_raw, cfg)
                            rx_res_raw = self.receiver.demodulate_digital_frame(rx_raw, tx_frame, cfg)
                            rx_iq = rx_raw
                            rx_res = rx_res_raw
                    if rx_iq is None or rx_res is None:
                        rx_iq, _, _ = self.channel.apply(tx_frame.iq, cfg, sps=tx_frame.sps)
                        rx_res = self.receiver.demodulate_digital_frame(rx_iq, tx_frame, cfg)
                        
                    self.rolling.update_digital(cfg_ver, rx_res['bit_errors'], rx_res['bits_tested'], cfg.packet_bits, rx_res['evm_rms'])
                    metrics = MetricCalculator.compute_all_metrics(plan, cfg, rx_res, self.rolling, tx_frame.iq)
                    rec_const = rx_res['recovered_symbols']
                else:
                    tx_iq, msg, _ = self.modulator.generate_analog_signal(cfg, duration=0.04)
                    rx_iq = None
                    rx_res = None
                    if mode == 'pluto' and self.bridge.link_up:
                        tx_key = (cfg.modulation, cfg.msg_bw, cfg.am_index, cfg.fm_beta, cfg.source_type, cfg.alloc_bw, getattr(cfg, 'fdia_active', False))
                        if tx_key != self._last_hw_tx_key:
                            self.bridge.send_tx(tx_iq)
                            self._last_hw_tx_key = tx_key
                            time.sleep(0.04)
                            
                        rx_raw = self.bridge.get_recent_rx(max(16384, len(tx_iq) * 2))
                        if len(rx_raw) >= 1024 and not np.all(rx_raw == 0):
                            if getattr(cfg, 'fdia_active', False):
                                rx_raw, _, _ = self.channel.apply_fdia_only(rx_raw, cfg)
                            rx_res_raw = self.receiver.demodulate_analog_signal(rx_raw, msg, cfg)
                            rx_iq = rx_raw
                            rx_res = rx_res_raw
                    if rx_iq is None or rx_res is None:
                        rx_iq, _, _ = self.channel.apply(tx_iq, cfg)
                        rx_res = self.receiver.demodulate_analog_signal(rx_iq, msg, cfg)
                        
                    self.rolling.update_analog(cfg_ver, rx_res['output_snr_db'])
                    metrics = MetricCalculator.compute_all_metrics(plan, cfg, rx_res, self.rolling, tx_iq)
                    rec_const = rx_iq
                    
                score_res = Scorer.evaluate(plan, cfg, metrics)
                self.last_measured_score = score_res['total']
                
                # Terminal Anomaly Logging for FDIA events
                is_attack_active = getattr(cfg, 'fdia_active', False)
                now_t = time.time()
                if is_attack_active and (now_t - self._last_terminal_fdia_report >= 3.0):
                    self._last_terminal_fdia_report = now_t
                    self.fdia_detected_count += 1
                    self._terminal_log_fdia("ANOMALY_DETECTED", {
                        "mod": cfg.modulation,
                        "trust": metrics.get('trust_score', 0),
                        "psr": metrics.get('psr', 0.0),
                        "crc": rx_res.get('header_valid', False),
                        "evm": metrics.get('evm_rms', 0.0),
                        "ber": metrics.get('ber', 0.0),
                        "detection_count": self.fdia_detected_count
                    })
                    self.log_event("fdia_anomaly_detected", f"In-band Anomaly Identified on {cfg.modulation} (PSR={metrics.get('psr', 0.0):.2f}, Trust={metrics.get('trust_score', 0)}%) [Detection #{self.fdia_detected_count}]", {
                        'mod': cfg.modulation,
                        'trust': metrics.get('trust_score', 0),
                        'psr': metrics.get('psr', 0.0),
                        'detection_count': self.fdia_detected_count
                    })
                
                # Visualizations
                # 1. Constellation (Calibrated Decision-Directed Equalizer & VSA Slicer)
                if mode == 'pluto' and self.bridge.link_up and rx_res is not None:
                    # In Hardware-In-The-Loop mode, display the REAL measured over-the-air symbols!
                    rec_syms = rx_res.get('recovered_symbols')
                    if rec_syms is not None and len(rec_syms) >= 30:
                        pwr = float(np.mean(np.abs(rec_syms)**2))
                        sc = 1.0 / np.sqrt(max(1e-12, pwr))
                        norm_syms = rec_syms * sc
                        if len(norm_syms) > 400:
                            step = len(norm_syms) // 400
                            sub_pts = norm_syms[::step][:400]
                        else:
                            sub_pts = norm_syms
                        const_pts = [[round(float(np.real(s)), 4), round(float(np.imag(s)), 4)] for s in sub_pts]
                    else:
                        # Fallback for analog or unsynced: display downsampled baseband IQ
                        raw_sub = rx_iq[:1600:4]
                        pwr = float(np.mean(np.abs(raw_sub)**2))
                        sc = 1.0 / np.sqrt(max(1e-12, pwr))
                        const_pts = [[round(float(np.real(s) * sc), 4), round(float(np.imag(s) * sc), 4)] for s in raw_sub[:400]]
                else:
                    const_pts = AdaptiveEqualizer.synthesize_constellation(
                        cfg.modulation, cfg, metrics, rx_res, n_points=400,
                        active_scenario=getattr(self, 'active_scenario', None)
                    )
                    
                # 2. Welch PSD (256 bins)
                if len(rx_iq) >= 256:
                    f_axis, pxx = welch(rx_iq[:16384], fs=self.fs, nperseg=256, return_onesided=False)
                    psd_shift = np.fft.fftshift(pxx)
                    f_shift = np.fft.fftshift(f_axis)
                    psd_db = [round(float(10.0 * np.log10(max(1e-12, p))), 1) for p in psd_shift]
                    psd_range = [round(float(f_shift[0] / 1000.0), 1), round(float(f_shift[-1] / 1000.0), 1)]
                else:
                    psd_db = []
                    psd_range = [-500.0, 500.0]
                    
                # 3. Time domain IQ trace (up to 300 points)
                sub_iq = rx_iq[:300]
                iq_traces = {
                    'i': [round(float(np.real(s)), 3) for s in sub_iq],
                    'q': [round(float(np.imag(s)), 3) for s in sub_iq]
                }
                
                # 4. Eye diagram traces (Digital Nyquist Eye / Analog Audio Scope)
                eye_traces = AdaptiveEqualizer.synthesize_eye_traces(
                    cfg.modulation, cfg, metrics, rx_res,
                    tx_frame=tx_frame if plan.is_digital else None,
                    active_scenario=getattr(self, 'active_scenario', None)
                )
                            
                payload = {
                    't': round(time.time(), 3),
                    'cfg_version': cfg_ver,
                    'mod': cfg.modulation,
                    'config': cfg.to_dict(),
                    'source': mode,
                    'link_up': self.bridge.link_up if mode == 'pluto' else True,
                    'metrics': metrics,
                    'score': score_res,
                    'viz': {
                        'const': const_pts,
                        'psd_db': psd_db,
                        'psd_f': psd_range,
                        'eye': eye_traces,
                        'iq': iq_traces
                    }
                }
                
                self.last_frame_telemetry = payload
                if self.on_frame_emit:
                    self.on_frame_emit(payload)
                    
            except Exception as e:
                # Log frame error and keep engine resilient
                print(f"[Engine FrameLoop Error] {e}", flush=True)
                time.sleep(0.05)
                
            elapsed = time.perf_counter() - t_start
            sleep_time = max(0.01, 0.095 - elapsed)
            time.sleep(sleep_time)

    def _twin_loop(self):
        """Twin evaluation loop at ~1 Hz."""
        while self.running:
            t_start = time.perf_counter()
            try:
                with self.lock:
                    cfg = TxConfig(**self.config.to_dict())
                    mode = self.mode
                    
                ch_state = {}
                if mode == 'pluto' and self.bridge.link_up:
                    # Provide live measured metrics as channel state to digital twin
                    if self.last_frame_telemetry and 'metrics' in self.last_frame_telemetry:
                        m = self.last_frame_telemetry['metrics']
                        meas_snr = m.get('snr_est_db')
                        if meas_snr is not None and meas_snr > 0.0:
                            ch_state['snr_db'] = float(meas_snr)
                        else:
                            ch_state['snr_db'] = float(cfg.snr_db)
                        meas_cfo = m.get('cfo_est_hz')
                        if meas_cfo is not None and abs(meas_cfo) > 1.0:
                            ch_state['cfo_hz'] = float(meas_cfo)
                        else:
                            ch_state['cfo_hz'] = float(cfg.cfo_hz)
                        
                twin_res = self.twin.evaluate(cfg, channel_state=ch_state if ch_state else None, scenario_preset=getattr(self, 'active_scenario', None))
                
                # Calculate Twin Fidelity (predicted score vs measured score for current modulation)
                pred_score = 0
                for r in twin_res['ranking']:
                    if r['mod'] == cfg.modulation:
                        pred_score = r['score']
                        break
                        
                fidelity_err = abs(pred_score - self.last_measured_score)
                twin_res['fidelity'] = {
                    'pred_score': pred_score,
                    'measured_score': self.last_measured_score,
                    'error_pts': fidelity_err
                }
                
                self.last_twin_payload = twin_res
                if self.on_twin_emit:
                    self.on_twin_emit(twin_res)
                    
                # Continuous Closed-Loop Autopilot Monitoring:
                # Continuously monitors trust and reliability score every 1 second in both SIM and PLUTO modes.
                # Features a 4.0s dwell window, anti-ping-pong hysteresis, and persistent degradation confirmation.
                if self.autopilot_enabled:
                    now = time.time()
                    if now - self.last_adaptation_time >= 4.0:
                        best_mod = twin_res.get('best')
                        current_mod = cfg.modulation
                        if best_mod and best_mod != current_mod:
                            current_pred = 0
                            best_pred = 0
                            for r in twin_res.get('ranking', []):
                                if r['mod'] == current_mod:
                                    current_pred = r['score']
                                elif r['mod'] == best_mod:
                                    best_pred = r['score']
                            
                            # Anti-ping-pong: if best_mod is the one we just switched away from,
                            # require a very high hurdle (12 pts) to avoid rapid oscillation
                            is_reversal = (best_mod == self._last_adapted_from)
                            hysteresis = 12 if is_reversal else 6
                            
                            should_adapt = False
                            # 1. Clear predicted superiority (>= 6 pts advantage, or 12 pts for reversal)
                            if best_pred >= current_pred + hysteresis:
                                should_adapt = True
                                self._suboptimal_count = 0
                            # 2. FDIA attack defense: switch to FSK to mitigate jamming
                            elif getattr(cfg, 'fdia_active', False) and current_mod != 'FSK' and best_mod == 'FSK':
                                should_adapt = True
                                self._suboptimal_count = 0
                            # 3. Persistent degradation: measured score genuinely low (< 65) for 3 consecutive checks
                            elif self.last_measured_score < 65 and best_pred >= current_pred + 4:
                                self._suboptimal_count += 1
                                if self._suboptimal_count >= 3:
                                    should_adapt = True
                                    self._suboptimal_count = 0
                            else:
                                self._suboptimal_count = max(0, self._suboptimal_count - 1)
                                
                            if should_adapt:
                                self._last_adapted_from = current_mod
                                self._last_adapted_to = best_mod
                                self.last_adaptation_time = now
                                self._pending_autopilot_time = None
                                self.apply_best()
                    
            except Exception as e:
                time.sleep(0.5)
                
            elapsed = time.perf_counter() - t_start
            sleep_time = max(0.1, 1.0 - elapsed)
            time.sleep(sleep_time)

    def _randomizer_loop(self):
        """Countdown and execution loop for auto-randomization and autopilot."""
        last_tick = time.time()
        while self.running:
            time.sleep(0.2)
            now = time.time()
            dt = now - last_tick
            last_tick = now
            
            # Autopilot trigger (handled with full hysteresis in _twin_loop)
            if self.autopilot_enabled and self._pending_autopilot_time:
                if now >= self._pending_autopilot_time:
                    self._pending_autopilot_time = None
                    
            if not self.randomizer_enabled:
                continue
                
            self.randomizer_next_in_s -= dt
            if self.randomizer_next_in_s <= 0.0:
                self._randomize_step()

    def _random_fdia_loop(self):
        """Pseudo-random interval FDIA burst injection thread."""
        import random
        while self.running:
            time.sleep(0.5)
            if not self.random_fdia_enabled:
                continue
                
            # Random quiet period between attacks: 8.0 to 18.0 seconds
            quiet_s = random.uniform(8.0, 18.0)
            t_quiet_end = time.time() + quiet_s
            while self.running and self.random_fdia_enabled and time.time() < t_quiet_end:
                self.random_fdia_next_s = max(0.0, t_quiet_end - time.time())
                time.sleep(0.2)
                
            if not self.running or not self.random_fdia_enabled:
                continue
                
            # Inject burst attack: random duration 5.0 to 12.0 seconds
            burst_s = random.uniform(5.0, 12.0)
            self.set_fdia(True, trigger=f"Random Timer Burst ({burst_s:.1f}s)")
            
            t_burst_end = time.time() + burst_s
            while self.running and self.random_fdia_enabled and time.time() < t_burst_end:
                self.random_fdia_next_s = max(0.0, t_burst_end - time.time())
                time.sleep(0.2)
                
            if self.random_fdia_enabled:
                self.set_fdia(False, trigger="Random Timer Burst Expired")
