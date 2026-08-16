% SNR sweep
snr_range = -5 : 1 : 30;          % dB
num_snr   = length(snr_range);

% Trials per config (for statistically significant fading/noise averaging)
num_trials = 20;

% Modulation catalogue
digital_mods = {'ASK', 'FSK', 'BPSK', 'QPSK'};
analog_mods  = {'AM_DSBSC', 'AM_DSBTC', 'FM'};
all_mods     = [digital_mods, analog_mods];
num_mods     = length(all_mods);

% Channel catalogue
channel_types = {'AWGN', 'Rayleigh'};
num_channels  = length(channel_types);

% Packet-loss definition (digital only)
packet_size     = 100;             % bits per packet
ber_loss_thresh = 0.10;            % packet "lost" if BER > 10 %

% Simulation parameters
params.fs          = 100000;       % Sample rate (Hz)
params.fc          = 10000;        % Carrier frequency (Hz)
params.symbol_rate = 1000;         % Symbol rate (Baud)
params.msg_freq    = 1000;         % Analog message frequency (Hz)
params.num_bits    = 1000;         % Bits per trial
params.duration    = 1.0;          % Analog duration (s)
params.fm_freq_dev = 5000;         % FM freq deviation (Hz)
params.mod_index   = 0.8;          % AM modulation index (0 to 1)

%% -------------------------------------------------------------------- %%
%  2.  LOAD FUNCTION HANDLES
%% -------------------------------------------------------------------- %%

mb = modulation_bank();
ch = channel_models();

%% -------------------------------------------------------------------- %%
%  3.  PRE-ALLOCATE RESULT ARRAYS
%% -------------------------------------------------------------------- %%

total = num_mods * num_channels * num_snr * num_trials;

res_mod_type          = cell(total, 1);
res_is_digital        = zeros(total, 1);
res_channel_type      = cell(total, 1);
res_input_snr         = zeros(total, 1);
res_trial             = zeros(total, 1);
res_ber               = NaN(total, 1);
res_ber_reliable      = false(total, 1);
res_received_snr      = zeros(total, 1);
res_output_snr        = NaN(total, 1);
res_packet_loss       = NaN(total, 1);
res_bw_10db           = zeros(total, 1);
res_peak_psd          = zeros(total, 1);
res_spectral_flatness = zeros(total, 1);
res_spectral_centroid = zeros(total, 1);

%% -------------------------------------------------------------------- %%
%  4.  MAIN SWEEP LOOP
%% -------------------------------------------------------------------- %%

row = 0;
spb = round(params.fs / params.symbol_rate);   % samples per bit (digital)

tic;   % start timer

