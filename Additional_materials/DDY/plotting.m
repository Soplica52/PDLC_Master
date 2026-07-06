clear; clc; close all;

% --- 1. Define File List and Display Names ---
% Make sure these filenames match exactly what is in your folder
fileList = { ...
    'Spectral_Data_Table_no_foil.rtf',              'No Foil (Baseline)'; ...
    'Spectral_Data_Table_foil_power_off.rtf',       'Foil (Power Off)'; ...
    'Spectral_Data_Table_foil_glass_power_off.rtf', 'Foil + Glass (Power Off)'; ...
    'Spectral_Data_Table_foil_glass_power_on.rtf',  'Foil + Glass (Power On)'; ...
    'Spectral_Data_Table_foil_power_on.rtf',        'Foil (Power On)'; ...
    'FGPO_4V.rtf',                                  'FGPO 4V' ...
};

% Data Storage
allData = containers.Map;
commonWavelengths = []; 

% Generate colors for consistent plotting
colors = lines(size(fileList, 1)); 

fprintf('Processing Spectral Files...\n');

% --- 2. Robust Parsing Loop ---
for i = 1:size(fileList, 1)
    fileName = fileList{i, 1};
    displayName = fileList{i, 2};
    
    try
        fid = fopen(fileName, 'r');
        if fid == -1
            warning('File not found: %s', fileName);
            continue;
        end
        
        % Read file content
        rawText = fread(fid, '*char')';
        fclose(fid);
        
        % Split into lines
        fileLines = regexp(rawText, '\r\n|\n|\r', 'split');
        
        w_all = [];
        v_all = [];
        
        % Loop through lines to find data wrapped in pipes "|"
        for k = 1:length(fileLines)
            line = fileLines{k};
            
            if contains(line, '|')
                % Replace European decimal comma with dot
                line = strrep(line, ',', '.');
                
                % Split by pipe
                parts = strsplit(line, '|');
                
                % --- RTF CLEANUP FIX ---
                % 1. Replace hidden RTF formatting tags and braces with spaces
                cleanParts = regexprep(parts, '\\[a-zA-Z]+-?\d*\s?|[{}]', ' ');
                
                % 2. Extract the actual numeric values, ignoring remaining text
                numMatches = regexp(cleanParts, '[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', 'match', 'once');
                
                % 3. Convert the cleaned strings to doubles
                nums = str2double(numMatches);
                % -----------------------
                
                % Remove NaNs (caused by empty strings, headers, or text-only blocks)
                nums(isnan(nums)) = [];
                
                % Store pairs (Wave, Value)
                if ~isempty(nums) && mod(length(nums), 2) == 0
                    w_chunk = nums(1:2:end)';
                    v_chunk = nums(2:2:end)';
                    
                    w_all = [w_all; w_chunk];
                    v_all = [v_all; v_chunk];
                end
            end
        end
        
        % Sort and Unique (to handle the data wrapping)
        if ~isempty(w_all)
            [w_sorted, sortIdx] = sort(w_all);
            v_sorted = v_all(sortIdx);
            
            % Averaging duplicates if any exist, or just taking unique
            [w_unique, uniqueIdx] = unique(w_sorted);
            v_unique = v_sorted(uniqueIdx);
            
            D.w = w_unique;
            D.v = v_unique;
            allData(displayName) = D;
            
            % Set common grid for difference calculation
            if isempty(commonWavelengths)
                commonWavelengths = w_unique;
            end
            fprintf('  Loaded: %s (%d points)\n', displayName, length(w_unique));
        else
            warning('  No spectral data found in %s. Verify the file contains "|" characters.', fileName);
        end
        
    catch ME
        warning('  Error reading %s: %s', fileName, ME.message);
    end
end

% --- 3. Generate 6 Separate Graphs ---
keys = fileList(:, 2);
for i = 1:length(keys)
    name = keys{i};
    if isKey(allData, name)
        D = allData(name);
        
        figure('Name', name, 'Color', 'w');
        plot(D.w, D.v, 'LineWidth', 2, 'Color', colors(i, :));
        title(['Spectrum: ' name]);
        xlabel('Wavelength (nm)');
        ylabel('Intensity (a.u.)');
        grid on;
        axis tight;
    end
end

% --- 4. Comparison Graph (All on one) ---
figure('Name', 'All Spectra Comparison', 'Color', 'w');
hold on;
plotHandles = [];
legendEntries = {};

for i = 1:length(keys)
    name = keys{i};
    if isKey(allData, name)
        D = allData(name);
        p = plot(D.w, D.v, 'LineWidth', 1.5, 'Color', colors(i, :));
        plotHandles(end+1) = p;
        legendEntries{end+1} = name;
    end
end

title('Comparison of All Spectral Measurements');
xlabel('Wavelength (nm)');
ylabel('Intensity (a.u.)');
legend(plotHandles, legendEntries, 'Location', 'Best');
grid on;
axis tight;
hold off;

% --- 5. Difference Graph (Relative to Baseline) ---
baselineName = 'No Foil (Baseline)';
if isKey(allData, baselineName)
    baseD = allData(baselineName);
    
    figure('Name', 'Spectral Differences', 'Color', 'w');
    hold on;
    diffHandles = [];
    diffEntries = {};
    
    for i = 1:length(keys)
        name = keys{i};
        if strcmp(name, baselineName), continue; end
        
        if isKey(allData, name)
            D = allData(name);
            
            % Interpolate to ensure wavelengths match exactly for subtraction
            v_interp = interp1(D.w, D.v, baseD.w, 'linear', NaN);
            
            % Calculate Difference
            diffVal = v_interp - baseD.v;
            
            p = plot(baseD.w, diffVal, 'LineWidth', 1.5, 'Color', colors(i, :));
            diffHandles(end+1) = p;
            diffEntries{end+1} = [name ' - Baseline'];
        end
    end
    
    yline(0, '--k', 'Zero Difference');
    title(['Spectral Differences (Relative to ' baselineName ')']);
    xlabel('Wavelength (nm)');
    ylabel('Delta Intensity');
    legend(diffHandles, diffEntries, 'Location', 'Best');
    grid on;
    axis tight;
    hold off;
else
    disp('Baseline file not found, skipping difference plot.');
end