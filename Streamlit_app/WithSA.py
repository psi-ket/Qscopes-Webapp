import streamlit as st
import plotly.express as px
import numpy as np
import subprocess
import time
import os
from datetime import datetime,timedelta
import wx
import re
import pandas as pd
from PIL import Image


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

# --- Function to load scan data from file ---
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

# --- Function to create an interactive heatmap using Plotly Express ---
def plot_heatmap_interactive(data_array, vmin=None, vmax=None, cmap="hot"):
    fig = px.imshow(
        data_array,
        color_continuous_scale=cmap,
        zmin=vmin,
        zmax=vmax,
        aspect="equal"
    )
    fig.update_xaxes(title_text="X Index")
    fig.update_yaxes(title_text="Y Index")
    fig.update_layout(
        autosize=True,
        width=800,
        height=800
    )
    return fig

# --- Function to parse file metadata from filename ---
def parse_filename(filename):
    """
    Expects filenames in the format:
    {prefix}_xs-{xs}_ys-{ys}_xe-{xe}_ye-{ye}_step-{step}_dw-{dw}_{timestamp}.txt
    Example: measurement1_xs-1.0_ys-1.0_xe--1.0_ye--1.0_step-100_dw-1.0_20230414_110203.txt
    """
    pattern = (r"^(.*?)_xs-([-+]?[0-9]*\.?[0-9]+)_ys-([-+]?[0-9]*\.?[0-9]+)_xe-([-+]?[0-9]*\.?[0-9]+)_"
               r"ye-([-+]?[0-9]*\.?[0-9]+)_step-([0-9]+)_dw-([-+]?[0-9]*\.?[0-9]+)_"
               r"([0-9]{8}_[0-9]{6})\.txt$")
    match = re.match(pattern, filename)
    if match:
        try:
            timestamp = datetime.strptime(match.group(8), "%Y%m%d_%H%M%S")
        except Exception:
            timestamp = None
        return {
            "prefix": match.group(1),
            "xs": float(match.group(2)),
            "ys": float(match.group(3)),
            "xe": float(match.group(4)),
            "ye": float(match.group(5)),
            "step": int(match.group(6)),
            "dw": float(match.group(7)),
            "timestamp": timestamp,
            "filename": filename
        }
    else:
        return None

# --- Set up the Streamlit app configuration ---
st.set_page_config(layout="wide", page_title="Qscope App",page_icon="qscopes.png")
st.logo("New.png")
# --- Initialize scanning flag if not already present ---
if "scanning" not in st.session_state:
    st.session_state["scanning"] = False
scanning = st.session_state["scanning"]

# --- Sidebar Navigation --- 
page = st.sidebar.selectbox("Select Page", ["Scan", "Analysis", "Single plot"])

