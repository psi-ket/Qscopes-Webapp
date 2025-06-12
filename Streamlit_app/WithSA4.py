from datetime import datetime, timedelta
import plotly.express as px
import streamlit as st
from PIL import Image
import pandas as pd
import numpy as np
import subprocess
import time
import clr
import os
import wx
import re
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.KCube.InertialMotorCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericMotorCLI.dll")
from Thorlabs.MotionControl.KCube.InertialMotorCLI import *
from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *

# --- Function to browse for an output directory using wxPython ---
def browse_for_output_dir():
    app = wx.App(False)
    dialog = wx.DirDialog(None, "Select Output Directory:", style=wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
    folder_path = ""
    if dialog.ShowModal() == wx.ID_OK:
        folder_path = dialog.GetPath()
    dialog.Destroy()
    return folder_path

# --- Function to load scan data from file ---
def load_data_in_2x50_chunks(filename, step):
    with open(filename, 'r') as f:
        lines = [line.strip() for line in f if line.strip() and line.strip() != "2D Voltage Scan Completed."]

    data_lines = []
    for line in lines:
        tokens = line.split()
        if tokens and tokens[0] in ["0.000000", ".000000"]:
            tokens = tokens[1:]
        if not tokens:
            continue
        floats = [float(x) for x in tokens]
        data_lines.append(floats)

    if not data_lines:
        raise ValueError("No valid data lines found in file.")

    nums_per_line = len(data_lines[0])
    for dl in data_lines:
        if len(dl) != nums_per_line:
            raise ValueError("Inconsistent number of floats per data line.")

    if step % nums_per_line != 0:
        raise ValueError("The step value must be an integer multiple of the number of floats per data line (after dummy removal).")
    lines_per_chunk = step // nums_per_line
    expected_lines = step * lines_per_chunk
    if len(data_lines) < expected_lines:
        raise ValueError(f"Expected at least {expected_lines} data lines, but got {len(data_lines)}.")

    data_rows = []
    for i in range(step):
        start = i * lines_per_chunk
        end = start + lines_per_chunk
        row_values = []
        for dl in data_lines[start:end]:
            row_values.extend(dl)
        data_rows.append(row_values)

    data_array = np.array(data_rows, dtype=float)
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
    fig.update_layout(autosize=True, width=800, height=800)
    return fig

# --- Function to parse file metadata from filename ---
def parse_filename_2d(filename):
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

def parse_filename_3d(fname):
    # Remove extension
    if fname.endswith('.txt'):
        fname = fname[:-4]
    # Match pattern (adjust as needed for your real pattern)
    pattern = (r"^(?P<prefix>scan)"
               r"_xs-(?P<xs>-?\d+\.?\d*)"
               r"_ys-(?P<ys>-?\d+\.?\d*)"
               r"_xe-(?P<xe>-?\d+\.?\d*)"
               r"_ye-(?P<ye>-?\d+\.?\d*)"
               r"_step-(?P<step>\d+)"
               r"_dw-(?P<dwell>-?\d+\.?\d*)"
               r"_z-(?P<z>-?\d+\.?\d*)"
               r"_(?P<timestamp>\d{8}_\d{6})$")
    m = re.match(pattern, fname)
    if m:
        meta = m.groupdict()
        # Convert to correct types
        meta['xs'] = float(meta['xs'])
        meta['ys'] = float(meta['ys'])
        meta['xe'] = float(meta['xe'])
        meta['ye'] = float(meta['ye'])
        meta['step'] = int(meta['step'])
        meta['dwell'] = float(meta['dwell'])
        meta['z'] = float(meta['z'])
        meta['timestamp'] = datetime.strptime(meta['timestamp'], "%Y%m%d_%H%M%S")
        meta['filename'] = fname + ".txt"
        return meta
    else:
        return None

def init_stage(serial_no: str):
    DeviceManagerCLI.BuildDeviceList()
    device = KCubeInertialMotor.CreateKCubeInertialMotor(serial_no)
    device.Connect(serial_no)
    time.sleep(0.25)
    if not device.IsSettingsInitialized():
        device.WaitForSettingsInitialized(10000)
    device.StartPolling(250)
    time.sleep(0.25)
    device.EnableDevice()
    time.sleep(0.25)
    cfg = device.GetInertialMotorConfiguration(serial_no)
    settings = ThorlabsInertialMotorSettings.GetSettings(cfg)
    chan = InertialMotorStatus.MotorChannels.Channel1
    settings.Drive.Channel(chan).StepRate = 500
    settings.Drive.Channel(chan).StepAcceleration = 100000
    device.SetSettings(settings, True, True)
    device.SetPositionAs(chan, 0)
    st.write(f"Moving stage to Z = {100}")
    device.MoveTo(chan, int(100), 60000)
    st.write("Stage move complete.")
    return device, chan
# --- Streamlit App Setup ---
st.set_page_config(layout="wide", page_title="Qscope App", page_icon="qscopes.png")
st.logo("New.png")
if "scanning" not in st.session_state:
    st.session_state["scanning"] = False
scanning = st.session_state["scanning"]

page = st.sidebar.selectbox("Select Page", ["Scan", "Analysis", "Single plot"])

# ============================
#       Scan Page
# ============================
if page == "Scan":
    st.title("Scan Page")
    col_left, col_mid, col_right = st.columns([1, 4, 1])

    with col_left:
        st.subheader("Scan Controls")
        scan_mode = st.radio("Scan Mode", ["Basic", "Advanced"], horizontal=True, disabled=scanning)
        # Basic vs Advanced X/Y inputs...
        if scan_mode == "Basic":
            basic_scan_area = st.number_input("Scan Area", value=1.0, step=0.01, key="basic_scan_area", disabled=scanning)
            l_ctrl, r_ctrl = st.columns([1, 1])
            with l_ctrl:
                basic_x_offset = st.number_input("X Offset", value=0.0, format="%.1f", key="basic_x_offset", disabled=scanning)
            with r_ctrl:
                basic_y_offset = st.number_input("Y Offset", value=0.0, format="%.1f", key="basic_y_offset", disabled=scanning)
            xs = basic_x_offset + basic_scan_area
            ys = basic_y_offset + basic_scan_area
            xe = basic_x_offset - basic_scan_area
            ye = basic_y_offset - basic_scan_area
        else:
            l_ctrl, r_ctrl = st.columns([1, 1])
            with l_ctrl:
                xs = st.number_input("X start", value=1.0, format="%.2f", key="adv_xs", disabled=scanning)
            with r_ctrl:
                ys = st.number_input("Y start", value=1.0, format="%.2f", key="adv_ys", disabled=scanning)
            with l_ctrl:
                xe = st.number_input("X end", value=-1.0, format="%.2f", key="adv_xe", disabled=scanning)
            with r_ctrl:
                ye = st.number_input("Y end", value=-1.0, format="%.2f", key="adv_ye", disabled=scanning)

        # Z-scan controls
        scan_3d = st.checkbox("3D Scan", key="scan_3d", disabled=scanning)
        if scan_3d:
            start_z = st.number_input("Start Z Step", value=0.0, step=0.1, disabled=scanning)
            inc_z = st.number_input("Increment Z Step", value=0.1, step=0.1, disabled=scanning)
            stop_z = st.number_input("Stop Z Step", value=1.0, step=0.1, disabled=scanning)

        # Other scan parameters
        l_ctrl, r_ctrl = st.columns([1, 1], vertical_alignment="bottom")
        with l_ctrl:
            step_val = st.number_input("Step (No. of Pixel)", value=100, step=25, min_value=25,
                                     help="Step size for the scan. Must be an integer multiple of the number of floats per data line.",
                                     disabled=scanning)
        with r_ctrl:
            dw = st.number_input("Dwell/P", value=1.0, step=0.5, min_value=1.0,
                                 help="Integration time per pixel", disabled=scanning)
        dw_seconds = dw / 1000
        total_seconds = (step_val ** 2) * dw_seconds * 1.65
        estimated_time = timedelta(seconds=total_seconds)
        st.markdown(f"**Estimated Scan Time:** {str(estimated_time)}")

        # Output settings
        st.markdown("**Output Settings**")
        l_ctrl, r_ctrl = st.columns([1, 1], vertical_alignment="bottom")
        with l_ctrl:
            output_dir = st.text_input("Output Directory", value="data", disabled=scanning)
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
        filename_prefix = st.text_input("Filename Prefix", value="scan", disabled=scanning)

        if st.button("Scan", disabled=scanning):
            st.session_state["scanning"] = True
            scanning = True
            time.sleep(0.1)
            # Prepare Z positions and stage
            z_positions = np.arange(start_z, stop_z+inc_z, inc_z) if scan_3d else [None]
            if scan_3d:
                device, chan = init_stage("97251223")
                time.sleep(1)
                

            for z in z_positions:
                if scan_3d:
                    st.write(f"Moving stage to Z = {z}")
                    device.MoveTo(chan, int(z), 60000)
                    st.write("Stage move complete.")

                args = ["-xs",str(xs),"-ys",str(ys),"-xe",str(xe),"-ye",str(ye),"-st",str(step_val),"-dw",str(dw)]
                proc = subprocess.Popen([r"scanwitharg.exe"]+args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                pbar = st.progress(0); ptext = st.empty(); exp=None
                while proc.poll() is None:
                    try: lines=[ln.strip() for ln in open("lua_output.txt") if ln.strip() and ln.strip()!="2D Voltage Scan Completed."]
                    except: lines=[]
                    if lines and exp is None:
                        toks = lines[0].split();
                        if toks[0] in ["0.000000",".000000"]: toks=toks[1:]
                        nppl=len(toks); lpC=step_val//nppl; exp=step_val*lpC
                    if exp:
                        cur=len(lines); frac=min(cur/exp,1.0)
                        pbar.progress(frac); ptext.text(f"Z={z} {cur}/{exp} lines")
                    time.sleep(0.2)
                pbar.progress(1.0); ptext.text(f"Z={z} completed.")
                proc.communicate()

                # Load and autosave
                try:
                    data = load_data_in_2x50_chunks("lua_output.txt", step_val)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    z_tag = f"_z-{z}" if scan_3d else ""
                    filename = f"{filename_prefix}_xs-{xs}_ys-{ys}_xe-{xe}_ye-{ye}_step-{step_val}_dw-{dw}{z_tag}_{timestamp}.txt"
                    save_dir = output_dir if os.path.isabs(output_dir) else os.path.join(os.getcwd(), output_dir)
                    os.makedirs(save_dir, exist_ok=True)
                    save_path = os.path.join(save_dir, filename)
                    np.savetxt(save_path, data, fmt="%.6f")
                    st.success(f"Data autosaved to {save_path}")
                    st.session_state['heatmap_data'] = data
                except Exception as e:
                    st.error(f"Error during scan or autosave at Z={z}: {e}")

            if scan_3d:
                device.StopPolling(); device.Disconnect()

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
    
    z_mode = st.radio("Filename mode", ["2D (no z in filename)", "3D (z in filename)"], index=1)
    
    if st.button("Refresh File List"):
        if os.path.isdir(folder):
            st.success(f"Folder found: {folder}")
        else:
            st.error("Folder does not exist. Please enter a valid folder path.")
    
    if os.path.isdir(folder):
        if z_mode == "3D (z in filename)":
            txt_files = [f for f in os.listdir(folder) if f.endswith('.txt') and "_z-" in f]
            parser = parse_filename_3d
        else:
            txt_files = [f for f in os.listdir(folder) if f.endswith('.txt') and "_z-" not in f]
            parser = parse_filename_2d
        
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
            x_range = st.sidebar.slider("X Start Range", min_x, max_x-1, (min_x, max_x-1))
            
            # Filter by Y start (ys) range from file name
            min_y = float(df_files["ys"].min())
            max_y = float(df_files["ys"].max())
            y_range = st.sidebar.slider("Y Start Range", min_y, max_y-1, (min_y, max_y-1))
            
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
