function mb = modulation_bank()
%MODULATION_BANK  Modulator/demodulator functions for the Digital Twin project.
%
%   mb = modulation_bank()  returns a struct whose fields are function handles.
%
%   DIGITAL MODULATIONS  (ASK, FSK, BPSK, QPSK)
%     [tx_signal, t, bits] = mb.<scheme>_mod(params)
%     [rx_bits,  ber]      = mb.<scheme>_demod(rx_signal, params, tx_bits)
%
%   ANALOG MODULATIONS   (AM DSB-SC, AM DSB-TC, FM)
%     [tx_signal, t, msg]      = mb.<scheme>_mod(params)
%     [rx_msg,  output_snr_dB] = mb.<scheme>_demod(rx_signal, params, tx_msg)
%
%   Required fields of the params struct
%   -------------------------------------
%     .fs           Sampling frequency  (Hz)
%     .fc           Carrier frequency   (Hz)
%     .symbol_rate  Bit / symbol rate   (Hz)
%     .num_bits     Number of bits per trial      (digital)
%     .msg_freq     Message frequency   (Hz)       (analog)
%     .duration     Message duration    (s)        (analog)
%     .fm_freq_dev  FM frequency deviation (Hz)    (FM only)
%     .mod_index    AM modulation index  (0-1)     (DSB-TC only)
%
%   No Communications Toolbox required.
%   See also: channel_models, run_sweep

    % ---- Digital modulations ----
    mb.bpsk_mod   = @bpsk_mod;    mb.bpsk_demod = @bpsk_demod;
    mb.qpsk_mod   = @qpsk_mod;    mb.qpsk_demod = @qpsk_demod;
    mb.ask_mod    = @ask_mod;     mb.ask_demod  = @ask_demod;
    mb.fsk_mod    = @fsk_mod;     mb.fsk_demod  = @fsk_demod;

    % ---- Analog modulations ----
    mb.am_dsbsc_mod   = @am_dsbsc_mod;   mb.am_dsbsc_demod = @am_dsbsc_demod;
    mb.am_dsbtc_mod   = @am_dsbtc_mod;   mb.am_dsbtc_demod = @am_dsbtc_demod;
    mb.fm_mod         = @fm_mod;         mb.fm_demod       = @fm_demod;
end


% =========================================================================
%  BPSK — Binary Phase Shift Keying
% =========================================================================

function [tx_signal, t, bits] = bpsk_mod(params)
%BPSK_MOD  BPSK modulation (passband).
%   Maps bits to NRZ (+/-1), upsamples, multiplies by cos(2*pi*fc*t).

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    N   = params.num_bits;
    spb = round(fs / Rb);                  % samples per bit

    bits     = randi([0 1], 1, N);
    nrz      = 2*bits - 1;                  % 0 -> -1,  1 -> +1
    baseband = repelem(nrz, spb);            % rectangular pulse shaping
    t        = (0 : length(baseband)-1) / fs;
    tx_signal = baseband .* cos(2*pi*fc*t);
end

function [rx_bits, ber] = bpsk_demod(rx_signal, params, tx_bits)
%BPSK_DEMOD  Coherent BPSK demodulation with integrate-and-dump.

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    spb = round(fs / Rb);
    N   = floor(length(rx_signal) / spb);

    t     = (0 : length(rx_signal)-1) / fs;
    demod = rx_signal .* cos(2*pi*fc*t);     % coherent multiply

    % Vectorised integrate-and-dump
    reshaped = reshape(demod(1:N*spb), spb, N);
    rx_bits  = double(sum(reshaped, 1) > 0);

    n   = min(length(tx_bits), N);
    ber = sum(tx_bits(1:n) ~= rx_bits(1:n)) / n;
end


% =========================================================================
%  QPSK — Quadrature Phase Shift Keying
% =========================================================================

