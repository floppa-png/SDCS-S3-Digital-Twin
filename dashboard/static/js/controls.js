class DashboardControls {
  constructor(apiClient) {
    this.api = apiClient;
    this.debounceTimer = null;
    this.pendingUpdates = {};
    
    this.initParamBindings();
    this.initHeroCards();
    this.initToolbarControls();
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
}