# ============================
#    Scan Page
# ============================
if page == "Scan":
    st.title("Scan Page")
    
    # Split layout into two columns: left (controls) and right (visualization)
    col_left, col_mid ,col_right = st.columns([1, 4 ,1])
    
    with col_left:
        st.subheader("Scan Controls")
        # --- Scan Mode Selector ---

        scan_mode = st.radio("Scan Mode", ["Basic", "Advanced"], horizontal=True, disabled=scanning)
        if scan_mode == "Basic":
            basic_scan_area = st.number_input("Scan Area", value=1.0, step=0.01 ,key="basic_scan_area", disabled=scanning)
            l_ctrl,r_ctrl = st.columns([1,1])
            with l_ctrl:    
                basic_x_offset = st.number_input("X Offset", value=0.0, format="%.1f", key="basic_x_offset", disabled=scanning)
            with r_ctrl:    
                basic_y_offset = st.number_input("Y Offset", value=0.0, format="%.1f", key="basic_y_offset", disabled=scanning)
            xs = basic_x_offset + basic_scan_area
            ys = basic_y_offset + basic_scan_area
            xe = basic_x_offset - basic_scan_area
            ye = basic_y_offset - basic_scan_area
        else:
            l_ctrl,r_ctrl = st.columns([1,1])
            with l_ctrl:  
                xs = st.number_input("X start", value=1.0, format="%.2f", key="adv_xs", disabled=scanning)
            with r_ctrl:  
                ys = st.number_input("Y start", value=1.0, format="%.2f", key="adv_ys", disabled=scanning)
            with l_ctrl:  
                xe = st.number_input("X end", value=-1.0, format="%.2f", key="adv_xe", disabled=scanning)
            with r_ctrl:  
                ye = st.number_input("Y end", value=-1.0, format="%.2f", key="adv_ye", disabled=scanning)
        
        # Other scan parameters
        l_ctrl,r_ctrl = st.columns([1,1],vertical_alignment="bottom")
        with l_ctrl:
            step_val = st.number_input("Step (No. of Pixel)", value=100, step=25, min_value=25,
                                     help="Step size for the scan. Must be an integer multiple of the number of floats per data line.",
                                     disabled=scanning)
        with r_ctrl:
            dw = st.number_input("Dwell/P", value=1.0, step=0.5,min_value=1.0 ,help="Integration time per pixel", disabled=scanning)
        dw_seconds = dw/1000
        total_seconds = (step_val**2) * dw_seconds * 1.65
        estimated_time = timedelta(seconds=total_seconds)
        st.markdown(f"**Estimated Scan Time:** {str(estimated_time)}")
        # --- Output Settings ---
        st.markdown(f"**Output Settings**")
        l_ctrl,r_ctrl = st.columns([1,1],vertical_alignment="bottom")
        with l_ctrl:
            output_dir = st.text_input("Output Directory", value="data", 
                                   help="Folder where scan data will be saved. (Relative or absolute path)",
                                   disabled=scanning)
        with r_ctrl:
            if st.button("Browse", disabled=scanning):
                selected_folder = browse_for_output_dir()
                if selected_folder:
                    st.session_state['output_dir'] = selected_folder
                    st.success(f"Selected folder: {selected_folder}")
                else:
                    st.warning("No folder selected.")
        if 'output_dir' in st.session_state:
            output_dir = st.session_state['output_dir']
        filename_prefix = st.text_input("Filename Prefix", value="scan", 
                                        help="Prefix for the saved scan file name. For example, 'measurement1'.",
                                        disabled=scanning)
        
        # --- Scan Button with Autosave and Progress Bar ---
        if st.button("Scan", disabled=scanning):
            # Mark scanning as in progress
            st.session_state["scanning"] = True
            scanning = True  # update local variable
            time.sleep(0.1)  # Small delay to ensure the UI updates before starting the scan
            # Build command-line arguments for the scan executable.
            args = [
                "-xs", str(xs),
                "-ys", str(ys),
                "-xe", str(xe),
                "-ye", str(ye),
                "-st", str(step_val),
                "-dw", str(dw)
            ]
            # Adjust the path to your executable as needed
            exe_path = r"scanwithargt7.exe"
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
                time.sleep(0.2)
            
            # Final update after process completes.
            progress_bar.progress(1.0)
            progress_text.text("Scanning completed.")
            stdout, stderr = process.communicate()  # Get any remaining output.
            
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
            
            # Mark scanning as completed and update the UI.
            st.session_state["scanning"] = False
            scanning = False
            st.rerun()
    
    with col_right:
        st.subheader("Transforms & Settings")
        if 'heatmap_data' in st.session_state:
            orig = st.session_state['heatmap_data']
            st.session_state["active_scan"] = orig.copy()
                
            spacer_left, btn_col, spacer_right = st.columns([1, 2, 1])
            with btn_col:
                if st.button("Flip H",use_container_width=True):
                    st.session_state["active_scan"] = np.fliplr(st.session_state["active_scan"])
                if st.button("Flip V",use_container_width=True):
                    st.session_state["active_scan"] = np.flipud(st.session_state["active_scan"])
                if st.button("↻ Rotate CW",use_container_width=True):
                    st.session_state["active_scan"] = np.rot90(st.session_state["active_scan"], k=-1)
                if st.button("↺ Rotate CCW",use_container_width=True):
                    st.session_state["active_scan"] = np.rot90(st.session_state["active_scan"], k=1)
                if st.button("Reset Orientation",use_container_width=True):
                    st.session_state["active_scan"] = orig.copy()
            plot_data = st.session_state["active_scan"]
            dmin, dmax = float(plot_data.min()), float(plot_data.max())
            vmin, vmax = st.slider(
                "Intensity range",
                dmin, dmax,
                (dmin, dmax),
                step=(dmax - dmin) / 100,
                key="scan_intensity"
            )
            
            # Color‐map selector
            color_scales = [
                "hot", "viridis", "plasma", "magma",
                "cividis", "inferno", "ice", "temps",
                "Turbo" , "greys","Gray" # etc, pick any from https://plotly.com/python/builtin-colorscales/
            ]
            cmap = st.selectbox("Color Scheme", color_scales, index=color_scales.index("Gray"), key="scan_cmap")
        else:
            st.info("Run a scan to display transforms & settings.")
            # set defaults so col_mid won't error
            vmin = vmax = None
            cmap = "hot"
        if st.button("Save as TIFF"):
            try:
                # 1) reload raw scan data
                data_array = load_data_in_2x50_chunks("lua_output.txt", step_val)

                # 2) normalize to 0–255
                arr = data_array.astype(np.float32)
                arr -= arr.min()
                if arr.max() != 0:
                    arr /= arr.max()
                arr8 = (arr * 255).astype(np.uint8)

                # 3) build PIL image
                img = Image.fromarray(arr8, mode="L")

                # 4) ensure output_dir exists
                out_dir = st.session_state.get("output_dir", "data")
                os.makedirs(out_dir, exist_ok=True)

                # 5) save with timestamped name
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"{filename_prefix}_raw_heatmap_{ts}.tiff"
                path = os.path.join(out_dir, name)
                img.save(path, format="TIFF")

                st.success(f"Saved TIFF to {path}")

                # 6) provide download link
                with open(path, "rb") as f:
                    st.download_button(
                        label="Download Raw TIFF",
                        data=f,
                        file_name=name,
                        mime="image/tiff"
                    )
            except Exception as e:
                st.error(f"Failed to save TIFF: {e}")
    
    # --- MIDDLE: Interactive Heatmap using chosen cmap ---
    with col_mid:
        st.subheader("Interactive Heatmap")
        if 'heatmap_data' in st.session_state:
            plot_data = st.session_state["active_scan"]
            fig = plot_heatmap_interactive(plot_data, vmin=vmin, vmax=vmax, cmap=cmap)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Run a scan to display the heatmap.")

