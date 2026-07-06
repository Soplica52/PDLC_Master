close all; clear; clc;

% --- Data Entry ---
% Shared Voltage Vector
v_part1 = [0, 0.5, 1];
v_part2 = 1.2:0.2:6;
v_part3 = 6.5:0.5:15;
v_part4 = 16;
voltage = [v_part1, v_part2, v_part3, v_part4];

% --- DATASET 1: No Glass (Bez szkła) ---
no_glass_up = [106.3, 106.3, 106.4, 106.5, 106.6, 106.7, 106.9, 107.1, 107.3, ...
               107.6, 107.9, 108.3, 108.7, 109.1, 109.6, 110, 110.6, 111, ...
               111.4, 111.8, 112.1, 112.4, 112.7, 112.9, 113.1, 113.3, 113.5, ...
               113.6, 113.8, 114, 114.1, 114.3, 114.4, 114.5, 114.5, 114.6, ...
               114.6, 114.7, 114.7, 114.7, 114.8, 114.8, 114.8, 114.9, 114.9, ...
               114.9, 115];

% --- DATASET 2: With Glass, Foil facing Source (Folia skierowana do źródła) ---
foil_src_up = [91.5, 91.5, 91.7, 91.8, 91.9, 92, 92.2, 92.3, 92.6, 92.8, ...
               93.1, 93.4, 93.8, 94.3, 94.9, 95.4, 95.9, 96.6, 97.3, 97.9, ...
               98.6, 99.2, 99.7, 100.2, 100.6, 100.9, 101.3, 101.5, 102, ...
               102.3, 102.5, 102.9, 103, 103.2, 103.3, 103.4, 103.5, 103.5, ...
               103.6, 103.7, 103.7, 103.8, 103.9, 104, 104, 104, 104.1];
               
foil_src_down = [93.9, 94.1, 94.3, 94.5, 94.8, 95, 95.2, 95.6, 95.9, 96.3, ...
                 96.7, 97.1, 97.6, 98, 98.5, 98.8, 99.2, 99.6, 99.9, 100.4, ...
                 100.6, 100.9, 101.2, 101.4, 101.6, 101.8, 101.9, 102.1, 102.5, ...
                 102.7, 103, 103.1, 103.3, 103.3, 103.5, 103.6, 103.6, 103.8, ...
                 103.8, 103.9, 103.9, 103.9, 104, 104, 104.1, 104.1, 104.1];

% --- DATASET 3: With Glass, Glass facing Source (Szkło skierowane do źródła) ---
glass_src_up1 = [93.4, 93.5, 93.7, 93.8, 93.9, 94.1, 94.2, 94.4, 94.7, 94.9, ...
                 95.3, 95.6, 96, 96.5, 97, 97.5, 98.1, 98.7, 99.2, 99.7, ...
                 100.1, 100.6, 101, 101.2, 101.5, 101.8, 102, 102.2, 102.5, ...
                 102.8, 103, 103.2, 103.3, 103.4, 103.5, 103.6, 103.7, 103.8, ...
                 103.8, 103.9, 104, 104.1, 104.2, 104.2, 104.2, 104.2, 104.3];
                 
glass_src_down = [95.5, 95.7, 95.8, 96, 96.2, 96.5, 96.8, 97.1, 97.4, 97.9, ...
                  98.3, 98.7, 99.2, 99.6, 100.1, 100.5, 101, 101.5, 102, 102.4, ...
                  102.7, 103, 103.3, 103.6, 103.9, 104.1, 104.3, 104.5, 104.8, ...
                  105.1, 105.3, 105.5, 105.7, 105.8, 105.9, 106, 106.1, 106.1, ...
                  106.2, 106.3, 106.3, 106.4, 106.4, 106.5, 106.5, 106.6, 106.6];
                  
glass_src_up2 = [95.5, 95.5, 95.6, 95.7, 95.9, 96, 96.2, 96.4, 96.6, 96.9, ...
                 97.8, 98.1, 98.4, 98.8, 99.2, 99.6, 100.2, 100.7, 101.2, 101.7, ...
                 102.2, 102.6, 103, 103.3, 103.6, 103.9, 104.1, 104.3, 104.6, ...
                 104.9, 105.2, 105.4, 105.6, 105.7, 105.8, 105.8, 105.9, 106, ...
                 106, 106.1, 106.1, 106.1, 106.2, 106.3, 106.4, 106.4, 106.5];