for m = 1:num_mods
    mod_name = all_mods{m};
    is_dig   = ismember(mod_name, digital_mods);

    for c = 1:num_channels
        ch_name = channel_types{c};
        fprintf('  %-10s  |  %-8s  |  SNR %+3d to %+3d dB ...', ...
                mod_name, ch_name, snr_range(1), snr_range(end));

        for s = 1:num_snr
            snr_db = snr_range(s);
            
            for tr = 1:num_trials
                row = row + 1;

                % ---------- Modulate ----------
                if is_dig
                    [tx_sig, t_vec, tx_bits] = call_mod(mb, mod_name, params);
                    bw_ratio = params.fs / params.symbol_rate;
                    if strcmp(mod_name, 'QPSK')
                        bw_ratio = params.fs / (params.symbol_rate / 2);
                    end
                else
                    [tx_sig, t_vec, tx_msg]  = call_mod(mb, mod_name, params);
                    bw_ratio = params.fs / (2 * params.msg_freq);
                end

                % ---------- Channel ----------
                if strcmp(mod_name, 'QPSK')
                    sps_ch = round(params.fs / (params.symbol_rate / 2));
                else
                    sps_ch = spb;
                end

                if strcmp(ch_name, 'AWGN')
                    [rx_sig, meas_snr] = ch.awgn(tx_sig, snr_db, bw_ratio);
                else
                    [rx_sig, meas_snr] = ch.rayleigh(tx_sig, snr_db, sps_ch, bw_ratio);
                end

                % ---------- Demodulate ----------
                if is_dig
                    [rx_bits, ber_val] = call_demod(mb, mod_name, rx_sig, params, tx_bits);
                else
                    [~, out_snr_val]   = call_demod(mb, mod_name, rx_sig, params, tx_msg);
                end

                % ---------- Store common fields ----------
                res_mod_type{row}        = mod_name;
                res_is_digital(row)      = is_dig;
                res_channel_type{row}    = ch_name;
                res_input_snr(row)       = snr_db;
                res_trial(row)           = tr;
                res_received_snr(row)    = meas_snr;

                % ---------- Digital-specific metrics ----------
                if is_dig
                    res_ber(row)        = ber_val;
                    res_output_snr(row) = meas_snr;
                    
                    % Reliable BER (at least 10 errors)
                    n = min(length(tx_bits), length(rx_bits));
                    num_errors = sum(tx_bits(1:n) ~= rx_bits(1:n));
                    res_ber_reliable(row) = num_errors >= 10;

                    % Packet loss
                    num_pkts = floor(n / packet_size);
                    lost = 0;
                    for p = 1:num_pkts
                        pkt = ((p-1)*packet_size + 1) : (p*packet_size);
                        pkt_ber = sum(tx_bits(pkt) ~= rx_bits(pkt)) / packet_size;
                        lost = lost + (pkt_ber > ber_loss_thresh);
                    end
                    if num_pkts > 0
                        res_packet_loss(row) = lost / num_pkts;
                    end
                else
                    res_output_snr(row) = out_snr_val;
                    res_ber_reliable(row) = false; % N/A
                end

                % ---------- Spectral features (of RECEIVED signal) ----------
                feat = compute_spectral_features(rx_sig, params.fs);
                res_bw_10db(row)           = feat.bw_10db;
                res_peak_psd(row)          = feat.peak_psd_db;
                res_spectral_flatness(row) = feat.spectral_flatness;
                res_spectral_centroid(row) = feat.spectral_centroid;
            end
        end

        fprintf('  done\n');
    end
end

elapsed = toc;
fprintf('\nSweep completed in %.1f s  (%d configurations)\n', elapsed, total);

%% -------------------------------------------------------------------- %%
%  5.  BUILD TABLE & SAVE
%% -------------------------------------------------------------------- %%

T = table( ...
    res_mod_type,          ...
    res_is_digital,        ...
    res_channel_type,      ...
    res_input_snr,         ...
    res_trial,             ...
    res_ber,               ...
    res_ber_reliable,      ...
    res_received_snr,      ...
    res_output_snr,        ...
    res_packet_loss,       ...
    res_bw_10db,           ...
    res_peak_psd,          ...
    res_spectral_flatness, ...
    res_spectral_centroid, ...
    'VariableNames', { ...
        'ModType',       'IsDigital',       'ChannelType', ...
        'InputSNR_dB',   'Trial',           'BER', ...
        'BER_Reliable',  'ReceivedSNR_dB',  'OutputSNR_dB', ...
        'PacketLossRate','BW_10dB',         'PeakPSD_dB', ...
        'SpectralFlatness','SpectralCentroid'});

save('ground_truth_dataset.mat', 'T', 'params', 'snr_range');
writetable(T, 'ground_truth_dataset.csv');

fprintf('\n  Saved:  ground_truth_dataset.mat\n');
fprintf('  Saved:  ground_truth_dataset.csv\n');
fprintf('  Table size:  %d rows x %d columns\n\n', height(T), width(T));

%% -------------------------------------------------------------------- %%
%  6.  GENERATE PLOTS
%% -------------------------------------------------------------------- %%

fprintf('Generating plots ...\n');
plot_results();
fprintf('All done!\n');


% ========================================================================
%                        LOCAL HELPER FUNCTIONS
% ========================================================================

