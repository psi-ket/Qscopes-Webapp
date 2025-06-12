import streamlit as st
import plotly.express as px
import numpy as np
import subprocess
import time
import os
from datetime import datetime
import wx

# --- Function to browse for an output directory using wxPython ---
def browse_for_output_dir():
    # Create a wx App (if one is not running)
    app = wx.App(False)
    dialog = wx.DirDialog(None, "Select Output Directory:", style=wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
    folder_path = ""
    if dialog.ShowModal() == wx.ID_OK:
        folder_path = dialog.GetPath()  # Returns the selected folder as a string
    dialog.Destroy()
    return folder_path

# --- Data Loading Function ---
def load_data_in_2x50_chunks(filename, step):
    with open(filename, 'r') as f:
        # Read non-empty lines and filter out any that equal the unwanted text.
        lines = [line.strip() for line in f if line.strip() and line.strip() != "2D Voltage Scan Completed."]
    
    # Process each line: remove the dummy token ("0.000000" or ".000000") at the start.
    data_lines = []
    for line in lines:
        tokens = line.split()
        if tokens and tokens[0] in ["0.000000", ".000000"]:
            tokens = tokens[1:]
        if not tokens:
            continue  # Skip if nothing remains
        try:
            floats = [float(x) for x in tokens]
        except ValueError as e:
            raise ValueError(f"Could not convert line '{line}' to floats: {e}")
        data_lines.append(floats)
    
    if not data_lines:
        raise ValueError("No valid data lines found in file.")
    
    # Ensure that all valid data lines have the same number of floats.
    nums_per_line = len(data_lines[0])
    for dl in data_lines:
        if len(dl) != nums_per_line:
            raise ValueError("Inconsistent number of floats per data line.")
    
    # Determine how many lines combine to form one output row.
    if step % nums_per_line != 0:
        raise ValueError("The step value must be an integer multiple of the number of floats per data line (after dummy removal).")
    lines_per_chunk = step // nums_per_line
    
    expected_lines = step * lines_per_chunk
    if len(data_lines) < expected_lines:
        raise ValueError(f"Expected at least {expected_lines} data lines, but got {len(data_lines)}.")
    
    # Build the final array by grouping the valid lines.
    data_rows = []
    for i in range(step):
        start = i * lines_per_chunk
        end = start + lines_per_chunk
        row_values = []
        for dl in data_lines[start:end]:
            row_values.extend(dl)
        if len(row_values) != step:
            raise ValueError("Chunk does not contain the expected number of floats.")
        data_rows.append(row_values)
    
    data_array = np.array(data_rows, dtype=float)
    print("Data Array Shape:", data_array.shape)
    print(data_array)
    return data_array

# --- Plotting Function ---
def plot_heatmap_interactive(data_array):
    """
    Creates an interactive heatmap using Plotly Express from a 2D NumPy array.
    """
    fig = px.imshow(
        data_array,
        color_continuous_scale='hot'
    )
    fig.update_xaxes(title_text="X Index")
    fig.update_yaxes(title_text="Y Index")
    fig.update_layout(
        autosize=True,
        width=1000,
        height=800
    )
    return fig

# --- Streamlit UI Setup ---
st.set_page_config(layout="wide")

# Adjust column widths: left column (controls) gets 1:3 ratio with right column (visualization)
col_left, col_right = st.columns([1, 3])

with col_left:
    st.header("Scan Controls")
    
    # --- Scan Mode Selector ---
    scan_mode = st.radio("Scan Mode", ["Basic", "Advanced"])
    
    if scan_mode == "Basic":
        # In Basic mode, use a single Scan Area input and X/Y offset inputs.
        basic_scan_area = st.number_input("Scan Area", value=1.0, format="%.1f", key="basic_scan_area")
        basic_x_offset = st.number_input("X Offset", value=0.0, format="%.1f", key="basic_x_offset")
        basic_y_offset = st.number_input("Y Offset", value=0.0, format="%.1f", key="basic_y_offset")
        
        # Compute boundaries automatically:
        xs = basic_x_offset + basic_scan_area
        ys = basic_y_offset + basic_scan_area
        xe = basic_x_offset - basic_scan_area
        ye = basic_y_offset - basic_scan_area
    else:
        # In Advanced mode, allow manual entry.
        xs = st.number_input("X start", value=1.0, format="%.2f", key="adv_xs")
        ys = st.number_input("Y start", value=1.0, format="%.2f", key="adv_ys")
        xe = st.number_input("X end", value=-1.0, format="%.2f", key="adv_xe")
        ye = st.number_input("Y end", value=-1.0, format="%.2f", key="adv_ye")
    
    # Other scan parameters
    step_val = st.number_input("Step (No. of Pixel)", value=100, step=1,help="Step size for the scan. Must be an integer multiple of the number of floats per data line.")
    dw = st.number_input("Dwell/P", value=1.0, step=0.5,help="Integration time per pixel")
    
    # --- Output Settings ---
    st.subheader("Output Settings")
    output_dir = st.text_input("Output Directory", value="data", 
                               help="Folder where scan data will be saved. (Relative or absolute path)")
    
    # Button to browse for an output directory using wxPython.
    if st.button("Browse Output Directory"):
        selected_folder = browse_for_output_dir()
        if selected_folder:
            st.session_state['output_dir'] = selected_folder
            st.success(f"Selected folder: {selected_folder}")
        else:
            st.warning("No folder selected.")
    
    # Update output directory from session state if available.
    if 'output_dir' in st.session_state:
        output_dir = st.session_state['output_dir']
    
    filename_prefix = st.text_input("Filename Prefix", value="scan", 
                                    help="Prefix for the saved scan file name. For example, 'measurement1'.")
    
    # --- Scan Button with Autosave and Progress Bar ---
    if st.button("Scan"):
        # Build command-line arguments for the scan executable.
        args = [
            "-xs", str(xs),
            "-ys", str(ys),
            "-xe", str(xe),
            "-ye", str(ye),
            "-st", str(step_val),
            "-dw", str(dw)
        ]
        exe_path = r"scanwitharg.exe"
        full_command = [exe_path] + args
        
        # Launch the scan process using Popen so we can monitor progress.
        process = subprocess.Popen(full_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # Create progress bar and text placeholder.
        progress_bar = st.progress(0)
        progress_text = st.empty()
        
        expected_lines = None  # Will be computed once the file has at least one valid line.
        # Continuously check the output file while the process is running.
        while process.poll() is None:
            try:
                with open("lua_output.txt", "r") as f:
                    file_content = f.readlines()
            except Exception:
                file_content = []
            # Filter out blank lines and lines matching the unwanted text.
            file_lines = [line.strip() for line in file_content if line.strip() and line.strip() != "2D Voltage Scan Completed."]
            
            # Compute expected_lines using the first valid line (if available).
            if file_lines and expected_lines is None:
                tokens = file_lines[0].split()
                if tokens and tokens[0] in ["0.000000", ".000000"]:
                    tokens = tokens[1:]
                nums_per_line = len(tokens)
                if step_val % nums_per_line != 0:
                    st.error("The step value must be an integer multiple of the number of floats per data line.")
                    break
                lines_per_chunk = step_val // nums_per_line
                expected_lines = step_val * lines_per_chunk
            
            # Update progress only if expected_lines is determined.
            if expected_lines:
                current_lines = len(file_lines)
                progress = min(current_lines / expected_lines, 1.0)
                progress_bar.progress(progress)
                progress_text.text(f"Scanning progress: {current_lines}/{expected_lines} lines")
            time.sleep(0.2) # Sleep to avoid busy waiting.
        
        # Final update after process completes.
        progress_bar.progress(1.0)
        progress_text.text("Scanning completed.")
        stdout, stderr = process.communicate()  # Get remaining output if needed.
        
        # Attempt to load the scan data.
        try:
            data = load_data_in_2x50_chunks("lua_output.txt", step_val)
            st.session_state['heatmap_data'] = data
            st.success("Data loaded successfully.")
            
            # Autosave the data immediately after a successful scan.
            if not os.path.isabs(output_dir):
                output_dir = os.path.join(os.getcwd(), output_dir)
            os.makedirs(output_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_xs-{xs}_ys-{ys}_xe-{xe}_ye-{ye}_step-{step_val}_dw-{dw}_{timestamp}.txt"
            save_path = os.path.join(output_dir, filename)
            np.savetxt(save_path, data, fmt="%.6f")
            st.success(f"Data autosaved successfully to {save_path}")
            
        except Exception as e:
            st.error(f"Error during scan or autosave: {e}")

with col_right:
    st.header("Camera & Visualization")
    st.subheader("Interactive Heatmap Plot")
    if 'heatmap_data' in st.session_state:
        try:
            data = st.session_state['heatmap_data']
            fig = plot_heatmap_interactive(data)
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Error creating heatmap: {e}")
    else:
        st.info("Run a scan to display the heatmap.")
