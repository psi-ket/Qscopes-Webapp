import numpy as np
import matplotlib.pyplot as plt

def generate_2d_scan_waveforms(dwell_time, amplitude_x, amplitude_y, steps_x, steps_y):
    """
    Generate full 2D scanning waveforms for X (sawtooth) and Y (step) axes.

    Parameters:
    - dwell_time: time per pixel (seconds)
    - amplitude_x: max amplitude for X axis
    - amplitude_y: max amplitude for Y axis
    - steps_x: number of pixels per line (horizontal)
    - steps_y: number of lines (vertical)

    Returns:
    - t: time array (seconds)
    - x_waveform: full X axis waveform values (sawtooth repeated per line)
    - y_waveform: full Y axis waveform values (step increment per line)
    """

    total_pixels = steps_x * steps_y
    total_time = total_pixels * dwell_time

    # Time vector for each pixel sample
    t = np.linspace(0, total_time, total_pixels, endpoint=False)

    # X waveform: sawtooth for each line, repeated steps_y times
    x_waveform = np.tile(np.linspace(0, amplitude_x, steps_x, endpoint=False), steps_y)

    # Y waveform: stair-step, increments every line (steps_x pixels)
    y_steps = np.linspace(0, amplitude_y, steps_y, endpoint=False)
    y_waveform = np.repeat(y_steps, steps_x)

    return t, x_waveform, y_waveform

# Parameters
dwell_time = 7.63e-6  # seconds per pixel
amplitude_x = 5.0     # amplitude units for X axis
amplitude_y = 5.0     # amplitude units for Y axis
steps_x = 512         # pixels per line
steps_y = 512         # lines per frame

# Generate waveforms
t, x_waveform, y_waveform = generate_2d_scan_waveforms(dwell_time, amplitude_x, amplitude_y, steps_x, steps_y)

# Plot full X axis waveform
plt.figure(figsize=(12, 4))
plt.plot(t * 1e3, x_waveform)
plt.title("Full X Axis Sawtooth Waveform (Full Frame)")
plt.xlabel("Time (milliseconds)")
plt.ylabel("X Amplitude")
plt.grid(True)
plt.tight_layout()
plt.show()

# Plot full Y axis waveform (line increments)
plt.figure(figsize=(12, 4))
plt.plot(t[::steps_x] * 1e3, y_waveform[::steps_x], marker='o')
plt.title("Full Y Axis Stair-Step Waveform (Line increments)")
plt.xlabel("Time (milliseconds)")
plt.ylabel("Y Amplitude")
plt.grid(True)
plt.tight_layout()
plt.show()
