const socket = io();

// DOM Elements
const modPrediction = document.getElementById('mod-prediction');
const shieldIcon = document.getElementById('shield-icon');
const fdiStatus = document.getElementById('fdi-status');
const fdiDesc = document.getElementById('fdi-desc');
const securityStatusBox = document.querySelector('.security-status');
const fdiLogBody = document.getElementById('fdi-log-body');

const valBw = document.getElementById('val-bw');
const valPeak = document.getElementById('val-peak');
const valFlatness = document.getElementById('val-flatness');
const valAmp = document.getElementById('val-amp');

let currentMod = "";
let currentFDI = false;
let logCount = 0;

// GSAP Init
document.addEventListener("DOMContentLoaded", () => {
    gsap.from(".navbar", { y: -50, opacity: 0, duration: 1, ease: "power3.out" });
    gsap.from(".glass-panel", { y: 50, opacity: 0, duration: 0.8, stagger: 0.2, ease: "power3.out", delay: 0.3 });
});

// Chart.js Init
Chart.defaults.color = '#9CA3AF';
Chart.defaults.font.family = "'Outfit', sans-serif";

const waveCtx = document.getElementById('waveformChart').getContext('2d');
const waveformChart = new Chart(waveCtx, {
    type: 'line',
    data: {
        labels: Array.from({length: 500}, (_, i) => i),
        datasets: [{
            label: 'Pluto SDR (Actual)',
            data: [],
            borderColor: '#3B82F6',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1
        }, {
            label: 'Digital Twin (Predicted)',
            data: [],
            borderColor: '#FCD34D',
            borderWidth: 1.5,
            borderDash: [5, 5],
            pointRadius: 0,
            tension: 0.1
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
            y: { min: -3, max: 3, grid: { color: 'rgba(255,255,255,0.05)' } },
            x: { display: false }
        },
        plugins: { legend: { display: false } }
    }
});

const radarCtx = document.getElementById('radarChart').getContext('2d');
const radarChart = new Chart(radarCtx, {
    type: 'radar',
    data: {
        labels: ['Bandwidth', 'Peak PSD', 'Flatness', 'Amp Var'],
        datasets: [{
            label: 'Current Signal',
            data: [0,0,0,0],
            backgroundColor: 'rgba(59, 130, 246, 0.2)',
            borderColor: '#3B82F6',
            pointBackgroundColor: '#3B82F6'
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        scales: {
            r: {
                angleLines: { color: 'rgba(255,255,255,0.1)' },
                grid: { color: 'rgba(255,255,255,0.1)' },
                pointLabels: { color: '#F3F4F6', font: { size: 12 } },
                ticks: { display: false, min: 0, max: 1 }
            }
        },
        plugins: { legend: { display: false } }
    }
});

socket.on('connect', () => { console.log('Connected to Digital Twin ZMQ'); });

socket.on('telemetry', (data) => {
    
    // 1. Update Waveform Chart (Dual Lines)
    if(data.signal) {
        waveformChart.data.datasets[0].data = data.signal;
        waveformChart.data.datasets[1].data = data.ideal_signal;
        waveformChart.update();
    }
    
    // 2. Update XAI Radar Chart (Normalized for visuals)
    radarChart.data.datasets[0].data = [
        Math.min(data.features.bw / 100000, 1),
        Math.min(Math.max(data.features.peak_psd + 20, 0) / 40, 1),
        Math.min(data.features.flatness * 5, 1),
        Math.min(data.features.amp_var * 2, 1)
    ];
    radarChart.data.datasets[0].borderColor = data.is_fdi ? '#EF4444' : '#3B82F6';
    radarChart.data.datasets[0].backgroundColor = data.is_fdi ? 'rgba(239, 68, 68, 0.2)' : 'rgba(59, 130, 246, 0.2)';
    radarChart.update();

    // 3. Update Text Features
    valBw.innerText = data.features.bw;
    valPeak.innerText = data.features.peak_psd;
    valFlatness.innerText = data.features.flatness;
    valAmp.innerText = data.features.amp_var;
    
    // 4. Update Optimizer Results
    if (data.optimizer) {
        document.getElementById('opt-score').innerText = data.optimizer.score + "%";
        document.getElementById('opt-top').innerHTML = data.optimizer.top3.map(m => `<span>${m}</span>`).join(' | ');
    }

    // Update Modulation Text and FDI Status UI
    if (data.is_fdi !== currentFDI) {
        currentFDI = data.is_fdi;
        if (data.is_fdi) {
            securityStatusBox.classList.add('alert-state');
            shieldIcon.innerText = "⚠️";
            fdiStatus.innerText = "FDI DETECTED";
            fdiDesc.innerText = "Anomalous physics signatures flagged by Isolation Forest.";
            gsap.fromTo(securityStatusBox, { x: -10 }, { x: 10, duration: 0.1, yoyo: true, repeat: 5 });
            
            // Force QUARANTINED state
            modPrediction.innerText = "QUARANTINED";
            modPrediction.style.color = "#EF4444";
        } else {
            securityStatusBox.classList.remove('alert-state');
            shieldIcon.innerText = "🛡️";
            fdiStatus.innerText = "SECURE";
            fdiDesc.innerText = "Isolation Forest Anomaly Detection Online";
            
            // Restore normal color
            modPrediction.style.color = "#ffffff";
        }
    }
    
    // Only update normal prediction if NOT in FDI lockdown
    if (!data.is_fdi) {
        if (data.modulation !== currentMod) {
            currentMod = data.modulation;
            modPrediction.innerText = data.modulation;
            gsap.fromTo(modPrediction, 
                { scale: 1.2, opacity: 0.5 }, 
                { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(1.7)" }
            );
        }
        
        // Update Top 3 Probabilities with Number Graphics
        if (data.top_3) {
            const colors = [
                { bg: 'rgba(251, 191, 36, 0.15)', border: '#FBBF24', text: '#FCD34D' }, // Gold
                { bg: 'rgba(156, 163, 175, 0.15)', border: '#9CA3AF', text: '#E5E7EB' }, // Silver
                { bg: 'rgba(180, 83, 9, 0.15)', border: '#B45309', text: '#D97706' }   // Bronze
            ];
            
            const top3Container = document.getElementById('top3-container');
            top3Container.innerHTML = data.top_3.map((t, index) => {
                const c = colors[index] || colors[1];
                const numGraphic = `<span style="background: ${c.border}; color: #000; width: 20px; height: 20px; display: inline-flex; justify-content: center; align-items: center; border-radius: 50%; font-size: 0.8rem; font-weight: 800;">${index + 1}</span>`;
                return `<span style="background: ${c.bg}; padding: 6px 16px; border-radius: 8px; border: 1px solid ${c.border}; color: ${c.text}; font-weight: 600; box-shadow: 0 0 15px ${c.bg}; font-size: 1.1rem; display: inline-flex; align-items: center; gap: 8px;">
                    ${numGraphic} ${t.mod}: <strong style="color: #fff;">${t.prob}%</strong>
                </span>`;
            }).join('');
        }
    } else {
        // If FDI is detected, hide or mask the Top 3
        const top3Container = document.getElementById('top3-container');
        top3Container.innerHTML = `<span style="background: rgba(239, 68, 68, 0.15); padding: 6px 16px; border-radius: 8px; border: 1px solid #EF4444; color: #EF4444; font-weight: 600; font-size: 1.1rem;">
            CLASSIFICATION BLOCKED BY ISOLATION FOREST
        </span>`;
        currentMod = "QUARANTINED";
    }
    
    // 6. Log to Table
    const now = new Date();
    const timeStr = now.toLocaleTimeString() + "." + String(now.getMilliseconds()).padStart(3, '0');
    
    const row = document.createElement('tr');
    row.innerHTML = `
        <td>${timeStr}</td>
        <td class="${data.is_fdi ? 'log-fdi' : 'log-secure'}">${data.is_fdi ? 'FDI DETECTED' : 'NORMAL'}</td>
        <td>${data.modulation}</td>
        <td>[BW: ${data.features.bw}Hz, Flatness: ${data.features.flatness}]</td>
    `;
    fdiLogBody.prepend(row);
    
    logCount++;
    if (logCount > 50) {
        fdiLogBody.removeChild(fdiLogBody.lastChild);
    }
});

// UI Control Logic
const ctrlMod = document.getElementById('ctrl-mod');
const ctrlBw = document.getElementById('ctrl-bw');
const ctrlSnr = document.getElementById('ctrl-snr');
const ctrlRnd = document.getElementById('ctrl-rnd');
const ctrlFdi = document.getElementById('ctrl-fdi');
let isRandom = false;
let isFdiMode = false;

function sendTxConfig() {
    fetch('/api/tx_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            modulation: ctrlMod.value,
            bandwidth: parseInt(ctrlBw.value),
            snr: parseInt(ctrlSnr.value),
            is_random: isRandom,
            is_fdi: isFdiMode
        })
    });
}

ctrlMod.addEventListener('change', () => { isRandom = false; isFdiMode = false; sendTxConfig(); });
ctrlBw.addEventListener('change', () => { isRandom = false; isFdiMode = false; sendTxConfig(); });
ctrlSnr.addEventListener('change', () => { isRandom = false; isFdiMode = false; sendTxConfig(); });

ctrlRnd.addEventListener('click', () => {
    isRandom = !isRandom;
    isFdiMode = false;
    sendTxConfig();
});

ctrlFdi.addEventListener('click', () => {
    isFdiMode = !isFdiMode;
    isRandom = false;
    sendTxConfig();
});

socket.on('tx_config_update', (config) => {
    ctrlMod.value = config.modulation || 'BPSK';
    if(config.bandwidth) ctrlBw.value = config.bandwidth;
    if(config.snr) ctrlSnr.value = config.snr;
    
    isRandom = config.is_random;
    isFdiMode = config.is_fdi;
    
    ctrlRnd.innerText = isRandom ? "Auto Randomize: ON" : "Auto Randomize: OFF";
    ctrlRnd.style.background = isRandom ? "rgba(16, 185, 129, 0.2)" : "rgba(59, 130, 246, 0.2)";
    ctrlRnd.style.borderColor = isRandom ? "#10B981" : "#3B82F6";
    ctrlRnd.style.color = isRandom ? "#34D399" : "#60A5FA";
    
    ctrlFdi.innerText = isFdiMode ? "FDI Attack: ACTIVE" : "Force FDI Attack";
    ctrlFdi.style.background = isFdiMode ? "rgba(239, 68, 68, 0.5)" : "rgba(239, 68, 68, 0.2)";
});
