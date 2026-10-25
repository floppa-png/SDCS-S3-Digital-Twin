class DashboardVisualizers {
  constructor() {
    this.constCanvas = document.getElementById('canvas-constellation');
    this.constCtx = this.constCanvas ? this.constCanvas.getContext('2d') : null;

    this.specCanvas = document.getElementById('canvas-spectrum');
    this.specCtx = this.specCanvas ? this.specCanvas.getContext('2d') : null;

    this.eyeCanvas = document.getElementById('canvas-eye');
    this.eyeCtx = this.eyeCanvas ? this.eyeCanvas.getContext('2d') : null;

    this.iqCanvas = document.getElementById('canvas-iq');
    this.iqCtx = this.iqCanvas ? this.iqCanvas.getContext('2d') : null;

    this.waterfallHeight = 90; // Bottom portion of spectrum canvas
    this.setupCanvases();
  }

  setupCanvases() {
    // Enable alpha blending and high-DPI crispness
    const canvases = [this.constCanvas, this.specCanvas, this.eyeCanvas, this.iqCanvas];
    canvases.forEach(c => {
      if (!c) return;
      const rect = c.getBoundingClientRect();
      if (rect.width && rect.height) {
        c.width = rect.width;
        c.height = rect.height;
      }
    });

    // Clear with dark base
    if (this.constCtx) {
      this.constCtx.fillStyle = '#03060c';
      this.constCtx.fillRect(0, 0, this.constCanvas.width, this.constCanvas.height);
    }
    if (this.specCtx) {
      this.specCtx.fillStyle = '#03060c';
      this.specCtx.fillRect(0, 0, this.specCanvas.width, this.specCanvas.height);
    }
  }

  _blendColor(c1, c2, factor) {
    if (factor <= 0) return c1;
    if (factor >= 1) return c2;
    const parse = hex => {
      let c = hex.replace('#', '');
      if (c.length === 3) c = c.split('').map(x => x + x).join('');
      const num = parseInt(c, 16);
      return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
    };
    try {
      const rgb1 = parse(c1);
      const rgb2 = parse(c2);
      const r = Math.round(rgb1[0] + (rgb2[0] - rgb1[0]) * factor);
      const g = Math.round(rgb1[1] + (rgb2[1] - rgb1[1]) * factor);
      const b = Math.round(rgb1[2] + (rgb2[2] - rgb1[2]) * factor);
      return `rgb(${r}, ${g}, ${b})`;
    } catch {
      return factor > 0.5 ? c2 : c1;
    }
  }

  renderConstellation(points, mod, modColor = '#22d3ee', isAttack = false) {
    if (!this.constCtx || !this.constCanvas) return;
    const w = this.constCanvas.width;
    const h = this.constCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const scale = Math.min(w, h) * 0.38;

    // Smooth frontend attack transition factor (lerp towards target)
    if (this.attackLerp === undefined) this.attackLerp = 0.0;
    const targetLerp = isAttack ? 1.0 : 0.0;
    this.attackLerp += (targetLerp - this.attackLerp) * 0.16;
    if (Math.abs(this.attackLerp - targetLerp) < 0.01) this.attackLerp = targetLerp;

    // 1. Phosphor persistence: fade previous frame with dark semi-transparent wash
    if (this.attackLerp > 0.05) {
      const rGlow = Math.round(3 + 22 * this.attackLerp);
      this.constCtx.fillStyle = `rgba(${rGlow}, 4, 8, 0.28)`;
    } else {
      this.constCtx.fillStyle = 'rgba(3, 6, 12, 0.28)';
    }
    this.constCtx.fillRect(0, 0, w, h);

    // 2. Coordinate axes & reference ring (subtle red warning glow when under attack)
    const axisColor = this.attackLerp > 0.05
      ? `rgba(${Math.round(148 + 100 * this.attackLerp)}, ${Math.round(163 * (1 - this.attackLerp * 0.5))}, ${Math.round(184 * (1 - this.attackLerp * 0.5))}, 0.16)`
      : 'rgba(148, 163, 184, 0.12)';
    this.constCtx.strokeStyle = axisColor;
    this.constCtx.lineWidth = 1;
    this.constCtx.beginPath();
    this.constCtx.moveTo(0, cy); this.constCtx.lineTo(w, cy);
    this.constCtx.moveTo(cx, 0); this.constCtx.lineTo(cx, h);
    this.constCtx.stroke();

    this.constCtx.beginPath();
    this.constCtx.arc(cx, cy, scale, 0, 2 * Math.PI);
    this.constCtx.stroke();

    if (!points || points.length === 0) return;

    // 3. Draw received constellation cloud with glowing phosphor dots
    const activeDotColor = this.attackLerp > 0.01 
      ? this._blendColor(modColor, '#ef4444', this.attackLerp)
      : modColor;
      
    this.constCtx.fillStyle = activeDotColor;
    this.constCtx.shadowBlur = 6 + Math.round(4 * this.attackLerp);
    this.constCtx.shadowColor = activeDotColor;

    for (let i = 0; i < points.length; i++) {
      const pt = points[i];
      const px = cx + pt[0] * scale;
      const py = cy - pt[1] * scale;
      if (px >= 0 && px < w && py >= 0 && py < h) {
        this.constCtx.beginPath();
        this.constCtx.arc(px, py, 1.8, 0, 2 * Math.PI);
        this.constCtx.fill();
      }
    }
    this.constCtx.shadowBlur = 0;
  }

  renderSpectrum(psdDb, psdRange, allocBwKhz = null) {
    if (!this.specCtx || !this.specCanvas) return;
    const w = this.specCanvas.width;
    const h = this.specCanvas.height;
    const topH = h - this.waterfallHeight;

    // --- Top Half: PSD Line Plot ---
    this.specCtx.fillStyle = '#03060c';
    this.specCtx.fillRect(0, 0, w, topH);

    // Grid lines
    this.specCtx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    this.specCtx.lineWidth = 1;
    for (let y = 20; y < topH; y += 30) {
      this.specCtx.beginPath();
      this.specCtx.moveTo(0, y);
      this.specCtx.lineTo(w, y);
      this.specCtx.stroke();
    }

    // Allocated bandwidth shaded band
    if (allocBwKhz && psdRange) {
      const fSpan = psdRange[1] - psdRange[0];
      const bwFraction = (allocBwKhz / fSpan) * w;
      const bandLeft = (w - bwFraction) / 2;
      this.specCtx.fillStyle = 'rgba(34, 211, 238, 0.08)';
      this.specCtx.fillRect(bandLeft, 0, bwFraction, topH);
      this.specCtx.strokeStyle = 'rgba(34, 211, 238, 0.25)';
      this.specCtx.strokeRect(bandLeft, 0, bwFraction, topH);
    }

    if (!psdDb || psdDb.length === 0) return;

    // Draw PSD line
    const n = psdDb.length;
    const minDb = -60;
    const maxDb = 20;
    const dbRange = maxDb - minDb;

    const grad = this.specCtx.createLinearGradient(0, 0, 0, topH);
    grad.addColorStop(0, 'rgba(34, 211, 238, 0.4)');
    grad.addColorStop(1, 'rgba(34, 211, 238, 0.0)');

    this.specCtx.beginPath();
    this.specCtx.moveTo(0, topH);

    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * w;
      const dbClamped = Math.max(minDb, Math.min(maxDb, psdDb[i]));
      const y = topH - ((dbClamped - minDb) / dbRange) * topH;
      if (i === 0) this.specCtx.lineTo(x, y);
      else this.specCtx.lineTo(x, y);
    }

    this.specCtx.lineTo(w, topH);
    this.specCtx.closePath();
    this.specCtx.fillStyle = grad;
    this.specCtx.fill();

    // Line stroke
    this.specCtx.beginPath();
    for (let i = 0; i < n; i++) {
      const x = (i / (n - 1)) * w;
      const dbClamped = Math.max(minDb, Math.min(maxDb, psdDb[i]));
      const y = topH - ((dbClamped - minDb) / dbRange) * topH;
      if (i === 0) this.specCtx.moveTo(x, y);
      else this.specCtx.lineTo(x, y);
    }
    this.specCtx.strokeStyle = '#22d3ee';
    this.specCtx.lineWidth = 1.8;
    this.specCtx.stroke();

    // --- Bottom Half: Waterfall Display ---
    const wfY = topH + 1;
    const wfH = this.waterfallHeight - 1;

    // Shift previous waterfall lines downwards by 2px
    this.specCtx.drawImage(
      this.specCanvas,
      0, wfY, w, wfH - 2,
      0, wfY + 2, w, wfH - 2
    );

    // Render new spectrum scanline at top of waterfall
    const imgData = this.specCtx.createImageData(w, 2);
    for (let x = 0; x < w; x++) {
      const binIdx = Math.floor((x / w) * n);
      const val = psdDb[binIdx] || minDb;
      const norm = Math.max(0, Math.min(1, (val - minDb) / dbRange));
      const rgb = this.colormapTurbo(norm);

      for (let row = 0; row < 2; row++) {
        const offset = (row * w + x) * 4;
        imgData.data[offset] = rgb[0];
        imgData.data[offset + 1] = rgb[1];
        imgData.data[offset + 2] = rgb[2];
        imgData.data[offset + 3] = 255;
      }
    }
    this.specCtx.putImageData(imgData, 0, wfY);
  }

  colormapTurbo(val) {
    // Thermal colormap: Dark Navy -> Teal -> Green -> Yellow -> Red
    let r, g, b;
    if (val < 0.25) {
      r = 6;
      g = Math.floor(10 + val * 4 * 140);
      b = Math.floor(25 + val * 4 * 230);
    } else if (val < 0.5) {
      const norm = (val - 0.25) * 4;
      r = Math.floor(6 + norm * 40);
      g = Math.floor(150 + norm * 80);
      b = Math.floor(255 - norm * 150);
    } else if (val < 0.75) {
      const norm = (val - 0.5) * 4;
      r = Math.floor(46 + norm * 200);
      g = Math.floor(230 + norm * 25);
      b = Math.floor(105 - norm * 105);
    } else {
      const norm = (val - 0.75) * 4;
      r = 255;
      g = Math.floor(255 - norm * 200);
      b = 0;
    }
    return [r, g, b];
  }

  renderEyeDiagram(traces) {
    if (!this.eyeCtx || !this.eyeCanvas) return;
    const w = this.eyeCanvas.width;
    const h = this.eyeCanvas.height;
    const cy = h / 2;

    // Fade with alpha wash
    this.eyeCtx.fillStyle = 'rgba(3, 6, 12, 0.20)';
    this.eyeCtx.fillRect(0, 0, w, h);

    // Centerline
    this.eyeCtx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    this.eyeCtx.lineWidth = 1;
    this.eyeCtx.beginPath();
    this.eyeCtx.moveTo(0, cy); this.eyeCtx.lineTo(w, cy);
    this.eyeCtx.stroke();

    if (!traces || traces.length === 0) return;

    this.eyeCtx.strokeStyle = 'rgba(34, 211, 238, 0.45)';
    this.eyeCtx.lineWidth = 1.2;

    for (let t = 0; t < traces.length; t++) {
      const trace = traces[t];
      const nPts = trace.length;
      if (nPts === 0) continue;

      this.eyeCtx.beginPath();
      for (let p = 0; p < nPts; p++) {
        const x = (p / (nPts - 1)) * w;
        const y = cy - trace[p] * (h * 0.38);
        if (p === 0) this.eyeCtx.moveTo(x, y);
        else this.eyeCtx.lineTo(x, y);
      }
      this.eyeCtx.stroke();
    }
  }

  renderIqTrace(iqData) {
    if (!this.iqCtx || !this.iqCanvas || !iqData) return;
    const w = this.iqCanvas.width;
    const h = this.iqCanvas.height;
    const cy = h / 2;

    this.iqCtx.fillStyle = '#03060c';
    this.iqCtx.fillRect(0, 0, w, h);

    // Center axis
    this.iqCtx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
    this.iqCtx.lineWidth = 1;
    this.iqCtx.beginPath();
    this.iqCtx.moveTo(0, cy); this.iqCtx.lineTo(w, cy);
    this.iqCtx.stroke();

    const iVals = iqData.i || [];
    const qVals = iqData.q || [];
    const n = Math.min(iVals.length, qVals.length);
    if (n < 2) return;

    const scale = h * 0.35;

    // Draw I Trace in Cyan
    this.iqCtx.strokeStyle = '#22d3ee';
    this.iqCtx.lineWidth = 1.5;
    this.iqCtx.beginPath();
    for (let p = 0; p < n; p++) {
      const x = (p / (n - 1)) * w;
      const y = cy - iVals[p] * scale;
      if (p === 0) this.iqCtx.moveTo(x, y);
      else this.iqCtx.lineTo(x, y);
    }
    this.iqCtx.stroke();

    // Draw Q Trace in Violet
    this.iqCtx.strokeStyle = '#8b5cf6';
    this.iqCtx.lineWidth = 1.5;
    this.iqCtx.beginPath();
    for (let p = 0; p < n; p++) {
      const x = (p / (n - 1)) * w;
      const y = cy - qVals[p] * scale;
      if (p === 0) this.iqCtx.moveTo(x, y);
      else this.iqCtx.lineTo(x, y);
    }
    this.iqCtx.stroke();
  }
}
