%% Project CoPES: Open-Loop Thyristor Circuit Simulation & RMS Curve
% Models the schematic behavior and plots the theoretical RMS output curve.
clear; clc; close all;

%% ========================================================================
%  PART 1: TIME-DOMAIN SIMULATION (Specific Firing Angle)
%  ========================================================================

% --- 1. Circuit Parameters ---
V_supply_rms = 24;           % Supply Voltage [V]
F_grid       = 50;           % Grid Frequency [Hz]
R_load       = 24;           % Load Resistance [Ohm]
V_peak       = V_supply_rms * sqrt(2);
Period       = 1/F_grid;     % 20ms

% Simulation Settings
Fs    = 100000;              % Sampling Freq (100kHz)
T_sim = 0.1;                 % Simulate 5 full cycles (0.1s)
t     = 0:1/Fs:T_sim-1/Fs;   % Time vector

% --- 2. Control Input (User Setting) ---
Alpha_deg = 90;              % Constant Firing Angle for simulation
Alpha_rad = deg2rad(Alpha_deg);

% --- 3. Simulation Loop ---
v_ac        = V_peak * sin(2*pi*F_grid*t);
v_load      = zeros(size(t));
zcd_signal  = zeros(size(t)); 
gate_pulse  = zeros(size(t)); 
triac_latched = false;
last_zc_time  = -100;

fprintf('Simulating with Constant Firing Angle: %d degrees...\n', Alpha_deg);

for k = 2:length(t)
    % Block 1: Zero Crossing Detector
    if abs(v_ac(k)) < 1.0 
        zcd_signal(k) = 1; 
    else
        zcd_signal(k) = 0; 
    end
    
    if sign(v_ac(k)) ~= sign(v_ac(k-1))
        last_zc_time = t(k);
        triac_latched = false; 
    end
    
    % Block 2: MCU Timer Logic
    time_since_zc = t(k) - last_zc_time;
    required_delay = (Alpha_rad / (2*pi)) * Period;
    
    if (time_since_zc >= required_delay) && (time_since_zc < required_delay + 100e-6)
        gate_pulse(k) = 1; 
    end
    
    % Block 3: Triac Switching
    if gate_pulse(k) == 1
        triac_latched = true;
    end
    
    % Block 4: Power Output
    if triac_latched
        v_load(k) = v_ac(k);
    else
        v_load(k) = 0;      
    end
end

% --- 4. RMS Calculations for Simulated Angle ---
V_load_rms_sim = sqrt(mean(v_load.^2));
V_load_rms_theory = V_supply_rms * sqrt(1 - (Alpha_rad/pi) + sin(2*Alpha_rad)/(2*pi));

fprintf('--------------------------------------------------\n');
fprintf('Simulated Load RMS Voltage:   %.2f V\n', V_load_rms_sim);
fprintf('Theoretical Load RMS Voltage: %.2f V\n', V_load_rms_theory);
fprintf('--------------------------------------------------\n');

%% ========================================================================
%  PART 2: VISUALIZATION
%  ========================================================================

% ---------------------------------------------------------
% FIGURE 1: Time-Domain Waveforms
% ---------------------------------------------------------
figure('Color','white', 'Position', [100, 100, 800, 600], 'Name', 'Simulation Waveforms');

% Subplot 1: Mains & Load Voltage
subplot(3,1,1);
plot(t, v_ac, 'Color', [0.7 0.7 0.7], 'DisplayName', 'Mains (24V AC)'); hold on;
plot(t, v_load, 'b', 'LineWidth', 1.5, 'DisplayName', 'Load Voltage');
title(sprintf('Output Waveform (\\alpha = %d^\\circ) | Simulated RMS = %.2f V', Alpha_deg, V_load_rms_sim));
ylabel('Voltage [V]'); grid on; legend('Location','best');
ylim([-40 40]);

% Subplot 2: Zero Crossing Signal
subplot(3,1,2);
plot(t, zcd_signal, 'k', 'LineWidth', 1.5);
title('Zero Crossing Signal (Pin: ZERO\_CROSS)');
ylabel('Logic'); grid on; ylim([-0.2 1.2]);

% Subplot 3: Control/Gate Pulses
subplot(3,1,3);
plot(t, gate_pulse, 'r', 'LineWidth', 1.5);
title(['Control Pulses (Pin: CONTROL) - Delayed by ' num2str(Alpha_deg) '^\circ']);
ylabel('Logic'); xlabel('Time [s]');
grid on; ylim([-0.2 1.2]);


% ---------------------------------------------------------
% FIGURE 2: RMS Output vs. Firing Angle Sweep
% ---------------------------------------------------------
% Generate the data for 0 to 180 degrees
alpha_sweep_deg = 0:1:180;        
alpha_sweep_rad = deg2rad(alpha_sweep_deg); 

% Calculate Theoretical RMS for all angles
V_load_rms_sweep = V_supply_rms .* sqrt(1 - (alpha_sweep_rad ./ pi) + sin(2 .* alpha_sweep_rad) ./ (2 .* pi));

figure('Color', 'white', 'Position', [150, 150, 700, 500], 'Name', 'RMS Curve');
plot(alpha_sweep_deg, V_load_rms_sweep, 'b-', 'LineWidth', 2.5);
hold on;

% Highlight key operating points (0, 90, 180 degrees)
plot(0, 24, 'ko', 'MarkerFaceColor', 'g', 'MarkerSize', 8);
plot(90, V_supply_rms * sqrt(0.5), 'ko', 'MarkerFaceColor', 'y', 'MarkerSize', 8);
plot(180, 0, 'ko', 'MarkerFaceColor', 'r', 'MarkerSize', 8);

% Add text annotations
text(5, 23.5, 'Max Power (0^\circ)', 'VerticalAlignment', 'top');
text(95, 17.5, 'Half Power (90^\circ)', 'VerticalAlignment', 'bottom');
text(170, 1, 'Off (180^\circ)', 'HorizontalAlignment', 'right', 'VerticalAlignment', 'bottom');

% Format the plot
title('Load RMS Voltage vs. Firing Angle (\alpha)');
xlabel('Firing Angle \alpha [Degrees]');
ylabel('Load RMS Voltage [V]');
grid on;
xlim([0 180]);
ylim([0 26]);