function [tx_signal, t, bits] = qpsk_mod(params)
%QPSK_MOD  QPSK modulation (passband, Gray-coded).
%   2 bits per symbol → I/Q mapping → cos / -sin carriers.

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;              % bit rate
    N   = params.num_bits;
    N   = N - mod(N, 2);                   % ensure even number of bits
    Rs  = Rb / 2;                          % symbol rate
    sps = round(fs / Rs);                  % samples per symbol

    bits   = randi([0 1], 1, N);
    I_bits = bits(1:2:end);                % odd-index bits  → in-phase
    Q_bits = bits(2:2:end);                % even-index bits → quadrature
    I_nrz  = 2*I_bits - 1;
    Q_nrz  = 2*Q_bits - 1;

    I_bb = repelem(I_nrz, sps);
    Q_bb = repelem(Q_nrz, sps);
    t    = (0 : length(I_bb)-1) / fs;

    tx_signal = I_bb .* cos(2*pi*fc*t) - Q_bb .* sin(2*pi*fc*t);
end

function [rx_bits, ber] = qpsk_demod(rx_signal, params, tx_bits)
%QPSK_DEMOD  Coherent QPSK demodulation.

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    Rs  = Rb / 2;
    sps = round(fs / Rs);
    Ns  = floor(length(rx_signal) / sps);  % number of symbols

    t     = (0 : length(rx_signal)-1) / fs;
    I_dem = rx_signal .*  cos(2*pi*fc*t);
    Q_dem = rx_signal .* (-sin(2*pi*fc*t));

    % Vectorised integrate-and-dump
    I_rs = reshape(I_dem(1:Ns*sps), sps, Ns);
    Q_rs = reshape(Q_dem(1:Ns*sps), sps, Ns);
    I_bits = double(sum(I_rs, 1) > 0);
    Q_bits = double(sum(Q_rs, 1) > 0);

    % Interleave I and Q decisions back to bit stream
    rx_bits           = zeros(1, 2*Ns);
    rx_bits(1:2:end)  = I_bits;
    rx_bits(2:2:end)  = Q_bits;

    n   = min(length(tx_bits), 2*Ns);
    ber = sum(tx_bits(1:n) ~= rx_bits(1:n)) / n;
end


% =========================================================================
%  ASK — Amplitude Shift Keying  (On-Off Keying / 2-ASK)
% =========================================================================

function [tx_signal, t, bits] = ask_mod(params)
%ASK_MOD  OOK modulation — bit 1 → carrier burst, bit 0 → silence.

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    N   = params.num_bits;
    spb = round(fs / Rb);

    bits     = randi([0 1], 1, N);
    baseband = repelem(double(bits), spb);   % amplitude: 0 or 1
    t        = (0 : length(baseband)-1) / fs;
    tx_signal = baseband .* cos(2*pi*fc*t);
end

function [rx_bits, ber] = ask_demod(rx_signal, params, tx_bits)
%ASK_DEMOD  Coherent ASK detection with adaptive threshold.

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    spb = round(fs / Rb);
    N   = floor(length(rx_signal) / spb);

    t     = (0 : length(rx_signal)-1) / fs;
    demod = rx_signal .* cos(2*pi*fc*t);

    % Vectorised integrate-and-dump
    reshaped = reshape(demod(1:N*spb), spb, N);
    corr_out = sum(reshaped, 1);

    % Adaptive threshold — midpoint of observed correlator distribution
    threshold = mean(corr_out);
    rx_bits   = double(corr_out > threshold);

    n   = min(length(tx_bits), N);
    ber = sum(tx_bits(1:n) ~= rx_bits(1:n)) / n;
end


% =========================================================================
%  FSK — Binary Frequency Shift Keying
% =========================================================================

function [tx_signal, t, bits] = fsk_mod(params)
%FSK_MOD  BFSK with orthogonal tone spacing (delta_f = Rb).
%   bit 0 → cos(2*pi*f0*t),  bit 1 → cos(2*pi*f1*t)

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    N   = params.num_bits;
    spb = round(fs / Rb);

    delta_f = Rb;                            % minimum orthogonal separation
    f0 = fc - delta_f/2;                     % freq for bit 0
    f1 = fc + delta_f/2;                     % freq for bit 1

    bits = randi([0 1], 1, N);
    t    = (0 : N*spb - 1) / fs;

    % Vectorised: build frequency-per-sample vector
    freq_per_bit = f0 + (f1 - f0) * bits;   % 1×N  (f0 or f1)
    freq_vec     = repelem(freq_per_bit, spb); % 1×(N*spb)
    tx_signal    = cos(2*pi * freq_vec .* t);
