class DashboardControls {
  constructor(apiClient) {
    this.api = apiClient;
    this.debounceTimer = null;
    this.pendingUpdates = {};
    
    this.initParamBindings();
    this.initHeroCards();
    this.initToolbarControls();
    this.initDossierModal();
  }

  initParamBindings() {
    // Map of slider to number input and readout span
    const params = [
      'data_rate', 'msg_bw', 'pcm_bits', 'alloc_bw', 'rolloff',
      'snr_db', 'k_factor_db', 'doppler_hz', 'cfo_hz', 'phase_noise_deg',
      'am_index', 'fm_beta', 'fsk_h', 'target_snr_out'
    ];

    params.forEach(param => {
      const rangeEl = document.getElementById(`range-${param}`);
      const numEl = document.getElementById(`num-${param}`);
      const readoutEl = document.getElementById(`readout-${param}`);

      if (rangeEl && numEl) {
        rangeEl.addEventListener('input', (e) => {
          const val = parseFloat(e.target.value);
          numEl.value = val;
          if (readoutEl) readoutEl.textContent = val;
          this.queueConfigUpdate(param, val);
        });

        numEl.addEventListener('change', (e) => {
          const val = parseFloat(e.target.value);
          rangeEl.value = val;
          if (readoutEl) readoutEl.textContent = val;
          this.queueConfigUpdate(param, val);
        });
      }
    });

    // Dropdowns
    const selectSource = document.getElementById('input-source_type');
    if (selectSource) {
      selectSource.addEventListener('change', (e) => {
        const val = e.target.value;
        const readout = document.getElementById('readout-source_type');
        if (readout) readout.textContent = val;
        this.updateVisibility(val, null);
        this.queueConfigUpdate('source_type', val);
      });
    }

    const selectChannel = document.getElementById('input-channel');
    if (selectChannel) {
      selectChannel.addEventListener('change', (e) => {
        const val = e.target.value;
        const readout = document.getElementById('readout-channel');
        if (readout) readout.textContent = val;
        this.updateVisibility(null, val);
        this.queueConfigUpdate('channel', val);
      });
    }

    const selectProfile = document.getElementById('input-profile');
    if (selectProfile) {
      selectProfile.addEventListener('change', (e) => {
        const val = e.target.value;
        const readout = document.getElementById('readout-profile');
        if (readout) readout.textContent = val;
        this.queueConfigUpdate('profile', val);
      });
    }

    const selectBer = document.getElementById('select-target_ber');
    if (selectBer) {
      selectBer.addEventListener('change', (e) => {
        const val = parseFloat(e.target.value);
        const readout = document.getElementById('readout-target_ber');
        if (readout) readout.textContent = val.toExponential(0);
        this.queueConfigUpdate('target_ber', val);
      });
    }
  }

  queueConfigUpdate(key, value) {
    this.pendingUpdates[key] = value;
    if (this.debounceTimer) clearTimeout(this.debounceTimer);

    this.debounceTimer = setTimeout(() => {
      this.flushConfigUpdates();
    }, 250);
  }

  flushConfigUpdates() {
    if (Object.keys(this.pendingUpdates).length === 0) return;
    const payload = { ...this.pendingUpdates };
    this.pendingUpdates = {};

    this.api.post('/api/config', payload).then(res => {
      if (res && res.errors) {
        console.warn('Parameter validation error:', res.errors);
      }
    });
  }

  updateVisibility(sourceType, channelType) {
    if (sourceType) {
      const isAnalog = sourceType === 'analog';
      const digitalEls = ['item-data_rate', 'item-target_ber', 'item-fsk_h'];
      const analogEls = ['item-msg_bw', 'item-pcm_bits', 'item-am_index', 'item-fm_beta', 'item-target_snr_out'];

      digitalEls.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = isAnalog ? 'none' : 'flex';
      });

