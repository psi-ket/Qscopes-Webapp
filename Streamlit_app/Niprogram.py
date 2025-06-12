import nidaqmx
import numpy as np
import time

# --- PARAMETERS ---
x_points = 50                # Number of points in X
y_points = 50                # Number of points in Y
dwell_time = 0.001           # 1 ms
x_min, x_max = -1.0, 1.0      # Voltage range for X
y_min, y_max = -1.0, 1.0      # Voltage range for Y

# Channels (update these for your device)
ao_x = "Dev1/ao0"
ao_y = "Dev1/ao1"
counter_channel = "Dev1/ctr0"

# --- PREPARE RASTER GRID ---
x_values = np.linspace(x_min, x_max, x_points)
y_values = np.linspace(y_min, y_max, y_points)
counts = np.zeros((y_points, x_points))

# --- MAIN ACQUISITION LOOP ---
with nidaqmx.Task() as ao_task, nidaqmx.Task() as ctr_task:
    # Configure AO channels for X and Y
    ao_task.ao_channels.add_ao_voltage_chan(ao_x)
    ao_task.ao_channels.add_ao_voltage_chan(ao_y)
    # Configure counter for edge counting
    ctr_task.ci_channels.add_ci_count_edges_chan(counter_channel)
    
    for iy, y in enumerate(y_values):
        for ix, x in enumerate(x_values):
            # Move to new X,Y point
            ao_task.write([x, y])
            # Read initial count
            c0 = ctr_task.read()
            # Dwell
            time.sleep(dwell_time)
            # Read count after dwell
            c1 = ctr_task.read()
            # Calculate number of pulses counted in this interval
            counts[iy, ix] = c1 - c0
            # print(f"Point ({ix},{iy}) - X={x:.2f} V, Y={y:.2f} V | Counts: {counts[iy, ix]}")
    
print("Raster scan complete.")
