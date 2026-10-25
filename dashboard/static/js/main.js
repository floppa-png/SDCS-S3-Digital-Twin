// Core API Client with strict application/json enforcement
class ApiClient {
  async post(endpoint, data = {}) {
    try {
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      return await resp.json();
    } catch (e) {
      console.error(`API Error on ${endpoint}:`, e);
      return null;
    }
  }

  async get(endpoint) {
    try {
      const resp = await fetch(endpoint);
      return await resp.json();
    } catch (e) {
      console.error(`API Error on ${endpoint}:`, e);
      return null;
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const api = new ApiClient();
  const charts = new DashboardCharts();
  const viz = new DashboardVisualizers();
  const controls = new DashboardControls(api);

  let currentModulation = 'BPSK';
  let bestModulation = 'BPSK';
  let lastScore = 0;
  let lastGrade = 'A';
  let frameCount = 0;
  let lastFpsTime = performance.now();
  let knownScenarios = {};

  // Socket.IO Connection
  const socket = io({
    transports: ['websocket', 'polling']
  });

  socket.on('connect', () => {
    console.log('[Socket] Connected to backend');
    addLogEntry('Connected to SDCS Digital Twin telemetry backend');
  });

  // 1. Initial State Snapshot
  socket.on('state', (state) => {
    if (!state) return;
    controls.syncFormValues(state.config);

    if (state.config && state.config.modulation) {
      selectHeroCard(state.config.modulation);
    }

    if (state.scenarios) {
      knownScenarios = state.scenarios;
    }
    if (state.active_scenario) {
      updateScenarioBadge(state.active_scenario, knownScenarios);
    }

    if (typeof state.fdia_active === 'boolean') {
      controls.syncFdiaButton(state.fdia_active);
    }

    if (state.random_fdia) {
      controls.syncRandomFdiaButton(state.random_fdia.enabled, state.random_fdia.next_in_s);
    }

    // Randomizer state
    const dotRand = document.getElementById('dot-randomizer');
    if (dotRand) {
      if (state.randomizer?.enabled) dotRand.classList.add('active');
      else dotRand.classList.remove('active');
    }

    // Autopilot state
    if (typeof state.autopilot === 'boolean') {
      controls.syncAutopilotButton(state.autopilot);
    }

    // Mode state
    const btnSim = document.getElementById('btn-mode-sim');
    const btnPluto = document.getElementById('btn-mode-pluto');
    if (btnSim && btnPluto) {
      if (state.mode === 'pluto') {
        btnPluto.classList.add('active');
        btnSim.classList.remove('active');
      } else {
        btnSim.classList.add('active');
        btnPluto.classList.remove('active');
      }
    }
  });

  // Config Update Broadcast
  socket.on('config', (cfgPayload) => {
    if (!cfgPayload) return;
    if (cfgPayload.config) {
      controls.syncFormValues(cfgPayload.config);
      if (cfgPayload.config.modulation) {
        selectHeroCard(cfgPayload.config.modulation);
      }
      if (typeof cfgPayload.config.fdia_active === 'boolean') {
        controls.syncFdiaButton(cfgPayload.config.fdia_active);
      }
    }
    if (typeof cfgPayload.fdia_active === 'boolean') {
      controls.syncFdiaButton(cfgPayload.fdia_active);
    }
    if (typeof cfgPayload.random_fdia_enabled === 'boolean') {
      controls.syncRandomFdiaButton(cfgPayload.random_fdia_enabled);
    }
    if (cfgPayload.active_scenario) {
      updateScenarioBadge(cfgPayload.active_scenario, knownScenarios);
    }
  });

  // 2. High-Rate Telemetry (~10 Hz)
  socket.on('frame', (frame) => {
    if (!frame) return;

    // Track active modulation in sync with backend
    if (frame.mod && frame.mod !== currentModulation) {
      currentModulation = frame.mod;
      selectHeroCard(frame.mod);
    }

    // Track FPS
    frameCount++;
    const now = performance.now();
    if (now - lastFpsTime >= 1000) {
      const fps = Math.round((frameCount * 1000) / (now - lastFpsTime));
      const fpsEl = document.getElementById('val-fps');
      if (fpsEl) fpsEl.textContent = `${fps} FPS`;
      frameCount = 0;
      lastFpsTime = now;
    }

    // Link status
    const labelLink = document.getElementById('label-link');
    const dotLink = document.getElementById('dot-link');
    if (labelLink && dotLink) {
      if (frame.source === 'pluto') {
        if (frame.link_up) {
          dotLink.classList.add('active');
          labelLink.textContent = 'PLUTO: LINK UP';
        } else {
          dotLink.classList.remove('active');
          labelLink.textContent = 'PLUTO: CONNECTING...';
        }
      } else {
        dotLink.classList.remove('active');
        labelLink.textContent = 'PLUTO: SIM';
      }
    }

    // Score & Gauge Updates
    if (frame.score) {
      const scoreTotal = frame.score.total;
      lastScore = scoreTotal;
      lastGrade = frame.score.grade;
      const scoreEl = document.getElementById('val-score-total');
      const gradeEl = document.getElementById('val-score-grade');
      const gaugeCircle = document.getElementById('gauge-circle-progress');

      if (scoreEl) scoreEl.textContent = scoreTotal;
      if (gradeEl) {
        gradeEl.textContent = `GRADE ${frame.score.grade}`;
        gradeEl.style.color = getGradeColor(frame.score.grade);
      }

      if (gaugeCircle) {
        // Circumference for r=70 is 2*PI*70 ≈ 440
        const circumference = 440;
        const offset = circumference - (scoreTotal / 100) * circumference;
        gaugeCircle.style.strokeDashoffset = offset;
        gaugeCircle.style.stroke = getGradeColor(frame.score.grade);
      }

      // Real-time synchronization of active modulation card badge with the big gauge!
      const activeBadge = document.getElementById(`badge-score-${frame.mod}`);
      if (activeBadge) {
        activeBadge.textContent = `${scoreTotal} PTS`;
        activeBadge.style.color = getGradeColor(frame.score.grade);
      }

      // Update 6 Sub-scores
      if (frame.score.subs) {
        const s = frame.score.subs;
        updateSubScore('rel', s.rel);
        updateSubScore('rate', s.rate);
        updateSubScore('bw', s.bw);
        updateSubScore('pwr', s.pwr);
        updateSubScore('cplx', s.cplx);
        updateSubScore('papr', s.papr);
      }

      charts.addScorePoint(scoreTotal);
    }

    // Metric Tiles
    if (frame.metrics) {
      const m = frame.metrics;
      setText('lbl-ber', m.is_digital ? 'BER' : 'SNR (Output)');
      setText('val-ber', m.is_digital ? formatBer(m.ber) : `${m.output_snr_db?.toFixed(1) || '--'} dB`);
      setText('val-theory-ber', m.is_digital ? formatBer(m.theory_ber) : `${m.theory_snr_db?.toFixed(1) || '--'} dB`);
      setText('val-per', `${((m.per || 0) * 100).toFixed(1)}%`);
      setText('val-goodput', `${((m.goodput_bps || 0) / 1000).toFixed(1)}`);
      setText('val-ebn0', m.is_digital ? `${m.ebn0_db?.toFixed(1) || '--'} dB` : `${m.gamma_analog_db?.toFixed(1) || '--'} dB`);
      setText('val-link-margin', `${m.link_margin_db?.toFixed(1) || '--'}`);
      setText('val-snr-meas', typeof m.snr_est_db === 'number' ? `${m.snr_est_db.toFixed(1)} dB` : '-- dB');
      setText('val-snr-set', typeof frame.config?.snr_db === 'number' ? frame.config.snr_db.toFixed(1) : '--');
      setText('val-evm', m.is_digital ? `${m.evm_rms?.toFixed(1) || '--'}%` : 'N/A');
      setText('val-papr', `${m.papr_db?.toFixed(1) || '--'}`);
      setText('val-obw', `${((m.obw_99 || 0) / 1000).toFixed(1)} kHz`);
      setText('val-alloc-bw-metric', `${((m.alloc_bw || 60000) / 1000).toFixed(0)}`);
      setText('val-spectral-eff', `${(m.spectral_efficiency || 0).toFixed(2)} b/s/Hz`);
      setText('val-shannon-cap', `${((m.shannon_cap_bps || 0) / 1000).toFixed(1)}`);
      setText('val-cfo-est', `${Math.round(m.cfo_est_hz || 0)} Hz`);

      // Cyber-Physical Trust Score & FDIA Attack Status
      const trust = typeof m.trust_score === 'number' ? m.trust_score : 100;
      const isAttackActive = Boolean(frame.config?.fdia_active);
      const isMitigated = Boolean(m.fdia_mitigated);
      
      // Header Trust Pill
      setText('val-trust-score', `${trust}%`);
      const dotTrust = document.getElementById('dot-trust');
      if (dotTrust) {
        if (trust >= 80) {
          dotTrust.style.background = 'var(--good)';
          dotTrust.style.boxShadow = '0 0 8px var(--good)';
        } else if (trust >= 50) {
          dotTrust.style.background = 'var(--warn)';
          dotTrust.style.boxShadow = '0 0 8px var(--warn)';
        } else {
          dotTrust.style.background = 'var(--bad)';
          dotTrust.style.boxShadow = '0 0 10px var(--bad)';
        }
      }

      // 1. Live Signal Stream Integrity Alarm Banner in FDIA Detector Suite
      const streamBanner = document.getElementById('stream-status-banner');
      const streamIcon = document.getElementById('stream-icon');
      const streamHeadline = document.getElementById('stream-headline');
      const streamDetail = document.getElementById('stream-detail');
      const tagStream = document.getElementById('tag-det-stream');

      if (streamBanner) {
        if (isAttackActive && !isMitigated) {
          streamBanner.classList.remove('secure', 'mitigated');
          streamBanner.classList.add('attack');
          if (streamIcon) streamIcon.textContent = '⚠️';
          if (streamHeadline) streamHeadline.textContent = 'MALICIOUS FDIA ATTACK DETECTED IN CURRENT SIGNAL STREAM!';
          if (streamDetail) streamDetail.textContent = 'Swept jamming tone & adversarial pilot spoofing active. Preamble correlation collapsed, CRC failing, trust degraded.';
          if (tagStream) {
            tagStream.textContent = 'FDIA DETECTED (JAMMING)';
            tagStream.className = 'det-tag alert';
          }
        } else if (isAttackActive && isMitigated) {
          streamBanner.classList.remove('attack', 'secure');
          streamBanner.classList.add('mitigated');
          if (streamIcon) streamIcon.textContent = '🛡️';
          if (currentModulation === 'FM') {
            if (streamHeadline) streamHeadline.textContent = 'FDIA ATTACK DETECTED · FM LIMITER CAPTURE EFFECT MITIGATING LINK';
            if (streamDetail) streamDetail.textContent = `Adversarial swept jamming active in carrier band. Receiver hard-limiter rejects amplitude interference via FM capture effect (Trust: ${trust}%).`;
            if (tagStream) {
              tagStream.textContent = 'ATTACK MITIGATED (FM)';
              tagStream.className = 'det-tag warn';
            }
          } else {
            if (streamHeadline) streamHeadline.textContent = 'FDIA ATTACK DETECTED · FSK TONE ORTHOGONALITY MITIGATING LINK';
            if (streamDetail) streamDetail.textContent = `Adversarial swept jamming active in carrier band. Receiver dual-tone energy detection successfully rejects carrier interference (Trust: ${trust}%).`;
            if (tagStream) {
              tagStream.textContent = 'ATTACK MITIGATED (FSK)';
              tagStream.className = 'det-tag warn';
            }
          }
        } else {
          streamBanner.classList.remove('attack', 'mitigated');
          streamBanner.classList.add('secure');
          if (streamIcon) streamIcon.textContent = '🛡️';
          if (streamHeadline) streamHeadline.textContent = 'AUTHENTIC SIGNAL STREAM · INTEGRITY VERIFIED (NO ATTACK)';
          if (streamDetail) streamDetail.textContent = 'No False Data Injection detected in current stream. Preamble correlation and header integrity match authentic transceiver profile.';
          if (tagStream) {
            tagStream.textContent = 'AUTHENTIC STREAM';
            tagStream.className = 'det-tag secure';
          }
        }
      }

      // 2. Anomaly Telemetry in Detector Suite
      setText('val-det-trust', `${trust}%`);
      const barDetTrust = document.getElementById('bar-det-trust');
      if (barDetTrust) {
        barDetTrust.style.width = `${Math.max(0, Math.min(100, trust))}%`;
        barDetTrust.style.background = trust >= 75 ? 'var(--good)' : (trust >= 50 ? 'var(--warn)' : 'var(--bad)');
      }

      const tagPsr = document.getElementById('tag-det-psr');
      if (tagPsr) {
        const psrVal = m.psr || 5.0;
        if (isAttackActive && !isMitigated) {
          tagPsr.textContent = `COLLAPSED · ${psrVal.toFixed(1)}x`;
          tagPsr.className = 'det-tag alert';
        } else if (isAttackActive && isMitigated) {
          tagPsr.textContent = `FSK DISCRIM · ${psrVal.toFixed(1)}x`;
          tagPsr.className = 'det-tag warn';
        } else {
          tagPsr.textContent = `NOMINAL · ${psrVal.toFixed(1)}x`;
          tagPsr.className = 'det-tag secure';
        }
      }

      const tagCrc = document.getElementById('tag-det-crc');
      if (tagCrc) {
        if (isAttackActive && !isMitigated) {
          tagCrc.textContent = 'MISMATCH (FAIL)';
          tagCrc.className = 'det-tag alert';
        } else if (isAttackActive && isMitigated) {
          tagCrc.textContent = 'PROTECTED (PASS)';
          tagCrc.className = 'det-tag warn';
        } else {
          tagCrc.textContent = 'VALID (MATCH)';
          tagCrc.className = 'det-tag secure';
        }
      }

      // Metric Tile Trust
      setText('val-tile-trust', `${trust}%`);
      const fdiaStatusEl = document.getElementById('val-fdia-status');
      const tileTrust = document.getElementById('tile-trust');
      if (fdiaStatusEl) {
        if (isAttackActive && !isMitigated) {
          fdiaStatusEl.textContent = 'ATTACK DETECTED (FDIA)';
          fdiaStatusEl.style.color = 'var(--bad)';
          if (tileTrust) tileTrust.classList.add('under-attack');
        } else if (isAttackActive && isMitigated) {
          fdiaStatusEl.textContent = 'FDIA DETECTED (MITIGATED)';
          fdiaStatusEl.style.color = 'var(--warn)';
          if (tileTrust) tileTrust.classList.remove('under-attack');
        } else {
          fdiaStatusEl.textContent = 'SECURE · NO ATTACK';
          fdiaStatusEl.style.color = 'var(--good)';
          if (tileTrust) tileTrust.classList.remove('under-attack');
        }
      }
    }

    // Visualizations
    if (frame.viz) {
      const isAttackActive = Boolean(frame.config?.fdia_active || (frame.metrics && frame.metrics.trust_score < 60));
      viz.renderConstellation(frame.viz.const, frame.mod, MOD_COLORS[frame.mod], isAttackActive);
      viz.renderSpectrum(frame.viz.psd_db, frame.viz.psd_f, (frame.metrics?.alloc_bw || 60000) / 1000);
      viz.renderEyeDiagram(frame.viz.eye, isAttackActive);
      viz.renderIqTrace(frame.viz.iq);

      // Dynamic Eye / Scope Header Update based on Modulation
      const eyeTitleEl = document.getElementById('label-eye-title');
      const eyeSubEl = document.getElementById('label-eye-sub');
      if (eyeTitleEl && eyeSubEl) {
        const isAnalog = ['AM_DSBSC', 'AM_DSBTC', 'FM'].includes(frame.mod);
        if (isAnalog) {
          eyeTitleEl.textContent = 'Audio Waveform Scope (Demodulated)';
          eyeSubEl.textContent = 'Baseband Audio';
        } else {
          eyeTitleEl.textContent = 'Eye Diagram (2 Symbol Span)';
          eyeSubEl.textContent = 'In-Phase';
        }
      }
    }
  });

  // 3. Digital Twin Evaluation (~1 Hz)
  socket.on('twin', (twin) => {
    if (!twin) return;

    // Twin eval time
    const twinTimeEl = document.getElementById('val-twin-time');
    if (twinTimeEl) twinTimeEl.textContent = `${twin.eval_time_ms} ms`;

    // Fidelity readout
    const fidEl = document.getElementById('label-fidelity');
    if (fidEl && twin.fidelity) {
      fidEl.textContent = `Twin ±${twin.fidelity.error_pts} pts`;
    }

    // Recommendation card
    bestModulation = twin.best;
    const recText = document.getElementById('twin-rec-text');
    const recRationale = document.getElementById('twin-rec-rationale');
    const recDetails = document.getElementById('twin-rec-details');
    const btnApply = document.getElementById('btn-apply-best');

    if (recText) {
      if (currentModulation === bestModulation) {
        recText.textContent = `Operating on optimal modulation: ${bestModulation}`;
        if (btnApply) {
          btnApply.disabled = true;
          btnApply.classList.remove('btn-pulse');
        }
      } else {
        // Find predicted score
        let bestScore = 0;
        let gain = 0;
        for (const r of twin.ranking) {
          if (r.mod === bestModulation) {
            bestScore = r.score;
            gain = Math.max(0, bestScore - lastScore);
            break;
          }
        }
        recText.textContent = `Switch ${currentModulation} → ${bestModulation} · +${gain} pts predicted gain`;
        if (btnApply) {
          btnApply.disabled = false;
          if (gain >= 10) btnApply.classList.add('btn-pulse');
          else btnApply.classList.remove('btn-pulse');
        }
      }
    }

    if (recRationale) {
      recRationale.textContent = `Physical Rationale: ${twin.rationale || 'Optimizing Euclidean distance and receiver loop tracking under active channel constraints.'}`;
    }

    if (recDetails) {
      recDetails.textContent = `Confidence: ${twin.confidence}% · Physical Twin Optimization Engine`;
    }

    // Update Hero Cards (Badges, disabled states, TWIN PICK ribbons)
    if (twin.ranking) {
      twin.ranking.forEach(r => {
        const card = document.getElementById(`card-mod-${r.mod}`);
        const badge = document.getElementById(`badge-score-${r.mod}`);

        if (card) {
          if (r.mod === bestModulation) card.classList.add('is-twin-pick');
          else card.classList.remove('is-twin-pick');

          if (!r.applicable) {
            card.classList.add('disabled');
            card.title = r.reason || "Not applicable";
          } else {
            card.classList.remove('disabled');
            card.title = "";
          }
        }

        if (badge) {
          if (r.mod === currentModulation) {
            // Active modulation: show live measured score (same as big gauge)
            badge.textContent = r.applicable ? `${lastScore} PTS` : 'N/A';
            badge.style.color = r.applicable ? getGradeColor(lastGrade || r.grade) : 'var(--text-dim)';
          } else {
            // Inactive modulations: show twin's predicted score
            badge.textContent = r.applicable ? `${r.score} PTS` : 'N/A';
            badge.style.color = r.applicable ? getGradeColor(r.grade) : 'var(--text-dim)';
          }
        }
      });

      charts.updateRanking(twin.ranking, currentModulation, bestModulation);
    }

    // Update BER curves
    if (twin.curves) {
      charts.updateBerCurves(twin.curves);
    }
  });

  // 4. Config & Version Updates
  socket.on('config', (data) => {
    if (!data || !data.config) return;
    controls.syncFormValues(data.config);
    if (data.config.modulation) {
      selectHeroCard(data.config.modulation);
    }
    if (data.active_scenario) {
      updateScenarioBadge(data.active_scenario, knownScenarios);
    }
    if (typeof data.fdia_active === 'boolean') {
      controls.syncFdiaButton(data.fdia_active);
    }
  });

  // 5. System Events Log
  socket.on('event', (ev) => {
    if (!ev) return;
    addLogEntry(ev.message, ev.time);

    // If event is an optimization apply, add marker line to timeline chart
    if (ev.type === 'apply') {
      const label = `APPLY ${ev.data?.from || ''}→${ev.data?.to || ''}`;
      charts.addScorePoint(lastScore, label);
    } else if (ev.type === 'randomize') {
      charts.addScorePoint(lastScore, 'RANDOMIZE');
      // Update countdown ring with 25.0s
      animateCountdown(ev.data?.next_in_s || 25.0);
    } else if (ev.type === 'preset') {
      charts.addScorePoint(lastScore, 'SCENARIO');
    } else if (ev.type === 'fdia') {
      charts.addScorePoint(lastScore, ev.data?.fdia_active ? 'FDIA ATTACK' : 'FDIA CLEARED');
    }
  });

  // Helpers
  function selectHeroCard(mod) {
    currentModulation = mod;
    const cards = document.querySelectorAll('.mod-card');
    cards.forEach(c => {
      if (c.getAttribute('data-mod') === mod) c.classList.add('selected');
      else c.classList.remove('selected');
    });

    const constLabel = document.getElementById('label-const-mod');
    if (constLabel) {
      constLabel.textContent = mod;
      constLabel.style.color = MOD_COLORS[mod] || '#22d3ee';
    }
  }

  function updateSubScore(key, val) {
    const bar = document.getElementById(`bar-sub-${key}`);
    const txt = document.getElementById(`val-sub-${key}`);
    const pct = Math.round(Math.max(0, Math.min(1, val || 0)) * 100);
    if (bar) bar.style.width = `${pct}%`;
    if (txt) txt.textContent = `${pct}%`;
  }

  function formatBer(ber) {
    if (ber === undefined || ber === null) return '--';
    if (ber === 0) return '< 1e-9';
    if (ber >= 0.1) return ber.toFixed(3);
    return ber.toExponential(2);
  }

  function getGradeColor(grade) {
    if (grade === 'A+' || grade === 'A') return 'var(--good)';
    if (grade === 'B') return 'var(--color-bpsk)';
    if (grade === 'C') return 'var(--warn)';
    return 'var(--bad)';
  }

  function addLogEntry(message, timeStr = null) {
    const container = document.getElementById('event-log-container');
    if (!container) return;

    const entry = document.createElement('div');
    entry.className = 'log-entry';

    const t = document.createElement('span');
    t.className = 'log-time';
    t.textContent = timeStr || new Date().toLocaleTimeString();

    const m = document.createElement('span');
    m.className = 'log-msg';
    m.textContent = message;

    entry.appendChild(t);
    entry.appendChild(m);

    container.insertBefore(entry, container.firstChild);
    while (container.children.length > 20) {
      container.removeChild(container.lastChild);
    }
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function animateCountdown(durationSec) {
    const ring = document.getElementById('ring-countdown-progress');
    const label = document.getElementById('label-countdown');
    if (!ring || !label) return;

    const circumference = 63; // 2 * PI * 10 ≈ 62.8
    const startTime = performance.now();
    const durationMs = durationSec * 1000;

    function frame(now) {
      const elapsed = now - startTime;
      const remaining = Math.max(0, (durationMs - elapsed) / 1000);
      label.textContent = `${remaining.toFixed(1)}s`;

      const progress = Math.min(1, elapsed / durationMs);
      const offset = circumference * progress;
      ring.style.strokeDashoffset = offset;

      if (elapsed < durationMs) {
        requestAnimationFrame(frame);
      } else {
        label.textContent = '0.0s';
      }
    }
    requestAnimationFrame(frame);
  }

  function updateScenarioBadge(key, scenarios) {
    if (!key) return;
    const meta = (scenarios && scenarios[key]) || {};
    const name = meta.name || key;
    const tag = meta.type_label || (meta.category === 'analog' ? 'ANALOG' : 'DIGITAL');
    setText('label-scenario-name', name);
    setText('label-scenario-tag', tag);
  }
});