      analogEls.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = isAnalog ? 'flex' : 'none';
      });
    }

    if (channelType) {
      const kFactorEl = document.getElementById('item-k_factor');
      if (kFactorEl) {
        kFactorEl.style.display = channelType === 'rician' ? 'flex' : 'none';
      }
    }
  }

  initHeroCards() {
    const cards = document.querySelectorAll('.mod-card');
    cards.forEach(card => {
      card.addEventListener('click', () => {
        if (card.classList.contains('disabled')) return;
        const mod = card.getAttribute('data-mod');
        if (!mod) return;

        // Immediate optimistic UI selection for instant visual feedback
        cards.forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');

        this.api.post('/api/modulation', { modulation: mod }).then(res => {
          if (res && res.error) {
            console.warn('Modulation switch blocked:', res.error);
          }
        });
      });
    });
  }

  initToolbarControls() {
    // Mode toggles (Sim vs Pluto)
    const btnSim = document.getElementById('btn-mode-sim');
    const btnPluto = document.getElementById('btn-mode-pluto');
    if (btnSim && btnPluto) {
      btnSim.addEventListener('click', () => {
        this.api.post('/api/mode', { mode: 'sim' }).then(() => {
          btnSim.classList.add('active');
          btnPluto.classList.remove('active');
        });
      });

      btnPluto.addEventListener('click', () => {
        this.api.post('/api/mode', { mode: 'pluto' }).then(() => {
          btnPluto.classList.add('active');
          btnSim.classList.remove('active');
        });
      });
    }

    // Auto-randomizer toggle
    const btnRandomizer = document.getElementById('btn-toggle-randomizer');
    if (btnRandomizer) {
      btnRandomizer.addEventListener('click', () => {
        const dot = document.getElementById('dot-randomizer');
        const isCurrentlyActive = dot ? dot.classList.contains('active') : false;
        const nextState = !isCurrentlyActive;

        this.api.post('/api/randomize', { enabled: nextState }).then(res => {
          if (dot) {
            if (nextState) dot.classList.add('active');
            else dot.classList.remove('active');
          }
        });
      });
    }

    // Shuffle button
    const btnShuffle = document.getElementById('btn-shuffle');
    if (btnShuffle) {
      btnShuffle.addEventListener('click', () => {
        this.api.post('/api/shuffle', {});
      });
    }

    // Autopilot toggle
    const btnAutopilot = document.getElementById('btn-toggle-autopilot');
    if (btnAutopilot) {
      btnAutopilot.addEventListener('click', () => {
        const dot = document.getElementById('dot-autopilot');
        const isCurrentlyActive = dot ? dot.classList.contains('active') : false;
        const nextState = !isCurrentlyActive;

        this.api.post('/api/autopilot', { enabled: nextState }).then(res => {
          if (res && res.status === 'ok') {
            this.syncAutopilotButton(res.autopilot);
          }
        });
      });
    }

    // Manual FDIA Attack Toggle (bind all buttons)
    const manualAttackBtns = [
      document.getElementById('btn-manual-attack'),
      document.getElementById('btn-toolbar-fdia-manual'),
      document.getElementById('btn-toggle-fdia')
    ].filter(Boolean);

    manualAttackBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const isCurrentlyActive = btn.classList.contains('active');
        const nextState = !isCurrentlyActive;

        this.api.post('/api/fdia', { active: nextState }).then(res => {
          if (res && res.status === 'ok') {
            this.syncFdiaButton(res.fdia_active);
          }
        });
      });
    });

    // Random Time FDIA Attack Toggle (bind all buttons)
    const randomAttackBtns = [
      document.getElementById('btn-random-attack'),
      document.getElementById('btn-toolbar-fdia-random')
    ].filter(Boolean);

    randomAttackBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const isCurrentlyActive = btn.classList.contains('active');
        const nextState = !isCurrentlyActive;

        this.api.post('/api/fdia_random', { enabled: nextState }).then(res => {
          if (res && res.status === 'ok') {
            this.syncRandomFdiaButton(res.random_fdia, 0);
          }
        });
      });
    });

    // Presets dropdown
    const selectPreset = document.getElementById('select-preset');
    if (selectPreset) {
      selectPreset.addEventListener('change', (e) => {
        const name = e.target.value;
        if (!name) return;
        this.api.post('/api/preset', { name }).then(res => {
          if (res && res.status === 'ok') {
            selectPreset.value = "";
          }
        });
      });
    }

    // Apply Best Recommendation button
    const btnApplyBest = document.getElementById('btn-apply-best');
    if (btnApplyBest) {
      btnApplyBest.addEventListener('click', () => {
        this.api.post('/api/apply_best', {}).then(res => {
          if (res && res.result) {
            // Remove pulse animation
            btnApplyBest.classList.remove('btn-pulse');
          }
        });
      });
    }

    // Reset stats
    const btnResetStats = document.getElementById('btn-reset-stats');
    if (btnResetStats) {
      btnResetStats.addEventListener('click', () => {
        this.api.post('/api/reset_stats', {});
      });
    }
  }

  syncFdiaButton(isActive) {
    const btns = [
      document.getElementById('btn-manual-attack'),
      document.getElementById('btn-toolbar-fdia-manual'),
      document.getElementById('btn-toggle-fdia')
    ].filter(Boolean);

    btns.forEach(btn => {
      if (isActive) btn.classList.add('active');
      else btn.classList.remove('active');
    });

    const labels = [
      document.getElementById('label-manual-attack'),
      document.getElementById('label-toolbar-fdia-manual'),
      document.getElementById('label-fdia')
    ].filter(Boolean);

    labels.forEach(lbl => {
      lbl.textContent = isActive ? 'Manual Attack: ON' : 'Manual Attack: OFF';
    });

    const dot = document.getElementById('dot-fdia');
    if (dot) {
      if (isActive) dot.classList.add('active');
      else dot.classList.remove('active');
    }
  }

  syncRandomFdiaButton(isEnabled, nextS = 0) {
    const btns = [
      document.getElementById('btn-random-attack'),
      document.getElementById('btn-toolbar-fdia-random')
    ].filter(Boolean);

    btns.forEach(btn => {
      if (isEnabled) btn.classList.add('active');
      else btn.classList.remove('active');
    });

    const labels = [
      document.getElementById('label-random-attack'),
      document.getElementById('label-toolbar-fdia-random')
    ].filter(Boolean);

    labels.forEach(lbl => {
      lbl.textContent = isEnabled ? 'Random Attack: ON' : 'Random Attack: OFF';
    });

    const timerLbl = document.getElementById('label-random-timer');
    if (timerLbl) {
      if (isEnabled) {
        timerLbl.textContent = nextS > 0
          ? `Random Burst State Active · Next toggle in ${nextS.toFixed(1)}s`
          : 'Random Burst Interval: ARMED & RUNNING';
        timerLbl.style.color = '#d8b4fe';
      } else {
        timerLbl.textContent = 'Random Burst Interval: INACTIVE';
        timerLbl.style.color = 'var(--text-muted)';
      }
    }
  }

  syncAutopilotButton(isActive) {
    const btn = document.getElementById('btn-toggle-autopilot');
    const dot = document.getElementById('dot-autopilot');
    if (btn) {
      if (isActive) btn.classList.add('active');
      else btn.classList.remove('active');
    }
    if (dot) {
      if (isActive) dot.classList.add('active');
      else dot.classList.remove('active');
    }
  }

  syncFormValues(config) {
    if (!config) return;

    for (const [key, val] of Object.entries(config)) {
      const rangeEl = document.getElementById(`range-${key}`);
      const numEl = document.getElementById(`num-${key}`);
      const readoutEl = document.getElementById(`readout-${key}`);

      if (rangeEl) rangeEl.value = val;
      if (numEl) numEl.value = val;
      if (readoutEl) readoutEl.textContent = val;

      const selectEl = document.getElementById(`input-${key}`);
      if (selectEl) selectEl.value = val;
    }

    this.updateVisibility(config.source_type, config.channel);
  }

  initDossierModal() {
    const modal = document.getElementById('modal-dossier');
    const btnOpen = document.getElementById('btn-export-dossier');
    const btnClose = document.getElementById('btn-close-dossier');
    const btnPrint = document.getElementById('btn-print-dossier');
    const selectWindow = document.getElementById('select-dossier-window');

    if (!modal) return;

    if (btnOpen) {
      btnOpen.addEventListener('click', () => {
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        const win = selectWindow ? selectWindow.value : 'boot';
        this.loadDossier(win);
      });
    }

    if (btnClose) {
      btnClose.addEventListener('click', () => {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
      });
    }

    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
      }
    });

    if (selectWindow) {
      selectWindow.addEventListener('change', (e) => {
        this.loadDossier(e.target.value);
      });
    }

    if (btnPrint) {
      btnPrint.addEventListener('click', () => {
        window.print();
      });
    }
  }

  loadDossier(windowVal = 'boot') {
    const container = document.getElementById('dossier-content');
    if (!container) return;

    container.innerHTML = `
      <div style="padding: 48px 24px; text-align: center; color: var(--text-muted); font-family: var(--font-mono);">
        <div style="font-size: 1.5rem; margin-bottom: 8px;">⏳</div>
        <div>Compiling Physical Link Telemetry & Filtering Security Logs (${windowVal})...</div>
      </div>
    `;

    fetch(`/api/dossier?window=${encodeURIComponent(windowVal)}`)
      .then(r => r.json())
      .then(d => {
        this.renderDossier(container, d);
      })
      .catch(err => {
        container.innerHTML = `
          <div style="padding: 30px; text-align: center; color: var(--bad); font-family: var(--font-mono);">
            Failed to load Link Dossier: ${err.message}
          </div>
        `;
      });
  }

  renderDossier(container, d) {
    const m = (d.current_link && d.current_link.metrics) || {};
    const cfg = (d.current_link && d.current_link.config) || {};
    const sec = d.security || {};
    const twin = d.twin || {};
    const ranking = twin.ranking || [];
    const events = d.events || [];

    const isAttacking = sec.fdia_active;
    const windowLabel = d.window === 'boot'
      ? 'Full Session (Since Boot)'
      : `Last ${Math.round(parseInt(d.window) / 60)} Minutes`;

    // Format events rows
    const eventRows = events.map(ev => {
      let badgeClass = 'info';
      let badgeText = (ev.type || 'LOG').toUpperCase();

      if (ev.type === 'fdia_attack_start') {
        badgeClass = 'attack';
        badgeText = 'ATTACK INJECTED';
      } else if (ev.type === 'fdia_attack_stop') {
        badgeClass = 'info';
        badgeText = 'ATTACK STOPPED';
      } else if (ev.type === 'fdia_anomaly_detected') {
        badgeClass = 'anomaly';
        badgeText = 'ANOMALY DETECTED';
      } else if (ev.type === 'fdia_mitigated') {
        badgeClass = 'mitigated';
        badgeText = 'THREAT DIVERTED';
      } else if (ev.type === 'apply') {
        badgeClass = 'info';
        badgeText = 'TWIN ADAPTED';
      } else if (ev.type === 'preset') {
        badgeClass = 'info';
        badgeText = 'SCENARIO';
      }

      return `
        <tr>
          <td style="white-space:nowrap; font-weight:600; color:var(--text-dim);">${ev.time || '--:--:--'}</td>
          <td style="white-space:nowrap;"><span class="dossier-badge ${badgeClass}">${badgeText}</span></td>
          <td style="font-size:0.78rem;">${this.escapeHtml(ev.message || '')}</td>
        </tr>
      `;
    }).join('');

    // Format candidate ranking rows
    const rankingRows = ranking.map((r, idx) => {
      const isPick = (r.mod === twin.best);
      const isCur = (r.mod === d.current_link.modulation);
      const rowClass = isPick ? 'highlight-row' : '';
      const statusTag = isPick
        ? '<span class="dossier-badge info">★ TWIN PICK</span>'
        : (isCur ? '<span class="dossier-badge" style="background:rgba(255,255,255,0.1); color:#fff;">ACTIVE</span>' : 'CANDIDATE');

      return `
        <tr class="${rowClass}">
          <td style="text-align:center; font-weight:700;">#${idx + 1}</td>
          <td style="font-weight:700;">${r.mod}</td>
          <td style="font-weight:700; color:${isPick ? 'var(--color-bpsk)' : '#f8fafc'};">${r.applicable ? r.score + ' PTS' : 'N/A'}</td>
          <td>${r.applicable ? r.grade : 'N/A'}</td>
          <td>${statusTag}</td>
          <td style="font-size:0.75rem;">${r.rationale || r.reason || 'Standard operational profile'}</td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      <div class="dossier-report">
        
        <!-- Header Executive Summary -->
        <div class="dossier-header-card">
          <div class="dossier-brand-title">SDCS Digital Twin · Autonomous Cognitive Radio Platform</div>
          <div class="dossier-doc-title">TELECOMMUNICATION LINK DOSSIER & SECURITY AUDIT</div>
          
          <div class="dossier-meta-grid">
            <div class="dossier-meta-item">
              <span class="dossier-meta-label">Audit Timestamp</span>
              <span class="dossier-meta-val">${d.generated_at}</span>
            </div>
            <div class="dossier-meta-item">
              <span class="dossier-meta-label">System Uptime</span>
              <span class="dossier-meta-val">${d.uptime} (Boot: ${d.boot_at})</span>
            </div>
            <div class="dossier-meta-item">
              <span class="dossier-meta-label">Operating Mode</span>
              <span class="dossier-meta-val">${d.mode} · ${d.link_up ? 'LINK LOCKED (ONLINE)' : 'OFFLINE'}</span>
            </div>
            <div class="dossier-meta-item">
              <span class="dossier-meta-label">Active Scenario</span>
              <span class="dossier-meta-val">${d.scenario.name}</span>
            </div>
            <div class="dossier-meta-item">
              <span class="dossier-meta-label">Log Filter Scope</span>
              <span class="dossier-meta-val" style="color:var(--color-bpsk);">${windowLabel}</span>
            </div>
            <div class="dossier-meta-item">
              <span class="dossier-meta-label">Security Health</span>
              <span class="dossier-meta-val" style="color:${isAttacking ? 'var(--bad)' : 'var(--good)'};">
                ${sec.status}
              </span>
            </div>
          </div>
        </div>

        <!-- Section 1: Cyber-Physical Security & FDIA Mitigation Summary -->
        <div class="dossier-section">
          <div class="dossier-section-title">
            <span>🛡️ 1. Cyber-Physical Security & Adversarial Threat Summary</span>
          </div>

          <div class="dossier-kpi-grid">
            <div class="dossier-kpi-card" style="border-left: 3px solid #f43f5e;">
              <span class="dossier-kpi-label">FDIA Attacks Injected</span>
              <span class="dossier-kpi-num" style="color:#f43f5e;">${sec.injected_count}</span>
              <span class="dossier-kpi-sub">Swept Jamming & Phase Spoofs</span>
            </div>

            <div class="dossier-kpi-card" style="border-left: 3px solid #f59e0b;">
              <span class="dossier-kpi-label">Anomalies Detected</span>
              <span class="dossier-kpi-num" style="color:#f59e0b;">${sec.detected_count}</span>
              <span class="dossier-kpi-sub">PSR / CRC / EVM Violations</span>
            </div>

            <div class="dossier-kpi-card" style="border-left: 3px solid #a3e635;">
              <span class="dossier-kpi-label">Threats Safely Diverted</span>
              <span class="dossier-kpi-num" style="color:#a3e635;">${sec.mitigated_count}</span>
              <span class="dossier-kpi-sub">Autonomous FSK Migrations</span>
            </div>

            <div class="dossier-kpi-card" style="border-left: 3px solid var(--color-bpsk);">
              <span class="dossier-kpi-label">Mitigation Efficiency</span>
              <span class="dossier-kpi-num" style="color:var(--color-bpsk);">${sec.mitigation_rate_pct}%</span>
              <span class="dossier-kpi-sub">Safe Link Recovery Ratio</span>
            </div>
          </div>

          <div class="dossier-rationale-box" style="border-color:${isAttacking ? '#f43f5e' : '#10b981'}; color:${isAttacking ? '#f43f5e' : '#10b981'}; background:${isAttacking ? 'rgba(244,63,94,0.08)' : 'rgba(16,185,129,0.08)'};">
            ${isAttacking 
              ? '<strong>⚠️ CYBER ATTACK IN PROGRESS:</strong> Malicious swept-carrier jamming & pilot phase spoofing detected in live baseband. PSK constellation rotation active. Autonomous mitigation recommended (Migrate to FSK non-coherent signaling).'
              : '<strong>🛡️ LINK INTEGRITY VERIFIED:</strong> Baseband correlation confirms authentic preamble peak-to-sidelobe ratio (PSR > 3.0) and CRC-8 header match. Zero active cyber threats detected.'}
          </div>
        </div>

        <!-- Section 2: Physical Link Operating Telemetry -->
        <div class="dossier-section">
          <div class="dossier-section-title">
            <span>📡 2. Physical Link Operating Telemetry & Health Audit</span>
          </div>

          <table class="dossier-table">
            <thead>
              <tr>
                <th>Telemetry Parameter</th>
                <th>Measured Baseband Value</th>
                <th>Analytical / Config Limit</th>
                <th>Integrity Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Active Modulation Scheme</td>
                <td style="font-weight:700;">${d.current_link.modulation}</td>
                <td>Score: <strong>${d.current_link.score} PTS</strong></td>
                <td><span class="dossier-badge info">OPERATING</span></td>
              </tr>
              <tr>
                <td>Signal-to-Noise Ratio (SNR)</td>
                <td>${m.snr_est_db !== undefined ? m.snr_est_db.toFixed(1) + ' dB' : '--'}</td>
                <td>Config: ${(cfg.snr_db || 0).toFixed(1)} dB</td>
                <td>${(m.snr_est_db || 0) >= 10.0 ? 'NOMINAL' : 'MARGINAL'}</td>
              </tr>
              <tr>
                <td>Carrier Frequency Offset (CFO)</td>
                <td>${m.cfo_est_hz !== undefined ? m.cfo_est_hz.toFixed(1) + ' Hz' : '--'}</td>
                <td>Channel: ${(cfg.cfo_hz || 0).toFixed(1)} Hz</td>
                <td>${Math.abs(m.cfo_est_hz || 0) < 500 ? 'LOCKED' : 'TRACKING'}</td>
              </tr>
              <tr>
                <td>RMS Error Vector Magnitude (EVM)</td>
                <td>${m.evm_rms !== undefined ? m.evm_rms.toFixed(1) + '%' : '--'}</td>
                <td>Target Limit: &lt; 25.0%</td>
                <td>${(m.evm_rms || 0) < 25.0 ? 'CLEAN' : 'DEGRADED'}</td>
              </tr>
              <tr>
                <td>Bit Error Rate (BER) & Packet Loss</td>
                <td>BER: ${m.ber !== undefined ? (m.ber === 0 ? '0.00e+0' : m.ber.toExponential(2)) : '--'}</td>
                <td>Packet Loss: ${m.per !== undefined ? m.per.toFixed(1) + '%' : '0.0%'}</td>
                <td>${(m.ber || 0) < 0.01 ? 'PASS' : 'DEGRADED'}</td>
              </tr>
              <tr>
                <td>Preamble Peak-to-Sidelobe (PSR)</td>
                <td>${m.psr !== undefined ? m.psr.toFixed(2) + 'x' : '--'}</td>
                <td>Nominal PSR &gt; 2.5x</td>
                <td>${(m.psr || 0) >= 2.5 ? 'AUTHENTIC' : 'SPOOFED / JAMMED'}</td>
              </tr>
              <tr>
                <td>Channel Impairments Model</td>
                <td>${(cfg.channel || 'awgn').toUpperCase()}</td>
                <td>Doppler: ${(cfg.doppler_hz || 0).toFixed(1)} Hz · Phase Noise: ${(cfg.phase_noise_deg || 0).toFixed(1)}°</td>
                <td>SYNCHRONIZED</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Section 3: Digital Twin Trade-Off Analysis & Recommendations -->
        <div class="dossier-section">
          <div class="dossier-section-title">
            <span>🧠 3. Digital Twin Multi-Objective Modulation Rankings</span>
          </div>

          <table class="dossier-table">
            <thead>
              <tr>
                <th style="width:50px; text-align:center;">Rank</th>
                <th style="width:110px;">Modulation</th>
                <th style="width:90px;">Predicted</th>
                <th style="width:70px;">Grade</th>
                <th style="width:110px;">Status</th>
                <th>Physical Suitability Rationale</th>
              </tr>
            </thead>
            <tbody>
              ${rankingRows}
            </tbody>
          </table>

          <div class="dossier-rationale-box">
            <div style="font-weight:700; margin-bottom:4px; color:#fff;">
              Optimal Recommendation: <span style="color:var(--color-bpsk); font-size:1.05rem;">${twin.best}</span> · Confidence: ${twin.confidence}% · Fidelity Error: ±${(twin.fidelity && twin.fidelity.error_pts) || 0} pts
            </div>
            <div>${twin.rationale || 'Physical channel trade-off analysis verified.'}</div>
          </div>
        </div>

        <!-- Section 4: Chronological Audit & Security Event Log -->
        <div class="dossier-section">
          <div class="dossier-section-title">
            <span>📋 4. Chronological Security & System Event Audit Log (${windowLabel})</span>
          </div>

          <table class="dossier-table">
            <thead>
              <tr>
                <th style="width:90px;">Timestamp</th>
                <th style="width:140px;">Classification</th>
                <th>Operational Event Details & Telemetry Context</th>
              </tr>
            </thead>
            <tbody>
              ${eventRows || '<tr><td colspan="3" style="text-align:center; padding:14px; color:var(--text-muted);">No log events recorded in this time window.</td></tr>'}
            </tbody>
          </table>
        </div>

        <!-- Verification Footer -->
        <div style="margin-top:10px; padding-top:14px; border-top:1px solid rgba(255,255,255,0.08); font-size:0.72rem; color:var(--text-dim); display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px; font-family:var(--font-mono);">
          <span>SDCS Cognitive SDR Platform · Digital Twin Engine Verification</span>
          <span>Security Compliance: CRC-8 Frame Check · Costas / AFC Carrier Recovery</span>
        </div>

      </div>
    `;
  }

  escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}
