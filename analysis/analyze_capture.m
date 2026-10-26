function rep = analyze_capture(capture_file, fs, fin, W)
%ANALYZE_CAPTURE  Spectrum and weight calibration of a tb_top_sine capture.
%   rep = analyze_capture('build/runs/<run>/jobs/<corner>/capture.txt', 100e6, fin)
%   W (optional) = output weights; the default is conversion.out_weights of specs/arch.yaml v0.2.
%   capture.txt is written by tb_capture_va: "<index> <t_rdy> <t_conv> <D13..D0>".
%   Needs ADCToolbox (matlab/src on the path: addpath(genpath('<ADCToolbox>/matlab/src'))).

if nargin < 2, fs = 100e6; end
if nargin < 4 || isempty(W)
    W = [1960 1120 636 360 204 114 64 36 20 12 6 4 2 1];   % specs/arch.yaml v0.2
end

fid = fopen(capture_file, 'r');
c = textscan(fid, '%f %f %f %s', 'CommentStyle', '#');
fclose(fid);
str = char(c{4});
bits = double(str == '1');                 % N x 14, MSB first
n = 2^floor(log2(size(bits, 1)));
bits = bits(1:n, :);
codes = bits * W.';
if nargin < 3 || isempty(fin)
    fin = findfreq(codes, fs);
end

[rep.enob, rep.sndr, rep.sfdr, rep.snr, rep.thd] = plotspec(codes, 'Fs', fs, 'disp', true);
title(sprintf('nominal weights: ENOB %.2f, SFDR %.1f dB', rep.enob, rep.sfdr));

[w, ~, postcal] = wcalsin(bits, 'freq', fin / fs, 'order', 3);
rep.weights = w * (sum(W) / sum(w));   % scale to the nominal sum (the LSB estimate is noisy)
figure;
[rep.enob_cal, rep.sndr_cal, rep.sfdr_cal] = plotspec(postcal, 'Fs', fs, 'disp', true);
title(sprintf('calibrated weights: ENOB %.2f, SFDR %.1f dB', rep.enob_cal, rep.sfdr_cal));
rep.t_conv_max_ns = max(c{3}) * 1e9;
end
