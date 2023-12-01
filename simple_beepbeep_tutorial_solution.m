%% Step 0: Initialization

clear;

rate = 48000; % sampling rate

% A chirp signal of 1 second 
% with a freq range of [1, 18]kHz 
x = audioread('chirp.wav');

groundTruth = 25; % cm

% Load data received by two different devices
y = struct();
y(1).raw = audioread(...
    ['client.wav']);
y(2).raw = audioread(...
    ['beacon.wav']);
%% Step 1-1: Transfer function h(f) extraction (xcorr)

for i = 1:2
    y(i).h = xcorr(y(i).raw, x);

    subplot(2, 1, i)
    plot(y(i).h)
end
%% Step 1-2: EToA estimation (findpeaks)

for i = 1:2
    [~, pks] = findpeaks(abs(y(i).h), 'MinPeakHeight', 100, 'MinPeakDistance', rate * 1);
    pks
    
    if i == 1
        y(i).tSelf = pks(1) / rate;
        y(i).tOther = pks(2) / rate;
    else
        y(i).tOther = pks(1) / rate;
        y(i).tSelf = pks(2) / rate;        
    end
end
%% Step 2: Distance calculation

c = 34000; % cm/s
dAA = 3.5; % Spk-to-mic distance in devA
dBB = 3.5; % Spk-to-mic distance in devB

distance = c * (y(2).tOther - y(1).tSelf) + ...
    c * (y(1).tOther - y(2).tSelf) + ...
    (dAA + dBB);

distance = distance / 2;

disp(distance)
disp(abs(distance - groundTruth))