function ch = channel_models()
%CHANNEL_MODELS  Channel simulation functions for the Digital Twin project.
%
%   ch = channel_models()  returns a struct with two function handles:
%
%   [rx_signal, measured_snr_dB] = ch.awgn(tx_signal, snr_dB)
%       Additive White Gaussian Noise channel.
%
%   [rx_signal, measured_snr_dB] = ch.rayleigh(tx_signal, snr_dB, samples_per_symbol)
%       Flat Rayleigh fading (one coefficient per symbol) + AWGN.
%       samples_per_symbol sets the fading block size.
%
%   No Communications Toolbox required.
%   See also: modulation_bank, run_sweep

    ch.awgn     = @awgn_channel;
    ch.rayleigh = @rayleigh_channel;
end


% =========================================================================
%  AWGN Channel
% =========================================================================

function [rx_signal, measured_snr_db] = awgn_channel(tx_signal, snr_db, bw_ratio)
%AWGN_CHANNEL  Adds white Gaussian noise at the specified SNR.
%
%   SNR is defined as:  10*log10( signal_power / noise_power )
%   bw_ratio (optional) scales noise to remove processing gain.

    if nargin < 3, bw_ratio = 1; end
    sig_power = mean(tx_signal.^2);

    if sig_power == 0
        % Edge case: all-zero signal (e.g., OOK with all-zero bits)
        rx_signal       = tx_signal;
        measured_snr_db = -Inf;
        return;
    end

    noise_power = (sig_power * bw_ratio) / (10^(snr_db / 10));
    noise       = sqrt(noise_power) * randn(size(tx_signal));
    rx_signal   = tx_signal + noise;

    % Report the realised SNR (should be close to requested)
    actual_noise_power = mean(noise.^2);
    if actual_noise_power > 0
        measured_snr_db = 10*log10((sig_power * bw_ratio) / actual_noise_power);
    else
        measured_snr_db = 100;     % effectively infinite
    end
end


% =========================================================================
%  Rayleigh Fading + AWGN Channel
% =========================================================================

function [rx_signal, measured_snr_db] = rayleigh_channel(tx_signal, snr_db, sps, bw_ratio)
%RAYLEIGH_CHANNEL  Flat Rayleigh fading (block fading) followed by AWGN.
%
%   The signal is divided into blocks of length sps (samples-per-symbol).
%   Each block is multiplied by an independent Rayleigh-distributed gain
%   |h_k|, where h_k ~ CN(0,1)/sqrt(2)  so that  E[|h_k|^2] = 1.
%
%   AWGN noise power is set relative to the *original* (un-faded) signal
%   power, matching the standard "average SNR" definition for fading
%   channels. bw_ratio corrects for processing gain.

    if nargin < 4, bw_ratio = 1; end
    N          = length(tx_signal);
    num_blocks = ceil(N / sps);

    % --- Generate Rayleigh fading coefficients (one per block) ---
    %   h_complex ~ CN(0,1)  →  |h_complex| is Rayleigh with E[|h|^2]=1
    h_complex = (randn(1, num_blocks) + 1j*randn(1, num_blocks)) / sqrt(2);
    h_mag     = abs(h_complex);              % Rayleigh envelope

    % --- Apply block fading ---
    faded = zeros(size(tx_signal));
    for k = 1:num_blocks
        idx_s = (k-1)*sps + 1;
        idx_e = min(k*sps, N);
        faded(idx_s:idx_e) = h_mag(k) * tx_signal(idx_s:idx_e);
    end

    % --- Add AWGN (average-SNR definition) ---
    sig_power = mean(tx_signal.^2);          % original (un-faded) power

    if sig_power == 0
        rx_signal       = faded;
        measured_snr_db = -Inf;
        return;
    end

    noise_power = (sig_power * bw_ratio) / (10^(snr_db / 10));
    noise       = sqrt(noise_power) * randn(size(faded));
    rx_signal   = faded + noise;

    % --- Measured SNR (faded signal power vs. noise power) ---
    faded_power        = mean(faded.^2);
    actual_noise_power = mean(noise.^2);
    if actual_noise_power > 0
        measured_snr_db = 10*log10((faded_power * bw_ratio) / actual_noise_power);
    else
        measured_snr_db = 100;
    end
end
