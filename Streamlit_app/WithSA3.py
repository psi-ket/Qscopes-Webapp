import streamlit as st
import plotly.express as px
import numpy as np
import subprocess
import time
import os
from datetime import datetime, timedelta
import wx
import re
import pandas as pd
from PIL import Image

# Thorlabs Kinesis .NET API imports via pythonnet
import clr
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.DeviceManagerCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\Thorlabs.MotionControl.GenericMotorCLI.dll")
clr.AddReference("C:\\Program Files\\Thorlabs\\Kinesis\\ThorLabs.MotionControl.KCube.InertialMotorCLI.dll")
from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
from Thorlabs.MotionControl.KCube.InertialMotorCLI import KCubeInertialMotor  # type: ignore
from Thorlabs.MotionControl.GenericMotorCLI import ThorlabsInertialMotorSettings, InertialMotorStatus # type: ignore

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
        raise ValueError("The step value must be an integer multiple of the number of floats per data line.")
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
    return np.array(data_rows, dtype=float)

# --- Plotting helper ---
def plot_heatmap_interactive(data_array, vmin=None, vmax=None, cmap="hot"):
    fig = px.imshow(data_array, color_continuous_scale=cmap, zmin=vmin, zmax=vmax, aspect="equal")
    fig.update_xaxes(title_text="X Index")
    fig.update_yaxes(title_text="Y Index")
    fig.update_layout(autosize=True, width=800, height=800)
    return fig

# --- Filename parser ---
def parse_filename(filename):
    pattern = (r"^(.*?)_xs-([-+]?[0-9]*\.?[0-9]+)_ys-([-+]?[0-9]*\.?[0-9]+)_xe-([-+]?[0-9]*\.?[0-9]+)_"
               r"ye-([-+]?[0-9]*\.?[0-9]+)_step-([0-9]+)_dw-([-+]?[0-9]*\.?[0-9]+)_"
               r"([0-9]{8}_[0-9]{6})\.txt$")
    match = re.match(pattern, filename)
    if not match:
        return None
    try:
        timestamp = datetime.strptime(match.group(8), "%Y%m%d_%H%M%S")
    except:
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

# --- Kinesis Stage Initialization ---
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
    return device, chan

# --- Streamlit App ---
st.set_page_config(layout="wide", page_title="Qscope App", page_icon="qscopes.png")
st.logo("New.png")
if "scanning" not in st.session_state:
    st.session_state["scanning"] = False
scanning = st.session_state["scanning"]
page = st.sidebar.selectbox("Select Page", ["Scan", "Analysis", "Single plot"])

if page == "Scan":
    st.title("Scan Page")
    col_left, col_mid, col_right = st.columns([1, 4, 1])

    with col_left:
        st.subheader("Scan Controls")
        scan_mode = st.radio("Scan Mode", ["Basic", "Advanced"], horizontal=True, disabled=scanning)
        if scan_mode == "Basic":
            area = st.number_input("Scan Area", 1.0, step=0.01, key="basic_scan_area", disabled=scanning)
            l, r = st.columns(2)
            with l: xoff = st.number_input("X Offset", 0.0, format="%.1f", disabled=scanning)
            with r: yoff = st.number_input("Y Offset", 0.0, format="%.1f", disabled=scanning)
            xs, ys = xoff+area, yoff+area
            xe, ye = xoff-area, yoff-area
        else:
            l, r = st.columns(2)
            with l: xs = st.number_input("X start", 1.0, format="%.2f", disabled=scanning)
            with r: ys = st.number_input("Y start", 1.0, format="%.2f", disabled=scanning)
            with l: xe = st.number_input("X end", -1.0, format="%.2f", disabled=scanning)
            with r: ye = st.number_input("Y end", -1.0, format="%.2f", disabled=scanning)

        scan_3d = st.checkbox("3D Scan", key="scan_3d", disabled=scanning)
        if scan_3d:
            start_z = st.number_input("Start Z Step", 0.0, step=0.1, disabled=scanning)
            inc_z   = st.number_input("Increment Z Step", 0.1, step=0.1, disabled=scanning)
            stop_z  = st.number_input("Stop Z Step", 1.0, step=0.1, disabled=scanning)
            serial_no = st.text_input("Stage Serial No.", "97251223", disabled=scanning)

        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1: step_val = st.number_input("Step (Pixels)", 100, step=25, min_value=25, disabled=scanning)
        with c2: dw = st.number_input("Dwell/P", 1.0, step=0.5, min_value=1.0, disabled=scanning)
        est = timedelta(seconds=(step_val**2)*(dw/1000)*1.65)
        st.markdown(f"**Estimated Scan Time:** {est}")

        c1, c2 = st.columns(2, vertical_alignment="bottom")
        with c1: out_dir = st.text_input("Output Directory", "data", disabled=scanning)
        with c2:
            if st.button("Browse", disabled=scanning):
                sel = browse_for_output_dir()
                if sel:
                    st.session_state['output_dir'] = sel
                    st.success(f"Selected folder: {sel}")
        if 'output_dir' in st.session_state: out_dir = st.session_state['output_dir']
        prefix = st.text_input("Filename Prefix", "scan", disabled=scanning)

        if st.button("Scan", disabled=scanning):
            st.session_state["scanning"] = True
            scanning = True
            time.sleep(0.1)

            # Prepare Z positions and stage
            z_positions = np.arange(start_z, stop_z+inc_z, inc_z) if scan_3d else [None]
            if scan_3d:
                device, chan = init_stage(97251223)

            for z in z_positions:
                if scan_3d:
                    st.write(f"Moving stage to Z = {z}")
                    device.MoveTo(chan, int(Decimal(z)), 5000)
                    st.write("Stage move complete.")

                args = ["-xs",str(xs),"-ys",str(ys),"-xe",str(xe),"-ye",str(ye),"-st",str(step_val),"-dw",str(dw)]
                if scan_3d and z is not None: args += ["-z",str(z)]
                proc = subprocess.Popen([r"scanwithargt7.exe"]+args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
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

                try:
                    data = load_data_in_2x50_chunks("lua_output.txt", step_val)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    ztag = f"_z-{z}" if scan_3d else ""
                    fname = f"{prefix}_xs-{xs}_ys-{ys}_xe-{xe}_ye-{ye}_step-{step_val}_dw-{dw}{ztag}_{ts}.txt"
                    sdir = out_dir if os.path.isabs(out_dir) else os.path.join(os.getcwd(), out_dir)
                    os.makedirs(sdir, exist_ok=True)
                    path=os.path.join(sdir,fname)
                    np.savetxt(path, data, fmt="%.6f")
                    st.success(f"Data saved to {path}")
                    st.session_state['heatmap_data'] = data
                except Exception as e:
                    st.error(f"Error saving Z={z}: {e}")

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