import nidaqmx
from nidaqmx.constants import AcquisitionType, Edge , CountDirection
import nidaqmx.constants
import numpy as np
import matplotlib.pyplot as plt
from time import time

# Hardware constraints
MAX_SAWTOOTH_FREQ = 175    # Hz (5.714 ms/line minimum)
SETTLING_TIME = 300e-6     # 300 μs settling time
DAQ_RATE_LIMIT = 500e3     # USB-6431 max AO rate (2 μs minimum interval)

# Scan parameters
x_res = 256                # X pixels
y_res = 128                # Y pixels
voltage_range = [-1, 1]    # Galvo range

# Calculate timing (enforcing 175Hz line rate)
min_line_time = 1/MAX_SAWTOOTH_FREQ
active_scan_time = min_line_time - SETTLING_TIME
dwell_time = active_scan_time / x_res
sample_rate = min(DAQ_RATE_LIMIT, 1/dwell_time)  # Respect DAQ limit
actual_dwell = 1/sample_rate

print(f"Configured: {dwell_time*1e6:.1f} micros desired -> {actual_dwell*1e6:.1f}micros actual dwell")

# Generate scan pattern
x_voltages = np.linspace(voltage_range[0], voltage_range[1], x_res)
y_voltages = np.linspace(voltage_range[0], voltage_range[1], y_res)

# Waveform construction
settling_samples = int(SETTLING_TIME * sample_rate)
samples_per_line = x_res + settling_samples
total_samples = y_res * samples_per_line

x_wave = np.zeros(total_samples)
y_wave = np.zeros(total_samples)

for y_idx in range(y_res):
    line_start = y_idx * samples_per_line
    # Settling period (hold at start of line)
    x_wave[line_start:line_start+settling_samples] = x_voltages[0]
    y_wave[line_start:line_start+settling_samples] = y_voltages[y_idx]
    # Active scan
    x_wave[line_start+settling_samples:line_start+settling_samples+x_res] = x_voltages
    y_wave[line_start+settling_samples:line_start+settling_samples+x_res] = y_voltages[y_idx]

# Interleave AO data
ao_data = np.vstack((x_wave, y_wave)).T.ravel()

# DAQmx configuration
with nidaqmx.Task() as ao_task, nidaqmx.Task() as ci_task:
    # Analog Output
    ao_task.ao_channels.add_ao_voltage_chan("Dev1/ao0,Dev1/ao1")
    ao_task.timing.cfg_samp_clk_timing(
        rate=sample_rate,
        samps_per_chan=len(ao_data)//2,
        sample_mode=AcquisitionType.FINITE
    )
    
    # Counter Input
    ci_task.ci_channels.add_ci_count_edges_chan("Dev1/ctr0",edge=Edge.RISING,count_direction=CountDirection.COUNT_UP).ci_count_edges_term="/Dev1/PFI0"
    ci_task.timing.cfg_samp_clk_timing(
        rate=sample_rate,
        source=ao_task.timing.samp_clk_output_term,
        samps_per_chan=total_samples
    )
    
    # Synchronization
    ao_task.triggers.start_trigger.cfg_dig_edge_start_trig("/Dev1/PFI0")
    ci_task.triggers.start_trigger.cfg_dig_edge_start_trig(
        ao_task.triggers.start_trigger.term
    )
    
    # Hardware-timed execution
    print(f"Starting scan: {total_samples/sample_rate*1000:.1f}ms duration")
    t0 = time()
    ao_task.write(ao_data, auto_start=False)
    ao_task.start()
    ci_task.start()
    
    counts = ci_task.read(
        number_of_samples_per_channel=total_samples,
        timeout=2*total_samples/sample_rate + 1.0
    )
    t_elapsed = time() - t0
    print(f"Acquisition completed in {t_elapsed*1000:.1f}ms")

# Data processing
image = np.array(counts).reshape(y_res, samples_per_line)[:, settling_samples:settling_samples+x_res]

# Visualization
plt.figure(figsize=(10,5))
plt.imshow(image, cmap='hot', aspect='auto',
          extent=[voltage_range[0], voltage_range[1],
                 voltage_range[1], voltage_range[0]])
plt.colorbar(label='Photon Counts')
plt.title(f"175Hz Scan (300μs settling)\n{x_res}x{y_res} @ {actual_dwell*1e6:.1f}μs dwell")
plt.xlabel("X Galvo (V)")
plt.ylabel("Y Galvo (V)")
plt.tight_layout()
plt.show()