function [out1, out2, out3] = call_mod(mb, mod_name, params)
%CALL_MOD  Dispatch to the correct modulation function.
    switch mod_name
        case 'ASK',       [out1,out2,out3] = mb.ask_mod(params);
        case 'FSK',       [out1,out2,out3] = mb.fsk_mod(params);
        case 'BPSK',      [out1,out2,out3] = mb.bpsk_mod(params);
        case 'QPSK',      [out1,out2,out3] = mb.qpsk_mod(params);
        case 'AM_DSBSC',  [out1,out2,out3] = mb.am_dsbsc_mod(params);
        case 'AM_DSBTC',  [out1,out2,out3] = mb.am_dsbtc_mod(params);
        case 'FM',        [out1,out2,out3] = mb.fm_mod(params);
        otherwise,        error('Unknown modulation: %s', mod_name);
    end
end

function [out1, out2] = call_demod(mb, mod_name, rx_sig, params, ref)
%CALL_DEMOD  Dispatch to the correct demodulation function.
    switch mod_name
        case 'ASK',       [out1,out2] = mb.ask_demod(rx_sig, params, ref);
        case 'FSK',       [out1,out2] = mb.fsk_demod(rx_sig, params, ref);
        case 'BPSK',      [out1,out2] = mb.bpsk_demod(rx_sig, params, ref);
        case 'QPSK',      [out1,out2] = mb.qpsk_demod(rx_sig, params, ref);
        case 'AM_DSBSC',  [out1,out2] = mb.am_dsbsc_demod(rx_sig, params, ref);
        case 'AM_DSBTC',  [out1,out2] = mb.am_dsbtc_demod(rx_sig, params, ref);
        case 'FM',        [out1,out2] = mb.fm_demod(rx_sig, params, ref);
        otherwise,        error('Unknown modulation: %s', mod_name);
    end
end

function feat = compute_spectral_features(signal, fs)
%COMPUTE_SPECTRAL_FEATURES  FFT/PSD-based features for the twin's input.
%
%   Returns a struct with:
%     .peak_psd_db       — peak of the one-sided PSD  (dB)
%     .bw_3db            — 3 dB bandwidth              (Hz)
%     .spectral_flatness — Wiener entropy (geometric / arithmetic mean of PSD)
%     .spectral_centroid — power-weighted average frequency (Hz)

    % Normalize signal to unit power to make features invariant to absolute receive power
    signal = signal / std(signal);

    N = length(signal);
    S = abs(fftshift(fft(signal))).^2 / N;       % periodogram PSD
    f = (-N/2 : N/2-1) * (fs / N);

    % ---- Positive-frequency half only ----
    pos = f >= 0;
    f_p = f(pos);
    S_p = S(pos);

    % Smooth PSD slightly to reduce noise variance for feature extraction
    S_p_smooth = movmedian(S_p, 5);

    % Find peak frequency
    [peak_val, peak_idx] = max(S_p_smooth);
    f_peak = f_p(peak_idx);

    % Peak PSD (dB)
    feat.peak_psd_db = 10*log10(peak_val + eps);

    % 10 dB bandwidth (frequencies where PSD >= peak/10)
    % Restrict search window to f_peak +/- 5 kHz to prevent catching 
    % far-away spurious noise spikes at low SNR
    window = (f_p >= max(0, f_peak - 5000)) & (f_p <= f_peak + 5000);
    S_p_window = S_p_smooth(window);
    f_window   = f_p(window);

    tenth_peak = peak_val / 10;
    above      = S_p_window >= tenth_peak;
    if any(above)
        f_above      = f_window(above);
        feat.bw_10db = f_above(end) - f_above(1);
    else
        feat.bw_10db = 0;
    end

    % Spectral flatness (Wiener entropy)  ∈ [0, 1]
    S_nz = S_p(S_p > 0);
    if ~isempty(S_nz)
        feat.spectral_flatness = exp(mean(log(S_nz))) / mean(S_nz);
    else
        feat.spectral_flatness = 0;
    end

    % Spectral centroid (Hz)
    total = sum(S_p);
    if total > 0
        feat.spectral_centroid = sum(f_p .* S_p) / total;
    else
        feat.spectral_centroid = 0;
    end
end
