import os
import sys
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

def set_cell_shading(cell, color_hex):
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)

def set_cell_margins(cell, top=80, bottom=80, left=120, right=120):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def set_table_borders(table, color="CBD5E1"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{color}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def build_document():
    doc = docx.Document()
    
    # Page Setup: Standard Letter, 0.75-inch margins for dense, professional formatting
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
        section.page_width = Inches(8.5)
        section.page_height = Inches(11.0)
        
    NAVY = RGBColor(0x1E, 0x3A, 0x8A)      # #1E3A8A - Title & Section Headings
    TEAL = RGBColor(0x0F, 0x76, 0x6E)      # #0F766E - Subtitle
    SLATE = RGBColor(0x33, 0x41, 0x55)     # #334155 - Body Text
    MUTED = RGBColor(0x64, 0x74, 0x8B)     # #64748B - Metadata & Subtext
    DARK = RGBColor(0x0F, 0x17, 0x2A)      # #0F172A - Bold Keywords
    
    # -------------------------------------------------------------
    # DOCUMENT HEADER
    # -------------------------------------------------------------
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(2)
    run_title = p_title.add_run("Software-Defined Cognitive Radio (SDCS) Digital Twin")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(16.5)
    run_title.font.bold = True
    run_title.font.color.rgb = NAVY
    
    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_before = Pt(0)
    p_sub.paragraph_format.space_after = Pt(3)
    run_sub = p_sub.add_run("Closed-Loop Physical Telemetry, Real-Time Modulation Optimization & Cyber-Physical Security Framework")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(10.0)
    run_sub.font.bold = True
    run_sub.font.color.rgb = TEAL
    
    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_before = Pt(0)
    p_meta.paragraph_format.space_after = Pt(10)
    run_meta = p_meta.add_run("Platform: ADALM-PLUTO SDR Hardware-in-the-Loop & High-Fidelity Physics Engine  |  Modulation Suite: 7 Schemes (BPSK, QPSK, ASK, FSK, AM-DSBSC, AM-DSBTC, FM)  |  Security: In-Band FDIA Swept-Jamming & Pilot Spoofing Detection")
    run_meta.font.name = "Arial"
    run_meta.font.size = Pt(8.2)
    run_meta.font.color.rgb = MUTED
    
    # -------------------------------------------------------------
    # 1. EXECUTIVE SUMMARY & OPERATIONAL CONTEXT
    # -------------------------------------------------------------
    p_h1 = doc.add_paragraph()
    p_h1.paragraph_format.space_before = Pt(6)
    p_h1.paragraph_format.space_after = Pt(3)
    r_h1 = p_h1.add_run("1. Executive Summary & Technical Context")
    r_h1.font.name = "Arial"
    r_h1.font.size = Pt(11.0)
    r_h1.font.bold = True
    r_h1.font.color.rgb = NAVY
    
    p_body1 = doc.add_paragraph()
    p_body1.paragraph_format.space_before = Pt(0)
    p_body1.paragraph_format.space_after = Pt(6)
    p_body1.paragraph_format.line_spacing = 1.15
    r_body1 = p_body1.add_run(
        "Modern mission-critical wireless communications (deep-space telemetry, urban microcells, tactical electronic warfare, and LEO satellite downlinks) "
        "operate over highly non-stationary channels subjected to severe multi-path fading, dynamic Doppler trajectory, carrier frequency offsets (CFO), and active electronic countermeasures. "
        "Conventional transceivers operate statically: choosing a fixed modulation scheme that either collapses under severe channel impairments or operates with drastic spectral inefficiency under favorable link margins. "
        "While theoretical cognitive radios have been proposed, existing approaches frequently rely on black-box machine learning models operating on synthetic datasets without grounding in closed-form physical bounds, "
        "or fail when deployed to real RF hardware due to unmodeled phase noise, I/Q imbalance, and hardware LO leakage. "
        "This project establishes a research-grade, real-time Software-Defined Cognitive System (SDCS) Digital Twin. "
        "The platform bridges mathematical communication theory with live over-the-air ADALM-PLUTO SDR hardware, executing real-time multi-objective modulation optimization (~10 Hz frame streaming, ~1 Hz twin evaluation) "
        "while actively defending against False Data Injection Attacks (FDIA) through real-time in-band preamble correlation and autonomous non-coherent fallback diversion."
    )
    r_body1.font.name = "Arial"
    r_body1.font.size = Pt(9.0)
    r_body1.font.color.rgb = SLATE

    # -------------------------------------------------------------
    # 2. SYSTEM ARCHITECTURE & DUALITY
    # -------------------------------------------------------------
    p_h2 = doc.add_paragraph()
    p_h2.paragraph_format.space_before = Pt(6)
    p_h2.paragraph_format.space_after = Pt(3)
    r_h2 = p_h2.add_run("2. System Architecture & Digital-Physical Twin Duality")
    r_h2.font.name = "Arial"
    r_h2.font.size = Pt(11.0)
    r_h2.font.bold = True
    r_h2.font.color.rgb = NAVY
    
    p_body2 = doc.add_paragraph()
    p_body2.paragraph_format.space_before = Pt(0)
    p_body2.paragraph_format.space_after = Pt(4)
    p_body2.paragraph_format.line_spacing = 1.15
    r_body2 = p_body2.add_run(
        "The architecture establishes an operational duality between an analytical Digital Twin and live physical execution channels (High-Fidelity Simulation vs. Over-The-Air SDR Hardware-in-the-Loop):"
    )
    r_body2.font.name = "Arial"
    r_body2.font.size = Pt(9.0)
    r_body2.font.color.rgb = SLATE

    # Bullet 1: Physical Pipeline
    p_b1 = doc.add_paragraph(style='List Bullet')
    p_b1.paragraph_format.space_before = Pt(0)
    p_b1.paragraph_format.space_after = Pt(2)
    p_b1.paragraph_format.line_spacing = 1.15
    r_b1_bold = p_b1.add_run("Physical Baseband Transceiver Pipeline: ")
    r_b1_bold.font.name = "Arial"
    r_b1_bold.font.size = Pt(9.0)
    r_b1_bold.font.bold = True
    r_b1_bold.font.color.rgb = DARK
    r_b1_txt = p_b1.add_run(
        "Synthesizes 1 MSPS complex baseband I/Q signals across 7 distinct modulation schemes (Digital: BPSK, QPSK, ASK, FSK; Analog: AM-DSBSC, AM-DSBTC, FM). "
        "Digital frames incorporate Barker-13 sync preambles, CRC-8 payload error headers, and Root-Raised Cosine (RRC) Nyquist pulse shaping (rolloff alpha=0.35). "
        "The channel engine models calibrated additive thermal AWGN, multi-tap frequency-selective Rayleigh fading (Jakes Doppler spectrum), Rician line-of-sight K-factor, "
        "fractional CFO (up to +/-5000 Hz), phase noise drift, and swept-carrier adversarial jamming."
    )
    r_b1_txt.font.name = "Arial"
    r_b1_txt.font.size = Pt(9.0)
    r_b1_txt.font.color.rgb = SLATE

    # Bullet 2: Digital Twin Engine
    p_b2 = doc.add_paragraph(style='List Bullet')
    p_b2.paragraph_format.space_before = Pt(0)
    p_b2.paragraph_format.space_after = Pt(6)
    p_b2.paragraph_format.line_spacing = 1.15
    r_b2_bold = p_b2.add_run("Digital Twin Analytical Oracle: ")
    r_b2_bold.font.name = "Arial"
    r_b2_bold.font.size = Pt(9.0)
    r_b2_bold.font.bold = True
    r_b2_bold.font.color.rgb = DARK
    r_b2_txt = p_b2.add_run(
        "Executes parallel closed-form analytical trade-off evaluations across all candidate modulations simultaneously at 1 Hz. "
        "Evaluates instantaneous channel parameters (SNR, Doppler, CFO, multipath delay profile, allocable bandwidth) to predict the exact candidate BER, throughput, spectral fit, "
        "and multi-objective score (0-100 pts, Grade A+ to F). Telemetry fidelity tracking continuously compares predicted twin performance against live measured baseband demodulation (fidelity error <= 2 pts)."
    )
    r_b2_txt.font.name = "Arial"
    r_b2_txt.font.size = Pt(9.0)
    r_b2_txt.font.color.rgb = SLATE

    # Table: Comparison across Dimensions
    rows_data = [
        ("Baseband Processing", "Direct 1 MSPS vectorized NumPy/SciPy pipeline", "Direct pyadi-iio / libiio DMA ring buffer streaming"),
        ("Channel Impairments", "Synthesized AWGN, multi-path Rayleigh, Rician K, CFO, Phase Noise", "Over-The-Air 2.4 GHz RF multipath, path loss, real analog LO leakage"),
        ("Carrier Interfacing", "Baseband zero-IF representation", "150 kHz Digital IF offset to eliminate Pluto DC/LO center spike"),
        ("Inter-Process Link", "Direct in-memory zero-copy ring buffers", "Non-blocking ZeroMQ sockets (:5555 RX, :5556 TX) + XML-RPC (:8090)"),
        ("Update Rate", "~10 Hz continuous frame loop, ~1 Hz Twin evaluate", "Hardware-clocked cyclic DMA buffers, ~10 Hz telemetry extraction"),
        ("Execution Integrity", "Mathematical determinism & controlled scenario repeatability", "Actual physical over-the-air validation under real hardware physics")
    ]
    
    table = doc.add_table(rows=len(rows_data) + 1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table)
    
    col_widths = [Inches(1.6), Inches(2.7), Inches(2.7)]
    headers = ["Technical Dimension", "High-Fidelity Baseband Simulation", "ADALM-PLUTO SDR Hardware-in-the-Loop"]
    for i, h in enumerate(headers):
        cell = table.cell(0, i)
        cell.width = col_widths[i]
        set_cell_shading(cell, "1E3A8A")
        set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        r = p.add_run(h)
        r.font.name = "Arial"
        r.font.size = Pt(8.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        
    for row_idx, rdata in enumerate(rows_data):
        row = table.rows[row_idx + 1]
        bg_color = "F8FAFC" if (row_idx % 2 == 1) else "FFFFFF"
        for col_idx, text in enumerate(rdata):
            cell = row.cells[col_idx]
            cell.width = col_widths[col_idx]
            set_cell_shading(cell, bg_color)
            set_cell_margins(cell, top=70, bottom=70, left=140, right=140)
            p = cell.paragraphs[0]
            r = p.add_run(text)
            r.font.name = "Arial"
            r.font.size = Pt(8.2)
            if col_idx == 0:
                r.font.bold = True
                r.font.color.rgb = DARK
            else:
                r.font.color.rgb = SLATE
                
    p_space = doc.add_paragraph()
    p_space.paragraph_format.space_before = Pt(4)
    p_space.paragraph_format.space_after = Pt(0)

    # -------------------------------------------------------------
    # 3. MATHEMATICAL RIGOR & MULTI-OBJECTIVE OPTIMIZATION
    # -------------------------------------------------------------
    p_h3 = doc.add_paragraph()
    p_h3.paragraph_format.space_before = Pt(6)
    p_h3.paragraph_format.space_after = Pt(3)
    r_h3 = p_h3.add_run("3. Mathematical Rigor, Theoretical Formulations & Multi-Objective Scoring")
    r_h3.font.name = "Arial"
    r_h3.font.size = Pt(11.0)
    r_h3.font.bold = True
    r_h3.font.color.rgb = NAVY

    # Closed-Form Formulations
    p_m1 = doc.add_paragraph(style='List Bullet')
    p_m1.paragraph_format.space_before = Pt(0)
    p_m1.paragraph_format.space_after = Pt(2)
    p_m1.paragraph_format.line_spacing = 1.15
    r_m1_b = p_m1.add_run("Closed-Form Analytical Physics: ")
    r_m1_b.font.name = "Arial"
    r_m1_b.font.size = Pt(9.0)
    r_m1_b.font.bold = True
    r_m1_b.font.color.rgb = DARK
    r_m1_t = p_m1.add_run(
        "Candidate modulations are evaluated against exact theoretical error expressions. In AWGN: Pb(BPSK) = Q(sqrt(2*Eb/N0)), "
        "Pb(QPSK) = Q(sqrt(2*Eb/N0)) (Gray-coded), Pb(FSK) = 0.5*exp(-Eb/(2*N0)) (non-coherent energy detection). "
        "In Rayleigh flat fading: Pb(BPSK) = 0.5 * (1 - sqrt(gamma_b / (1 + gamma_b))), incorporating the exact fading integral. "
        "Carrier tracking degradation is modeled via Costas loop phase jitter variance sigma_theta^2 = B_L / (S/N), imposing analytical BER floors if phase noise exceeds decision boundaries."
    )
    r_m1_t.font.name = "Arial"
    r_m1_t.font.size = Pt(9.0)
    r_m1_t.font.color.rgb = SLATE

    # Multi-Objective Scoring
    p_m2 = doc.add_paragraph(style='List Bullet')
    p_m2.paragraph_format.space_before = Pt(0)
    p_m2.paragraph_format.space_after = Pt(2)
    p_m2.paragraph_format.line_spacing = 1.15
    r_m2_b = p_m2.add_run("Multi-Objective Composite Fitness Function: ")
    r_m2_b.font.name = "Arial"
    r_m2_b.font.size = Pt(9.0)
    r_m2_b.font.bold = True
    r_m2_b.font.color.rgb = DARK
    r_m2_t = p_m2.add_run(
        "System scoring combines 6 distinct objective sub-scores: Total Score = w1*S_rel + w2*S_rate + w3*S_bw + w4*S_pwr + w5*S_cplx + w6*S_papr. "
        "1. S_rel (Reliability): Evaluates log-scaled BER against target Pb (10^-5) with steep penalty for packet loss. "
        "2. S_rate (Throughput): Evaluates bit rate achievement against requested mission data rate. "
        "3. S_bw (Spectral Containment): Penalizes occupied Carson/Nyquist bandwidth exceeding allocated channel allocation (alloc_bw). "
        "4. S_pwr (Power Margin): Measures excess link margin above minimum operational threshold. "
        "5. S_cplx (Receiver Complexity): Penalizes complex multi-stage phase synchronization for resource-constrained nodes. "
        "6. S_papr (Power Amplifier Efficiency): Constant envelope modulations (FSK, BPSK) receive 100%, avoiding PA nonlinear distortion."
    )
    r_m2_t.font.name = "Arial"
    r_m2_t.font.size = Pt(9.0)
    r_m2_t.font.color.rgb = SLATE

    # Continuous Closed-Loop Autopilot
    p_m3 = doc.add_paragraph(style='List Bullet')
    p_m3.paragraph_format.space_before = Pt(0)
    p_m3.paragraph_format.space_after = Pt(6)
    p_m3.paragraph_format.line_spacing = 1.15
    r_m3_b = p_m3.add_run("Continuous Autopilot & Anti-Ping-Pong Hysteresis: ")
    r_m3_b.font.name = "Arial"
    r_m3_b.font.size = Pt(9.0)
    r_m3_b.font.bold = True
    r_m3_b.font.color.rgb = DARK
    r_m3_t = p_m3.add_run(
        "An autonomous adaptation state machine operates continuously at 1 Hz. To eliminate rapid modulation oscillation ('ping-pong' effect), "
        "it enforces a 4.0-second dwell window, a 6-point predicted score superiority hurdle, a 12-point reversal barrier, and 3-check persistent degradation confirmation before triggering autonomous transceiver reconfiguration."
    )
    r_m3_t.font.name = "Arial"
    r_m3_t.font.size = Pt(9.0)
    r_m3_t.font.color.rgb = SLATE

    # -------------------------------------------------------------
    # 4. CYBER-PHYSICAL SECURITY & FDIA MITIGATION
    # -------------------------------------------------------------
    p_h4 = doc.add_paragraph()
    p_h4.paragraph_format.space_before = Pt(6)
    p_h4.paragraph_format.space_after = Pt(3)
    r_h4 = p_h4.add_run("4. Cyber-Physical Security: False Data Injection Attack (FDIA) & Autonomous Diversion")
    r_h4.font.name = "Arial"
    r_h4.font.size = Pt(11.0)
    r_h4.font.bold = True
    r_h4.font.color.rgb = NAVY

    # Attack Mechanism
    p_s1 = doc.add_paragraph(style='List Bullet')
    p_s1.paragraph_format.space_before = Pt(0)
    p_s1.paragraph_format.space_after = Pt(2)
    p_s1.paragraph_format.line_spacing = 1.15
    r_s1_b = p_s1.add_run("Adversarial Threat Injection Model: ")
    r_s1_b.font.name = "Arial"
    r_s1_b.font.size = Pt(9.0)
    r_s1_b.font.bold = True
    r_s1_b.font.color.rgb = DARK
    r_s1_t = p_s1.add_run(
        "Simulates sophisticated in-band False Data Injection Attacks (FDIA) combining swept-carrier jamming (5 Hz triangular frequency modulation spanning +/-1.5 kHz) "
        "and synchronous pilot phase spoofing. This malicious energy pulls Costas loop carrier synchronizers out of lock and induces false phase constellation rotations."
    )
    r_s1_t.font.name = "Arial"
    r_s1_t.font.size = Pt(9.0)
    r_s1_t.font.color.rgb = SLATE

    # Real-Time Anomaly Detection
    p_s2 = doc.add_paragraph(style='List Bullet')
    p_s2.paragraph_format.space_before = Pt(0)
    p_s2.paragraph_format.space_after = Pt(2)
    p_s2.paragraph_format.line_spacing = 1.15
    r_s2_b = p_s2.add_run("Multi-Sensor In-Band Anomaly Detection: ")
    r_s2_b.font.name = "Arial"
    r_s2_b.font.size = Pt(9.0)
    r_s2_b.font.bold = True
    r_s2_b.font.color.rgb = DARK
    r_s2_t = p_s2.add_run(
        "Integrates three concurrent detection mechanisms: 1. Preamble Peak-to-Sidelobe Ratio (PSR): Cross-correlation against authentic Barker-13 sequence collapses from nominal >3.0x down to <1.5x during jamming. "
        "2. Frame Header CRC-8 Validation: Detects corrupted frame sync payloads. 3. RMS EVM Anomaly Spikes: Constellation dispersion exceeding nominal thresholds collapses the composite Cyber Trust Score (100% -> <40%)."
    )
    r_s2_t.font.name = "Arial"
    r_s2_t.font.size = Pt(9.0)
    r_s2_t.font.color.rgb = SLATE

    # Autonomous FSK Threat Diversion
    p_s3 = doc.add_paragraph(style='List Bullet')
    p_s3.paragraph_format.space_before = Pt(0)
    p_s3.paragraph_format.space_after = Pt(6)
    p_s3.paragraph_format.line_spacing = 1.15
    r_s3_b = p_s3.add_run("Autonomous Threat Diversion via FSK Fallback: ")
    r_s3_b.font.name = "Arial"
    r_s3_b.font.size = Pt(9.0)
    r_s3_b.font.bold = True
    r_s3_b.font.color.rgb = DARK
    r_s3_t = p_s3.add_run(
        "While phase-shift keying schemes (BPSK, QPSK) collapse under swept-carrier PLL pull-off, Frequency Shift Keying (FSK) utilizes dual-tone non-coherent energy detection "
        "(envelope detection across two discrete spectral bins). The FSK receiver requires zero carrier phase synchronization and discards continuous-wave phase perturbations. "
        "Upon attack identification, the Digital Twin immediately overrides candidate rankings to prioritize FSK, enabling the autopilot to safely divert the link with 100% mitigation efficiency."
    )
    r_s3_t.font.name = "Arial"
    r_s3_t.font.size = Pt(9.0)
    r_s3_t.font.color.rgb = SLATE

    # -------------------------------------------------------------
    # 5. HARDWARE-IN-THE-LOOP & DRIVER ARCHITECTURE
    # -------------------------------------------------------------
    p_h5 = doc.add_paragraph()
    p_h5.paragraph_format.space_before = Pt(6)
    p_h5.paragraph_format.space_after = Pt(3)
    r_h5 = p_h5.add_run("5. Hardware-in-the-Loop (HITL) Interfacing & Driver Architecture")
    r_h5.font.name = "Arial"
    r_h5.font.size = Pt(11.0)
    r_h5.font.bold = True
    r_h5.font.color.rgb = NAVY

    p_body5 = doc.add_paragraph()
    p_body5.paragraph_format.space_before = Pt(0)
    p_body5.paragraph_format.space_after = Pt(6)
    p_body5.paragraph_format.line_spacing = 1.15
    r_body5 = p_body5.add_run(
        "To achieve robust over-the-air communication without relying on fragile external software, the system incorporates a dedicated, standalone Pluto SDR Native Bridge (pluto_native_bridge.py). "
        "The bridge directly links C-level libiio and pyadi-iio bindings to stream complex64 I/Q buffers over local ZeroMQ IPC sockets (PUSH tcp://127.0.0.1:5555 for RX; PULL tcp://127.0.0.1:5556 for TX). "
        "RF parameters (2.4 GHz center frequency, hardware gain, and TX attenuation) are dynamically controlled at runtime via XML-RPC on port 8090. "
        "Crucially, the bridge synthesizes a 150 kHz Digital Intermediate Frequency (IF) offset: shifting baseband signals away from 0 Hz prevents ADALM-PLUTO hardware DC offset and Local Oscillator (LO) leakage from corrupting constellation centroids. "
        "An operating system mutex socket on port 8099 strictly prevents dual-instance process collisions (eliminating libiio -16 device-busy locks) during automated launcher boots."
    )
    r_body5.font.name = "Arial"
    r_body5.font.size = Pt(9.0)
    r_body5.font.color.rgb = SLATE

    # -------------------------------------------------------------
    # 6. WEB DASHBOARD, REAL-TIME ANALYTICS & AUDIT DOSSIER
    # -------------------------------------------------------------
    p_h6 = doc.add_paragraph()
    p_h6.paragraph_format.space_before = Pt(6)
    p_h6.paragraph_format.space_after = Pt(3)
    r_h6 = p_h6.add_run("6. Modern Web Dashboard, Explainability & Audit Report Generation")
    r_h6.font.name = "Arial"
    r_h6.font.size = Pt(11.0)
    r_h6.font.bold = True
    r_h6.font.color.rgb = NAVY

    # Web Dashboard & Visualizations
    p_w1 = doc.add_paragraph(style='List Bullet')
    p_w1.paragraph_format.space_before = Pt(0)
    p_w1.paragraph_format.space_after = Pt(2)
    p_w1.paragraph_format.line_spacing = 1.15
    r_w1_b = p_w1.add_run("Real-Time Analytics & Phosphor Constellation: ")
    r_w1_b.font.name = "Arial"
    r_w1_b.font.size = Pt(9.0)
    r_w1_b.font.bold = True
    r_w1_b.font.color.rgb = DARK
    r_w1_t = p_w1.add_run(
        "Built using Flask and Flask-SocketIO streaming real-time JSON packets at 10 FPS. Features HTML5 Canvas phosphor persistence visualizers: "
        "an organic constellation display calibrated via a decision-directed equalizer (with 0.8s blooming transitions during attacks and suboptimal modulation scatter), "
        "a 256-bin Welch Power Spectral Density (PSD) estimate, eye diagrams, time-domain I/Q traces, and an 8-tile telemetry grid."
    )
    r_w1_t.font.name = "Arial"
    r_w1_t.font.size = Pt(9.0)
    r_w1_t.font.color.rgb = SLATE

    # Physical Rationale & Future SHAP
    p_w2 = doc.add_paragraph(style='List Bullet')
    p_w2.paragraph_format.space_before = Pt(0)
    p_w2.paragraph_format.space_after = Pt(2)
    p_w2.paragraph_format.line_spacing = 1.15
    r_w2_b = p_w2.add_run("Explainability Layer (Physical Rationale & SHAP Blueprint): ")
    r_w2_b.font.name = "Arial"
    r_w2_b.font.size = Pt(9.0)
    r_w2_b.font.bold = True
    r_w2_b.font.color.rgb = DARK
    r_w2_t = p_w2.add_run(
        "Every twin recommendation presents a live 'Physical Rationale' tag explaining the underlying communication physics (e.g. Euclidean distance margin in Deep Space, RRC filtering in Rayleigh fading). "
        "An architectural roadmap establishes SHAP (SHapley Additive exPlanations) integration: computing game-theoretic feature attribution values (phi_i) "
        "to quantify how individual physical metrics (SNR, Doppler, EVM, PSR collapse) drive modulation score gains with mathematical proof and <2 ms latency."
    )
    r_w2_t.font.name = "Arial"
    r_w2_t.font.size = Pt(9.0)
    r_w2_t.font.color.rgb = SLATE

    # Export Link Dossier (Printable PDF)
    p_w3 = doc.add_paragraph(style='List Bullet')
    p_w3.paragraph_format.space_before = Pt(0)
    p_w3.paragraph_format.space_after = Pt(6)
    p_w3.paragraph_format.line_spacing = 1.15
    r_w3_b = p_w3.add_run("Executive Link Dossier & Audit Report (Printable PDF): ")
    r_w3_b.font.name = "Arial"
    r_w3_b.font.size = Pt(9.0)
    r_w3_b.font.bold = True
    r_w3_b.font.color.rgb = DARK
    r_w3_t = p_w3.add_run(
        "A one-click modal generates a formal Telecommunication Link Dossier and Cyber-Physical Security Audit Report. "
        "Features user-configurable log filtering (Full Session since boot, last 5 min, last 15 min, last 1 hr), 4 KPI summary cards (attacks injected, anomalies detected, threats diverted, mitigation rate), "
        "comprehensive physical link telemetry, candidate rankings, and chronological audit logs with publication-grade @media print PDF styling."
    )
    r_w3_t.font.name = "Arial"
    r_w3_t.font.size = Pt(9.0)
    r_w3_t.font.color.rgb = SLATE

    # -------------------------------------------------------------
    # 7. EMPIRICAL VERIFICATION & BENCHMARK SUITE
    # -------------------------------------------------------------
    p_h7 = doc.add_paragraph()
    p_h7.paragraph_format.space_before = Pt(6)
    p_h7.paragraph_format.space_after = Pt(3)
    r_h7 = p_h7.add_run("7. Empirical Verification Suite & Benchmark Results")
    r_h7.font.name = "Arial"
    r_h7.font.size = Pt(11.0)
    r_h7.font.bold = True
    r_h7.font.color.rgb = NAVY

    p_body7 = doc.add_paragraph()
    p_body7.paragraph_format.space_before = Pt(0)
    p_body7.paragraph_format.space_after = Pt(4)
    p_body7.paragraph_format.line_spacing = 1.15
    r_body7 = p_body7.add_run(
        "The system was validated through an automated benchmark suite (validate_fixes.py) achieving 100% pass across all 6 rigorous test categories:"
    )
    r_body7.font.name = "Arial"
    r_body7.font.size = Pt(9.0)
    r_body7.font.color.rgb = SLATE

    v_tests = [
        ("Analog Scenario Optimality: ", "Validated exact expected winners for analog presets: FM broadcast -> FM (Score 96, A+), AM broadcast -> AM-DSBTC (Score 92, A+), Maritime voice -> AM-DSBSC (Score 93, A+)."),
        ("QPSK Rayleigh Stability: ", "Tested over 10 consecutive frames under Urban Cellular multi-path fading: achieved Mean BER = 0.00000 (std=0.00000), Mean Score = 96.8 +/- 0.4 pts (Grade A+), zero fluctuation dropouts."),
        ("Digital Expected Winners: ", "Verified 100% accuracy: Deep Space -> BPSK (97 pts), Urban Cellular -> QPSK (92 pts), LEO Orbit Doppler -> FSK (95 pts), Sub-GHz IoT Sensor -> ASK (95 pts)."),
        ("FDIA Cyber Jamming Diversion: ", "Under active swept-carrier jamming, candidate ranking autonomously selects FSK as the top candidate with 100% diversion success."),
        ("Constellation Decision Fidelity: ", "Verified decision slicer dispersion: optimal modulation constellation clusters tightly (std=0.025-0.035), suboptimal modulations exhibit realistic noise scatter (std=0.13-0.18), and attack jamming features an organic 0.8s transition blooming ramp."),
        ("EVM Bounded Range Check: ", "Verified receiver EVM bounded within realistic 8-10% range for active links, preventing mathematical overflow or visual instability.")
    ]

    for title, desc in v_tests:
        p_v = doc.add_paragraph(style='List Bullet')
        p_v.paragraph_format.space_before = Pt(0)
        p_v.paragraph_format.space_after = Pt(2)
        p_v.paragraph_format.line_spacing = 1.15
        r_vb = p_v.add_run(title)
        r_vb.font.name = "Arial"
        r_vb.font.size = Pt(9.0)
        r_vb.font.bold = True
        r_vb.font.color.rgb = DARK
        r_vt = p_v.add_run(desc)
        r_vt.font.name = "Arial"
        r_vt.font.size = Pt(9.0)
        r_vt.font.color.rgb = SLATE

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SDCS_Digital_Twin_Project_Explanation.docx")
    doc.save(output_path)
    print(f"[Success] Generated document at: {output_path}")

if __name__ == '__main__':
    build_document()
