function plot_results()
%PLOT_RESULTS  Generate BER-vs-SNR and output-SNR-vs-SNR plots.
%
%   plot_results()   loads ground_truth_dataset.mat from the current folder
%   and produces four publication-quality figures:
%
%     1. BER vs SNR — digital modulations, AWGN channel
%     2. BER vs SNR — digital modulations, Rayleigh channel
%     3. Output SNR vs Input SNR — analog modulations, AWGN channel
%     4. Output SNR vs Input SNR — analog modulations, Rayleigh channel
%
%   Figures are also saved as PNG files in the current folder.
%
%   See also: run_sweep, modulation_bank, channel_models

    % ---- Load dataset ----
    if ~isfile('ground_truth_dataset.mat')
        error('ground_truth_dataset.mat not found.  Run  run_sweep  first.');
    end
    data      = load('ground_truth_dataset.mat');
    T         = data.T;
    snr_range = data.snr_range;

    % ---- Colour and marker palettes ----
    colours = lines(7);   % MATLAB default colourmap — 7 distinct colours
    markers = {'o', 's', 'd', '^', 'v', '>', '<'};

    digital_mods = {'ASK', 'FSK', 'BPSK', 'QPSK'};
    analog_mods  = {'AM_DSBSC', 'AM_DSBTC', 'FM'};

    % =====================================================================
    %   FIGURE 1 — BER vs SNR  (Digital, AWGN)
    % =====================================================================
    fig1 = figure('Name', 'BER vs SNR — AWGN', ...
                  'Position', [100 100 800 550]);
    hold on; grid on;

    for k = 1:length(digital_mods)
        mod_name = digital_mods{k};
        mask = strcmp(T.ModType, mod_name) & strcmp(T.ChannelType, 'AWGN');
        sub  = T(mask, :);
        
        % Only plot reliable BERs (truncate curves before the false floor)
        valid = sub.BER_Reliable == true;
        [snr_vals, ber_plot] = average_trials(sub.InputSNR_dB(valid), sub.BER(valid));

        if ~isempty(snr_vals)
            semilogy(snr_vals, ber_plot, ...
                     ['-' markers{k}], ...
                     'Color',      colours(k,:), ...
                     'LineWidth',  1.5, ...
                     'MarkerSize', 5, ...
                     'MarkerFaceColor', colours(k,:), ...
                     'DisplayName', mod_name);
        end
    end

    % Theoretical BPSK limit for validation
    ber_theory = 0.5 * erfc(sqrt(10.^(snr_range/10)));
    semilogy(snr_range, ber_theory, '--k', 'LineWidth', 1.5, 'DisplayName', 'BPSK Theory');

    xlabel('SNR (dB)', 'FontSize', 12);
    ylabel('Bit Error Rate', 'FontSize', 12);
    title('BER vs SNR — Digital Modulations (AWGN Channel)', 'FontSize', 14);
    legend('Location', 'southwest', 'FontSize', 11);
    ylim([1e-6 1]);
    set(gca, 'FontSize', 11);
    set(gca, 'YScale', 'log');
    hold off;

    saveas(fig1, fullfile('Proofs & graphs', 'ber_vs_snr_awgn.png'));
    fprintf('  Saved:  Proofs & graphs/ber_vs_snr_awgn.png\n');

    % =====================================================================
    %   FIGURE 2 — BER vs SNR  (Digital, Rayleigh)
    % =====================================================================
    fig2 = figure('Name', 'BER vs SNR — Rayleigh', ...
                  'Position', [150 100 800 550]);
    hold on; grid on;

    for k = 1:length(digital_mods)
        mod_name = digital_mods{k};
        mask = strcmp(T.ModType, mod_name) & strcmp(T.ChannelType, 'Rayleigh');
        sub  = T(mask, :);
        
        % Only plot reliable BERs
        valid = sub.BER_Reliable == true;
        [snr_vals, ber_plot] = average_trials(sub.InputSNR_dB(valid), sub.BER(valid));

        if ~isempty(snr_vals)
            semilogy(snr_vals, ber_plot, ...
                     ['-' markers{k}], ...
                     'Color',      colours(k,:), ...
                     'LineWidth',  1.5, ...
                     'MarkerSize', 5, ...
                     'MarkerFaceColor', colours(k,:), ...
                     'DisplayName', mod_name);
        end
    end

    xlabel('SNR (dB)', 'FontSize', 12);
    ylabel('Bit Error Rate', 'FontSize', 12);
    title('BER vs SNR — Digital Modulations (Rayleigh Channel)', 'FontSize', 14);
    legend('Location', 'southwest', 'FontSize', 11);
    ylim([1e-6 1]);
    set(gca, 'FontSize', 11);
    set(gca, 'YScale', 'log');
    hold off;

    saveas(fig2, fullfile('Proofs & graphs', 'ber_vs_snr_rayleigh.png'));
    fprintf('  Saved:  Proofs & graphs/ber_vs_snr_rayleigh.png\n');

    % =====================================================================
    %   FIGURE 3 — Output SNR vs Input SNR  (Analog, AWGN)
    % =====================================================================
    fig3 = figure('Name', 'Output SNR — AWGN', ...
                  'Position', [200 100 800 550]);
    hold on; grid on;

    for k = 1:length(analog_mods)
        mod_name = analog_mods{k};
        mask = strcmp(T.ModType, mod_name) & strcmp(T.ChannelType, 'AWGN');
        sub  = T(mask, :);
        
        [snr_vals, out_snr] = average_trials(sub.InputSNR_dB, sub.OutputSNR_dB);

        plot(snr_vals, out_snr, ...
             ['-' markers{k}], ...
             'Color',      colours(k+4,:), ...
             'LineWidth',  1.5, ...
             'MarkerSize', 5, ...
             'MarkerFaceColor', colours(k+4,:), ...
             'DisplayName', strrep(mod_name, '_', ' '));
    end

    % Reference line: output = input (no improvement / no degradation)
    plot(snr_range, snr_range, '--k', 'LineWidth', 1, ...
         'DisplayName', 'Output = Input');

    xlabel('Input SNR (dB)', 'FontSize', 12);
    ylabel('Output SNR (dB)', 'FontSize', 12);
    title('Output SNR vs Input SNR — Analog Modulations (AWGN)', 'FontSize', 14);
    legend('Location', 'northwest', 'FontSize', 11);
    set(gca, 'FontSize', 11);
    hold off;

    saveas(fig3, fullfile('Proofs & graphs', 'output_snr_awgn.png'));
    fprintf('  Saved:  Proofs & graphs/output_snr_awgn.png\n');

    % =====================================================================
    %   FIGURE 4 — Output SNR vs Input SNR  (Analog, Rayleigh)
    % =====================================================================
    fig4 = figure('Name', 'Output SNR — Rayleigh', ...
                  'Position', [250 100 800 550]);
    hold on; grid on;

    for k = 1:length(analog_mods)
        mod_name = analog_mods{k};
        mask = strcmp(T.ModType, mod_name) & strcmp(T.ChannelType, 'Rayleigh');
        sub  = T(mask, :);
        
        [snr_vals, out_snr] = average_trials(sub.InputSNR_dB, sub.OutputSNR_dB);

        plot(snr_vals, out_snr, ...
             ['-' markers{k}], ...
             'Color',      colours(k+4,:), ...
             'LineWidth',  1.5, ...
             'MarkerSize', 5, ...
             'MarkerFaceColor', colours(k+4,:), ...
             'DisplayName', strrep(mod_name, '_', ' '));
    end

    plot(snr_range, snr_range, '--k', 'LineWidth', 1, ...
         'DisplayName', 'Output = Input');

    xlabel('Input SNR (dB)', 'FontSize', 12);
    ylabel('Output SNR (dB)', 'FontSize', 12);
    title('Output SNR vs Input SNR — Analog Modulations (Rayleigh)', 'FontSize', 14);
    legend('Location', 'northwest', 'FontSize', 11);
    set(gca, 'FontSize', 11);
    hold off;

    saveas(fig4, fullfile('Proofs & graphs', 'output_snr_rayleigh.png'));
    fprintf('  Saved:  Proofs & graphs/output_snr_rayleigh.png\n');

    % =====================================================================
    %   FIGURE 5 — Packet Loss Rate vs SNR  (Digital, both channels)
    % =====================================================================
    fig5 = figure('Name', 'Packet Loss', ...
                  'Position', [300 100 800 550]);

    for ch_idx = 1:2
        ch_name = {'AWGN', 'Rayleigh'};
        subplot(1, 2, ch_idx);
        hold on; grid on;

        for k = 1:length(digital_mods)
            mod_name = digital_mods{k};
            mask = strcmp(T.ModType, mod_name) & ...
                   strcmp(T.ChannelType, ch_name{ch_idx});
            sub  = T(mask, :);
            
            [snr_vals, pkt_loss] = average_trials(sub.InputSNR_dB, sub.PacketLossRate);

            plot(snr_vals, pkt_loss, ...
                 ['-' markers{k}], ...
                 'Color',      colours(k,:), ...
                 'LineWidth',  1.5, ...
                 'MarkerSize', 4, ...
                 'MarkerFaceColor', colours(k,:), ...
                 'DisplayName', mod_name);
        end

        xlabel('SNR (dB)', 'FontSize', 11);
        ylabel('Packet Loss Rate', 'FontSize', 11);
        title(['Packet Loss — ' ch_name{ch_idx}], 'FontSize', 13);
        legend('Location', 'northeast', 'FontSize', 10);
        ylim([-0.05 1.05]);
        set(gca, 'FontSize', 10);
        hold off;
    end

    saveas(fig5, fullfile('Proofs & graphs', 'packet_loss.png'));
    fprintf('  Saved:  Proofs & graphs/packet_loss.png\n');

    % =====================================================================
    %   FIGURE 6 — Spectral Features Comparison
    % =====================================================================
    fig6 = figure('Name', 'Spectral Features', ...
                  'Position', [350 100 900 600]);

    % Get one row per modulation type. Since spectral features now vary with
    % SNR and fading, we'll plot the clean (AWGN, SNR=30dB) features.
    all_mods = unique(T.ModType, 'stable');
    n_mods   = length(all_mods);
    bw       = zeros(n_mods, 1);
    peak_p   = zeros(n_mods, 1);
    sf       = zeros(n_mods, 1);
    sc       = zeros(n_mods, 1);

    for k = 1:n_mods
        mask = strcmp(T.ModType, all_mods{k}) & strcmp(T.ChannelType, 'AWGN') & T.InputSNR_dB == 30;
        idx  = find(mask, 1, 'first');
        if isempty(idx) % Fallback if 30dB not found
            idx = find(strcmp(T.ModType, all_mods{k}), 1, 'first');
        end
        bw(k)     = T.BW_10dB(idx);
        peak_p(k) = T.PeakPSD_dB(idx);
        sf(k)     = T.SpectralFlatness(idx);
        sc(k)     = T.SpectralCentroid(idx);
    end

    labels = strrep(all_mods, '_', ' ');

    subplot(2,2,1);
    bar(bw, 'FaceColor', [0.3 0.6 0.9]);
    set(gca, 'XTickLabel', labels, 'XTickLabelRotation', 30, 'FontSize', 9);
    ylabel('Hz'); title('10 dB Bandwidth');

    subplot(2,2,2);
    bar(peak_p, 'FaceColor', [0.9 0.4 0.3]);
    set(gca, 'XTickLabel', labels, 'XTickLabelRotation', 30, 'FontSize', 9);
    ylabel('dB'); title('Peak PSD');

    subplot(2,2,3);
    bar(sf, 'FaceColor', [0.4 0.8 0.4]);
    set(gca, 'XTickLabel', labels, 'XTickLabelRotation', 30, 'FontSize', 9);
    ylabel('Ratio'); title('Spectral Flatness');

    subplot(2,2,4);
    bar(sc, 'FaceColor', [0.8 0.6 0.9]);
    set(gca, 'XTickLabel', labels, 'XTickLabelRotation', 30, 'FontSize', 9);
    ylabel('Hz'); title('Spectral Centroid');

    sgtitle('Spectral Features — All Modulation Schemes', 'FontSize', 14);

    saveas(fig6, fullfile('Proofs & graphs', 'spectral_features.png'));
    fprintf('  Saved:  Proofs & graphs/spectral_features.png\n');

    fprintf('\n  All plots generated successfully.\n');
end

function [x, y] = average_trials(snr_col, metric_col)
    if isempty(snr_col)
        x = []; y = []; return;
    end
    x = unique(snr_col);
    y = zeros(size(x));
    for i = 1:length(x)
        y(i) = mean(metric_col(snr_col == x(i)), 'omitnan');
    end
end