end

function [rx_bits, ber] = fsk_demod(rx_signal, params, tx_bits)
%FSK_DEMOD  Non-coherent FSK detection — correlate with both tones.

    fs  = params.fs;
    fc  = params.fc;
    Rb  = params.symbol_rate;
    spb = round(fs / Rb);
    N   = floor(length(rx_signal) / spb);

    delta_f = Rb;
    f0 = fc - delta_f/2;
    f1 = fc + delta_f/2;

    t = (0 : length(rx_signal)-1) / fs;

    % Vectorised correlation with both tones
    ref0 = cos(2*pi*f0*t);
    ref1 = cos(2*pi*f1*t);

    prod0 = reshape(rx_signal(1:N*spb) .* ref0(1:N*spb), spb, N);
    prod1 = reshape(rx_signal(1:N*spb) .* ref1(1:N*spb), spb, N);

    corr0 = sum(prod0, 1);
    corr1 = sum(prod1, 1);

    rx_bits = double(corr1 > corr0);

    n   = min(length(tx_bits), N);
    ber = sum(tx_bits(1:n) ~= rx_bits(1:n)) / n;
end


% =========================================================================
%  AM DSB-SC — Double Sideband Suppressed Carrier
% =========================================================================

function [tx_signal, t, msg] = am_dsbsc_mod(params)
%AM_DSBSC_MOD  s(t) = m(t) * cos(2*pi*fc*t + phi_c),  m(t) = cos(2*pi*fm*t + phi_m)

    fs  = params.fs;
    fc  = params.fc;
    % Jitter message frequency by +/- 10% to prevent leakage
    fm  = params.msg_freq + (rand()*0.2 - 0.1)*params.msg_freq;
    dur = params.duration;
    
    phi_m = 2*pi*rand();
    phi_c = 2*pi*rand();

    t   = 0 : 1/fs : dur - 1/fs;
    msg = cos(2*pi*fm*t + phi_m);                    % unit-amplitude sinusoid
    tx_signal = msg .* cos(2*pi*fc*t + phi_c);
end

function [rx_msg, out_snr_db] = am_dsbsc_demod(rx_signal, params, tx_msg)
%AM_DSBSC_DEMOD  Coherent detection: multiply by carrier then LPF.

    fs = params.fs;
    fc = params.fc;
    fm = params.msg_freq;

    t     = (0 : length(rx_signal)-1) / fs;
    demod = 2 * rx_signal .* cos(2*pi*fc*t);  % factor 2 for cos^2 scaling

    % 6th-order Butterworth LPF, cutoff at 1.5 × message freq
    Wn = min(1.5*fm / (fs/2), 0.99);
    [b, a] = butter(6, Wn, 'low');
    rx_msg  = filter(b, a, demod);

    out_snr_db = measure_analog_snr(rx_msg, tx_msg);
end


% =========================================================================
%  AM DSB-TC — Double Sideband Transmitted / Full Carrier
% =========================================================================

function [tx_signal, t, msg] = am_dsbtc_mod(params)
%AM_DSBTC_MOD  s(t) = (1 + ka*m(t)) * cos(2*pi*fc*t + phi_c)

    fs  = params.fs;
    fc  = params.fc;
    % Jitter message frequency by +/- 10% to prevent leakage
    fm  = params.msg_freq + (rand()*0.2 - 0.1)*params.msg_freq;
    dur = params.duration;
    ka  = params.mod_index;                  % 0 < ka <= 1

    phi_m = 2*pi*rand();
    phi_c = 2*pi*rand();

    t   = 0 : 1/fs : dur - 1/fs;
    msg = cos(2*pi*fm*t + phi_m);
    tx_signal = (1 + ka*msg) .* cos(2*pi*fc*t + phi_c);
end

function [rx_msg, out_snr_db] = am_dsbtc_demod(rx_signal, params, tx_msg)
%AM_DSBTC_DEMOD  Envelope detection (Hilbert transform) then LPF.

    fs = params.fs;
    fm = params.msg_freq;

    % Envelope detection
    envelope = abs(hilbert(rx_signal));

    % LPF
    Wn = min(1.5*fm / (fs/2), 0.99);
    [b, a] = butter(6, Wn, 'low');
    rx_msg  = filter(b, a, envelope);

    % Remove DC component (the "1" in  1 + ka*m)
    trim    = max(round(0.1 * length(rx_msg)), 1);
    rx_msg(trim:end) = rx_msg(trim:end) - mean(rx_msg(trim:end));

    out_snr_db = measure_analog_snr(rx_msg, tx_msg);
