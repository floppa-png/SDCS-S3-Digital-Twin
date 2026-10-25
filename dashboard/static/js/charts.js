// Per-modulation color palette
const MOD_COLORS = {
  'BPSK': '#22d3ee',
  'QPSK': '#8b5cf6',
  'ASK': '#f59e0b',
  'FSK': '#a3e635',
  'AM_DSBSC': '#60a5fa',
  'AM_DSBTC': '#fb923c',
  'FM': '#2dd4bf'
};

class DashboardCharts {
  constructor() {
    this.scoreHistory = []; // {t: timestamp, score: number, event?: string}
    this.timelineChart = null;
    this.berChart = null;
    this.rankingChart = null;
    
    this.initTimelineChart();
    this.initBerChart();
    this.initRankingChart();
  }

  initTimelineChart() {
    const ctx = document.getElementById('chart-score-timeline');
    if (!ctx) return;

    // Custom plugin for drawing optimization event annotations
    const eventAnnotationPlugin = {
      id: 'eventAnnotations',
      afterDraw: (chart) => {
        const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data) return;

        ctx.save();
        chart.data.labels.forEach((label, idx) => {
          const pt = this.scoreHistory[idx];
          if (pt && pt.event) {
            const xPos = meta.data[idx]?.x;
            if (xPos !== undefined && xPos >= chart.chartArea.left && xPos <= chart.chartArea.right) {
              // Vertical marker line
              ctx.strokeStyle = pt.event.includes('APPLY') ? '#22d3ee' : '#f59e0b';
              ctx.lineWidth = 1.5;
              ctx.setLineDash([4, 4]);
              ctx.beginPath();
              ctx.moveTo(xPos, top);
              ctx.lineTo(xPos, bottom);
              ctx.stroke();

              // Badge label
              ctx.setLineDash([]);
              ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
              ctx.fillRect(xPos - 35, top + 4, 70, 16);
              ctx.strokeStyle = ctx.strokeStyle;
              ctx.strokeRect(xPos - 35, top + 4, 70, 16);
              
              ctx.fillStyle = '#f8fafc';
              ctx.font = 'bold 9px "JetBrains Mono"';
              ctx.textAlign = 'center';
              ctx.fillText(pt.event, xPos, top + 15);
            }
          }
        });
        ctx.restore();
      }
    };

    this.timelineChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'System Performance Score',
          data: [],
          borderColor: '#22d3ee',
          backgroundColor: 'rgba(34, 211, 238, 0.1)',
          borderWidth: 2,
          fill: true,
          tension: 0.25,
          pointRadius: (ctx) => {
            const idx = ctx.dataIndex;
            return this.scoreHistory[idx]?.event ? 5 : 0;
          },
          pointBackgroundColor: '#fff',
          pointBorderColor: '#22d3ee'
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 0 },
        scales: {
          x: {
            display: false
          },
          y: {
            min: 0,
            max: 100,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: 'index',
            intersect: false,
            callbacks: {
              label: (ctx) => `Score: ${ctx.parsed.y} pts`
            }
          }
        }
      },
      plugins: [eventAnnotationPlugin]
    });
  }

  initBerChart() {
    const ctx = document.getElementById('chart-ber-curves');
    if (!ctx) return;

    this.berChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: []
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        scales: {
          x: {
            title: { display: true, text: 'Eb/N0 (dB)', color: '#94a3b8', font: { size: 10 } },
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } }
          },
          y: {
            type: 'logarithmic',
            min: 1e-7,
            max: 0.5,
            title: { display: true, text: 'Theoretical BER', color: '#94a3b8', font: { size: 10 } },
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#94a3b8',
              font: { family: 'JetBrains Mono', size: 9 },
              callback: (val) => val === 1e-6 || val === 1e-4 || val === 1e-2 || val === 0.5 ? val.toExponential(0) : ''
            }
          }
        },
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#f8fafc', boxWidth: 10, font: { family: 'Space Grotesk', size: 10 } }
          }
        }
      }
    });
  }

  initRankingChart() {
    const ctx = document.getElementById('chart-ranking');
    if (!ctx) return;

    this.rankingChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{
          label: 'Score',
          data: [],
          backgroundColor: [],
          borderColor: 'transparent',
          borderWidth: 1.5,
          borderRadius: 4
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 350 },
        scales: {
          x: {
            min: 0,
            max: 100,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 10 } }
          },
          y: {
            grid: { display: false },
            ticks: { color: '#f8fafc', font: { family: 'Space Grotesk', size: 10, weight: 600 } }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `Twin Score: ${ctx.parsed.x} / 100 pts`
            }
          }
        }
      }
    });
  }

  addScorePoint(score, eventLabel = null) {
    const now = new Date().toLocaleTimeString();
    this.scoreHistory.push({
      t: now,
      score: score,
      event: eventLabel
    });

    if (this.scoreHistory.length > 120) {
      this.scoreHistory.shift();
    }

    if (this.timelineChart) {
      this.timelineChart.data.labels = this.scoreHistory.map(p => p.t);
      this.timelineChart.data.datasets[0].data = this.scoreHistory.map(p => p.score);
      this.timelineChart.update('none');
    }
  }

  updateBerCurves(curvesData, currentEbn0 = null, currentBer = null) {
    if (!this.berChart || !curvesData || !curvesData.ebn0_db) return;

    const labels = curvesData.ebn0_db;
    const datasets = [];

    // Curves for digital modulations
    for (const [mod, pts] of Object.entries(curvesData.mods)) {
      datasets.push({
        label: mod,
        data: pts,
        borderColor: MOD_COLORS[mod] || '#94a3b8',
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.2
      });
    }

    // Operating point marker if present
    if (currentEbn0 !== null && currentBer !== null && currentBer > 0) {
      datasets.push({
        label: 'Operating Point',
        data: [{ x: currentEbn0, y: Math.max(1e-7, currentBer) }],
        borderColor: '#fff',
        backgroundColor: '#ef4444',
        pointRadius: 6,
        pointHoverRadius: 8,
        showLine: false
      });
    }

    this.berChart.data.labels = labels;
    this.berChart.data.datasets = datasets;
    this.berChart.update();
  }

  updateRanking(ranking, currentMod, bestMod) {
    if (!this.rankingChart || !ranking) return;

    const applicable = ranking.filter(r => r.applicable);
    const labels = applicable.map(r => r.mod);
    const scores = applicable.map(r => r.score);
    const bgColors = applicable.map(r => MOD_COLORS[r.mod] || '#64748b');

    this.rankingChart.data.labels = labels;
    this.rankingChart.data.datasets[0].data = scores;
    this.rankingChart.data.datasets[0].backgroundColor = bgColors;
    
    // Highlight current modulation with border
    this.rankingChart.data.datasets[0].borderColor = labels.map(l => l === currentMod ? '#ffffff' : 'transparent');
    this.rankingChart.update();
  }
}