% ==========================================
% CALCULATIONS (Error and % Change)
% ==========================================
% 1. No Glass Calculation
noglass_pct_change = ((no_glass_up(end) - no_glass_up(1)) / no_glass_up(1)) * 100;

% 2. Foil Facing Source Calculations
foil_all = [foil_src_up; foil_src_down];
foil_mean = mean(foil_all, 1);
foil_std = std(foil_all, 1, 1); % Standard deviation between passes
foil_mean_error = mean(foil_std);
foil_pct_change = ((foil_mean(end) - foil_mean(1)) / foil_mean(1)) * 100;

% 3. Glass Facing Source Calculations
glass_all = [glass_src_up1; glass_src_down; glass_src_up2];
glass_mean = mean(glass_all, 1);
glass_std = std(glass_all, 1, 1); % Standard deviation between passes
glass_mean_error = mean(glass_std);
glass_pct_change = ((glass_mean(end) - glass_mean(1)) / glass_mean(1)) * 100;

% Print calculations to the command window
fprintf('--- ERROR & PERCENTAGE CHANGE RESULTS ---\n');
fprintf('No Glass Config -> Pct Change: %.2f%%\n\n', noglass_pct_change);
fprintf('Foil -> Source Config -> Mean Error: %.4f | Pct Change: %.2f%%\n\n', foil_mean_error, foil_pct_change);
fprintf('Glass -> Source Config -> Mean Error: %.4f | Pct Change: %.2f%%\n', glass_mean_error, glass_pct_change);
fprintf('-----------------------------------------\n');

% ==========================================
% PLOTTING (Without Error shading)
% ==========================================
% --- FIGURE 1: Overall Comparison (The "Up" Curves) ---
figure('Name', 'Configuration Comparison', 'Position', [100, 100, 800, 500]);
hold on;
plot(voltage, no_glass_up, '-ob', 'LineWidth', 1.5, 'MarkerSize', 4, 'DisplayName', 'No Glass');
plot(voltage, glass_src_up1, '-oy', 'LineWidth', 1.5, 'MarkerSize', 4, 'DisplayName', 'Glass -> Source');
plot(voltage, foil_src_up, '-or', 'LineWidth', 1.5, 'MarkerSize', 4, 'DisplayName', 'Foil -> Source');

% Add calculation text
text(2, 114, sprintf('No Glass Change: %.2f%%', noglass_pct_change), 'FontSize', 10, 'Color', 'b');
text(6, 100, sprintf('Glass -> Source Change: %.2f%%', glass_pct_change), 'FontSize', 10, 'Color', '#D9A400'); % dark yellow
text(10, 94, sprintf('Foil -> Source Change: %.2f%%', foil_pct_change), 'FontSize', 10, 'Color', 'r');

title('Comparison of Optical Transmission (AC Up)');
xlabel('Voltage [V]');
ylabel('Illuminance [lx]');
legend('Location', 'Southeast');
grid on; grid minor;
subtitle('Ref: Source=148.3lx, Source Voltage=12.03V');
hold off;

% --- FIGURE 2: Full Cycle Hysteresis (Glass Facing Source) ---
figure('Name', 'Glass Facing Source Cycle', 'Position', [150, 150, 800, 500]);
hold on;
% 1. Initial Up
plot(voltage, glass_src_up1, '-^y', 'LineWidth', 1.2, 'MarkerSize', 4, 'DisplayName', '1. Up');
% 2. Down
plot(voltage, glass_src_down, '-v r', 'LineWidth', 1.2, 'MarkerSize', 4, 'DisplayName', '2. Down');
% 3. Up Again
plot(voltage, glass_src_up2, '--g', 'LineWidth', 1.5, 'DisplayName', '3. Up Again');

title('Hysteresis Loop: Glass Facing Source');
subtitle('Sequence: Up -> Down -> Up Again');
xlabel('Voltage [V]');
ylabel('Illuminance [lx]');
legend('Location', 'Southeast');
grid on; grid minor;
hold off;