end


% =========================================================================
%  FM — Frequency Modulation
% =========================================================================

function [tx_signal, t, msg] = fm_mod(params)
%FM_MOD  s(t) = cos(2*pi*fc*t + phi_c + 2*pi*kf * integral(m(tau),0,t))

    fs  = params.fs;
    fc  = params.fc;
    % Jitter message frequency by +/- 10% to prevent leakage
    fm  = params.msg_freq + (rand()*0.2 - 0.1)*params.msg_freq;
    dur = params.duration;
    kf  = params.fm_freq_dev;                % Hz per unit of m(t)

    phi_m = 2*pi*rand();
    phi_c = 2*pi*rand();

    t   = 0 : 1/fs : dur - 1/fs;
    msg = cos(2*pi*fm*t + phi_m);

    msg_int   = cumsum(msg) / fs;            % numerical integration
    tx_signal = cos(2*pi*fc*t + phi_c + 2*pi*kf*msg_int);
end

function [rx_msg, out_snr_db] = fm_demod(rx_signal, params, tx_msg)
%FM_DEMOD  FM discriminator: differentiate instantaneous phase.

    fs = params.fs;
    fc = params.fc;
    fm = params.msg_freq;
    kf = params.fm_freq_dev;

    % Analytic signal → instantaneous phase → differentiate → inst. freq
    analytic   = hilbert(rx_signal);
    inst_phase = unwrap(angle(analytic));
    inst_freq  = [0, diff(inst_phase)] * fs / (2*pi);   % Hz
    rx_demod   = (inst_freq - fc) / kf;                 % recover m(t)

    % LPF to suppress out-of-band noise
    Wn = min(1.5*fm / (fs/2), 0.99);
    [b, a] = butter(6, Wn, 'low');
    rx_msg  = filter(b, a, rx_demod);

    out_snr_db = measure_analog_snr(rx_msg, tx_msg);
end


% =========================================================================
%  SHARED HELPER — Output SNR measurement for analog demodulation
% =========================================================================

function out_snr_db = measure_analog_snr(rx_msg, tx_msg)
%MEASURE_ANALOG_SNR  Estimate output SNR by comparing recovered vs original.
%   Trims the first 10% of samples to avoid filter transients, uses xcorr
%   to align phase/delay caused by filters, and then least-squares scaling.

    trim = max(round(0.1 * length(rx_msg)), 1);
    n    = min(length(rx_msg) - trim + 1, length(tx_msg) - trim + 1);
    if n < 10
        out_snr_db = 0;
        return;
    end

    rx_t = rx_msg(trim : trim+n-1);
    tx_t = tx_msg(trim : trim+n-1);

    % Remove DC offsets
    rx_t = rx_t - mean(rx_t);
    tx_t = tx_t - mean(tx_t);

    % Cross-correlate to find phase delay from filters (search up to 500 samples)
    max_lag = min(500, floor(length(rx_t)/2));
    [c, lags] = xcorr(rx_t, tx_t, max_lag);
    [~, I] = max(c);
    delay = lags(I);

    % Align signals
    if delay > 0
        rx_t = rx_t(1+delay : end);
        tx_t = tx_t(1 : end-delay);
    elseif delay < 0
        rx_t = rx_t(1 : end+delay);
        tx_t = tx_t(1-delay : end);
    end

    % Least-squares amplitude alignment:  min || tx - s*rx ||^2
    denom = dot(rx_t, rx_t);
    if denom == 0
        out_snr_db = 0;
        return;
    end
    sc     = dot(tx_t, rx_t) / denom;
    rx_adj = rx_t * sc;
    noise  = tx_t - rx_adj;

    s_pow = mean(tx_t.^2);
    n_pow = mean(noise.^2);

    if n_pow > 0
        out_snr_db = 10*log10(s_pow / n_pow);
    else
        out_snr_db = 100;          % effectively infinite
    end
end