# ============================
#    Analysis Page
# ============================
elif page == "Analysis":
    st.title("Analysis Page")
    
    # Folder selection for scanned files
    folder = st.text_input("Select Folder Containing Scan Files", value="data")
    
    if st.button("Refresh File List"):
        if os.path.isdir(folder):
            st.success(f"Folder found: {folder}")
        else:
            st.error("Folder does not exist. Please enter a valid folder path.")
    
    if os.path.isdir(folder):
        # List all .txt files in the folder
        txt_files = [f for f in os.listdir(folder) if f.endswith('.txt')]
        
        # Parse metadata from each file using the naming convention
        files_data = []
        for f in txt_files:
            meta = parse_filename(f)
            if meta:
                files_data.append(meta)
                
        if files_data:
            df_files = pd.DataFrame(files_data)
            st.write("### Found Scan Files", df_files)
            
            # --- Sidebar Filters ---
            st.sidebar.header("Filter Options")
            unique_prefixes = sorted(df_files["prefix"].unique().tolist())
            selected_prefix = st.sidebar.multiselect("Select Prefix", options=unique_prefixes, default=unique_prefixes)
            
            # Filter by X start (xs) range from file name
            min_x = float(df_files["xs"].min())
            max_x = float(df_files["xs"].max())
            x_range = st.sidebar.slider("X Start Range", min_x, max_x, (min_x, max_x))
            
            # Filter by Y start (ys) range from file name
            min_y = float(df_files["ys"].min())
            max_y = float(df_files["ys"].max())
            y_range = st.sidebar.slider("Y Start Range", min_y, max_y, (min_y, max_y))
            
            # Filter by timestamp (date) range – if available.
            if df_files["timestamp"].notnull().all():
                min_date = df_files["timestamp"].min().date()
                max_date = df_files["timestamp"].max().date()
                date_range = st.sidebar.date_input("Select Date Range", (min_date, max_date))
            else:
                date_range = None
            
            # --- Apply Filters ---
            filtered_df = df_files[
                (df_files["prefix"].isin(selected_prefix)) &
                (df_files["xs"] >= x_range[0]) & (df_files["xs"] <= x_range[1]) &
                (df_files["ys"] >= y_range[0]) & (df_files["ys"] <= y_range[1])
            ]
            if date_range and isinstance(date_range, list) and len(date_range) == 2:
                start_date, end_date = date_range
                filtered_df = filtered_df[
                    (filtered_df["timestamp"].dt.date >= start_date) & 
                    (filtered_df["timestamp"].dt.date <= end_date)
                ]
            
            st.write("### Filtered Files", filtered_df)
            
            # File selection from the filtered results
            selected_files = st.multiselect(
                "Select Files to Plot", 
                options=filtered_df["filename"].tolist(), 
                default=filtered_df["filename"].tolist()
            )
            
            # Plot button: display heatmaps for each selected file.
            if st.button("Plot Selected Files"):
                if not selected_files:
                    st.warning("No files selected for plotting.")
                else:
                    for file in selected_files:
                        file_path = os.path.join(folder, file)
                        try:
                            data = np.loadtxt(file_path)
                            fig = plot_heatmap_interactive(data)
                            st.plotly_chart(fig, use_container_width=True)
                            st.write(f"**Plotted file:** {file}")
                        except Exception as e:
                            st.error(f"Failed to load or plot {file}: {e}")
        else:
            st.info("No scan files found with the expected naming pattern in the specified folder.")
    else:
        st.warning("Please enter a valid folder path.")

# ============================
#    Single plot Page
# ============================
elif page == "Single plot":
    st.title("Single Plot")
    st.info("Upload a scan file (txt format) to display its heatmap plot.")
    
    uploaded_file = st.file_uploader("Choose a scan file", type="txt")
    
    if uploaded_file is not None:
        try:
            # Ensure the pointer is at the beginning of the file
            uploaded_file.seek(0)
            data = np.loadtxt(uploaded_file)
            fig = plot_heatmap_interactive(data)
            st.plotly_chart(fig, use_container_width=True)
            st.success("Plot generated successfully.")
        except Exception as e:
            st.error(f"Error loading or plotting the file: {e}")
    else:
        st.info("Awaiting file upload...")
