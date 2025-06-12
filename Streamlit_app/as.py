import numpy as np
import matplotlib.pyplot as plt
fs = 1_000_000  # 1 MSa/s for smooth plotting
duration = 0.001  # 1 ms view window (enough for 10 cycles of 10 kHz)

# 1. Sinewave resolution/quantization steps
bits_list = [13, 14, 16, 20]
f_sine = 10000  # 10 kHz
t = np.linspace(0, duration, int(fs * duration), endpoint=False)
# Let's plot 6, 8, 10, and 12 bits for maximum step visibility
low_bits_list = [6, 8, 10, 12]
wide_start = 0.00
wide_end = 0.2  # ms, two full cycles
start_idx = int(wide_start * 1e-3 * fs)
end_idx = int(wide_end * 1e-3 * fs)
t_wide = t[start_idx:end_idx]
sine_ideal_wide = np.sin(2 * np.pi * f_sine * t_wide)

plt.figure(figsize=(12, 6))
plt.plot(t_wide * 1e3, sine_ideal_wide, 'k--', label="Ideal Sine", linewidth=2)
for bits in low_bits_list:
    levels = 2 ** bits
    sine_quant = np.round((sine_ideal_wide + 1) / 2 * (levels - 1)) / (levels - 1) * 2 - 1
    plt.plot(t_wide * 1e3, sine_quant, drawstyle='steps-post', label=f"{bits} bits ({levels} steps)")
plt.title("10 kHz Sinewave: Visible Steps for Low Bit Depths")
plt.xlabel("Time (ms)")
plt.ylabel("Amplitude")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()

