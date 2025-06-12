# Qscopes-Webapp

# Control System and Data Acquisition

This project implements a control system and data acquisition setup using a **LabJack** microcontroller. The system uses a **Streamlit** interface (Python) as the frontend, a **C++** backend for core logic, and **Lua** scripts on the device for embedded firmware-level control.

---

## 🧩 Project Components

- **Frontend**: Python with [Streamlit](https://streamlit.io/)
- **Backend**: C++
- **Firmware**: Lua running on the LabJack device
- **Microcontroller**: LabJack (e.g., T7 or T4)

---

## 📦 Requirements

- LabJack device (T7 or compatible)
- [LabJack Kipling](https://labjack.com/pages/support?doc=/software-driver/kipling/) (for firmware flashing)
- Python 3.8+
- C++ compiler (e.g., `g++`)
- LabJack drivers (LJM)
- Streamlit: `pip install streamlit`
- Additional Python packages: see `requirements.txt`

---

## 🔧 Setup Instructions

### 1. 🔌 Connect the LabJack

Connect your LabJack device to your PC via USB or Ethernet.

---

### 2. ⚡ Flash Firmware with Kipling

1. Open [Kipling](https://labjack.com/pages/support?doc=/software-driver/kipling/).
2. Connect to your LabJack device.
3. Navigate to the **Device Updater** tab.
4. Load and flash the provided Lua firmware script to the device.
   - Firmware location: `firmware/main.lua`

---

### 3. 🛠️ Compile the C++ Backend

Compile the backend logic using a C++ compiler:

```bash
g++ backend/main.cpp -o backend/main
