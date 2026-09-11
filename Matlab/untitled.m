% =========================================================================
% STM32 Smart Window - Separate Performance Analytics for 3 Files
% =========================================================================
clear; clc; close all;

% -------------------------------------------------------------------------
% 1. PUT YOUR 3 FILE NAMES HERE
% -------------------------------------------------------------------------
files = {
    'stm32_log_20260522_124508.csv', % File 1
    'stm32_log_20260522_144739.csv', % File 2
    'stm32_log_20260522_154040.csv'  % File 3
};

fprintf('==================================================\n');
fprintf('  STM32 CONTROL SYSTEM PERFORMANCE REPORT\n');
fprintf('==================================================\n\n');

% Loop through each file one by one
for i = 1:length(files)
    current_file = files{i};
    
    % Check if file exists to prevent crashing
    if ~isfile(current_file)
        fprintf('WARNING: File %d (%s) not found. Skipping...\n\n', i, current_file);
        continue;
    end
    
    % ---------------------------------------------------------------------
    % 2. LOAD & PROCESS DATA
    % ---------------------------------------------------------------------
    data = readtable(current_file);
    
    % Create Time Axis in Minutes (Assuming 200ms / 5Hz loop time)
    time_mins = ((0:(height(data)-1))' * 0.2) / 60; 
    
    target = data.Target;
    lux = data.Lux;
    error = lux - target; % Positive = Too bright (Overshoot)
    
    % --- Calculate Performance Metrics ---
    total_time  = max(time_mins);
    mae         = mean(abs(error));
    max_over    = max(error);
    max_under   = min(error);
    
    % Steady-State Error (Looking at the last 15% of the data)
    ss_index    = floor(height(data) * 0.85);
    ss_error    = mean(abs(error(ss_index:end)));
    
    % Actuator Usage
    avg_effort  = mean(data.Effort);
    max_effort  = max(data.Effort);
    max_foil    = max(data.Foil_V);
    max_led     = max(data.LED_Pct);
    
    % ---------------------------------------------------------------------
    % 3. PRINT REPORT TO COMMAND WINDOW
    % ---------------------------------------------------------------------
    fprintf('▶ FILE %d: %s\n', i, current_file);
    fprintf('   Duration:             %.2f Minutes\n', total_time);
    fprintf('   Target Lux:           %.0f Lux\n', target(1));
    fprintf('   Mean Absolute Error:  %.2f Lux\n', mae);
    fprintf('   Max Overshoot:        +%.0f Lux\n', max_over);
    fprintf('   Steady-State Error:   ±%.2f Lux (Last 15%% of run)\n', ss_error);
    fprintf('   -- Actuators --\n');
    fprintf('   Max Controller Effort: %.1f / 200\n', max_effort);
    fprintf('   Max Foil Voltage:      %.1f V\n', max_foil);
    fprintf('   Max LED Brightness:    %.1f %%\n', max_led);
    fprintf('--------------------------------------------------\n\n');
    
    % ---------------------------------------------------------------------
    % 4. GENERATE INDIVIDUAL GRAPH
    % ---------------------------------------------------------------------
    fig = figure('Name', sprintf('Run %d Analysis: %s', i, current_file), 'Color', 'w');
    fig.Position = [50 + (i*50), 50 + (i*50), 900, 700]; % Staggers the windows
    
    % -- Top Plot: Controller Tracking --
    ax1 = subplot(2, 1, 1);
    plot(time_mins, lux, 'Color', '#D95319', 'LineWidth', 1.5); hold on;
    plot(time_mins, target, 'Color', '#0072BD', 'LineStyle', '--', 'LineWidth', 2);
    
    title(sprintf('Run %d: PI Controller Tracking Performance', i));
    ylabel('Illuminance (lx)');
    xlabel('Elapsed Time (Minutes)'); % <--- ADDED: X-axis label for the top graph
    legend('Actual lx (Sensor)', 'Target lx', 'Location', 'best');
    grid on;
    
    % -- Bottom Plot: Hardware Actuation --
    ax2 = subplot(2, 1, 2);
    
    yyaxis left;
    plot(time_mins, data.Effort, 'k', 'LineWidth', 1.5);
    ylabel('Master PI Effort (0-200 %)');
    ylim([0 210]);
    
    yyaxis right;
    if i == 3
        foil_scaled = data.Foil_V * 10; % Rescale 0-10V to 0-100% for visual comparison
        plot(time_mins, foil_scaled, 'm', 'LineWidth', 1.5); hold on;
        plot(time_mins, data.LED_Pct, 'r', 'LineWidth', 1.5);
        ylabel('Actuator Effort (%)');
        legend_foil_label = 'PDLC Foil (%)';
    else
        plot(time_mins, data.Foil_V, 'm', 'LineWidth', 1.5); hold on;
        plot(time_mins, data.LED_Pct, 'r', 'LineWidth', 1.5);
        ylabel('Actuator Effort (%)');
        legend_foil_label = 'PDLC Foil (%)';
    end
    ylim([0 110]);
    
    title('Actuator Response (Effort vs Hardware)');
    xlabel('Elapsed Time (Minutes)');
    legend('PI Effort (%)', legend_foil_label, 'LED Output (%)', 'Location', 'best');
    grid on;
    
    % Link X-axes for zooming
    linkaxes([ax1, ax2], 'x');
end

disp('All analyses generated successfully!');