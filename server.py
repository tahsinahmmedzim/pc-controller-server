import asyncio
import websockets
import json
import os
import subprocess
import webbrowser
import ctypes
import time
import socket
import threading
import sys
import shutil
import base64
import io
from PIL import Image
import mss
# Monkeypatch mss on Windows to disable CAPTUREBLT flag (0x40000000)
# This completely resolves physical mouse cursor flickering/blinking during screen sharing/capturing
try:
    import mss.windows.gdi
    mss.windows.gdi.CAPTUREBLT = 0
except Exception:
    pass
import pystray
from pystray import MenuItem as item
import tkinter as tk
from tkinter import messagebox
import pyaudiowpatch as pyaudio


# ===== CTYPES KEYBOARD CONTROL (ULTRA-LIGHTWEIGHT, UNICODE SUPPORT) =====
VK_CODES = {
    'backspace': 0x08,
    'enter': 0x0D,
    'esc': 0x1B,
    'volumeup': 0xAF,
    'volumedown': 0xAE,
    'volumemute': 0xAD,
    'playpause': 0xB3,
    'nexttrack': 0xB0,
    'prevtrack': 0xB1,
    'alt': 0x12,
    'f4': 0x73,
    'f': 0x46,
    'ctrl': 0x11,
    '+': 0xBB,
    '-': 0xBD,
    'left': 0x25,
    'right': 0x27,
    'win': 0x5B,
    'shift': 0x10,
    'tab': 0x09,
    'capslock': 0x14,
    'space': 0x20,
    'up': 0x26,
    'down': 0x28,
    'delete': 0x2E,
    'del': 0x2E,
    'insert': 0x2D,
    'home': 0x24,
    'end': 0x23,
    'pageup': 0x21,
    'pagedown': 0x22,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    ';': 0xBA,
    '=': 0xBB,
    ',': 0xBC,
    '.': 0xBE,
    '/': 0xBF,
    '`': 0xC0,
    '[': 0xDB,
    '\\': 0xDC,
    ']': 0xDD,
    "'": 0xDE,
}

def key_press(key):
    key = key.lower().strip()
    vk = VK_CODES.get(key)
    if vk:
        scan = ctypes.windll.user32.MapVirtualKeyA(vk, 0)
        ext = 1 if vk in [0x5B, 0x5C, 0x25, 0x26, 0x27, 0x28, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22] else 0
        ctypes.windll.user32.keybd_event(vk, scan, ext, 0)
        time.sleep(0.005)
        ctypes.windll.user32.keybd_event(vk, scan, ext | 2, 0)
    elif len(key) == 1:
        # Standard character fallback
        char_code = ord(key.upper())
        scan = ctypes.windll.user32.MapVirtualKeyA(char_code, 0)
        ctypes.windll.user32.keybd_event(char_code, scan, 0, 0)
        time.sleep(0.005)
        ctypes.windll.user32.keybd_event(char_code, scan, 2, 0)

def key_write(text):
    # KEYEVENTF_UNICODE = 0x0004
    # KEYEVENTF_KEYUP = 0x0002
    for char in text:
        utf16_bytes = char.encode('utf-16-le')
        for i in range(0, len(utf16_bytes), 2):
            code = int.from_bytes(utf16_bytes[i:i+2], byteorder='little')
            ctypes.windll.user32.keybd_event(0, code, 4, 0)
            ctypes.windll.user32.keybd_event(0, code, 4 | 2, 0)

def key_hotkey(*keys):
    vks = []
    for k in keys:
        k_str = k.lower().strip()
        vk = VK_CODES.get(k_str)
        if vk:
            vks.append(vk)
        elif len(k_str) == 1:
            vks.append(ord(k_str.upper()))
    
    # Press all keys in order
    for vk in vks:
        if vk:
            scan = ctypes.windll.user32.MapVirtualKeyA(vk, 0)
            ext = 1 if vk in [0x5B, 0x5C, 0x25, 0x26, 0x27, 0x28, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22] else 0
            ctypes.windll.user32.keybd_event(vk, scan, ext, 0)
            time.sleep(0.005)
            
    # Release all keys in reverse order
    for vk in reversed(vks):
        if vk:
            scan = ctypes.windll.user32.MapVirtualKeyA(vk, 0)
            ext = 1 if vk in [0x5B, 0x5C, 0x25, 0x26, 0x27, 0x28, 0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22] else 0
            ctypes.windll.user32.keybd_event(vk, scan, ext | 2, 0)
            time.sleep(0.005)

# ===== CTYPES MOUSE CONTROL (HIGH PERFORMANCE, ZERO BLINKING/SHAKING) =====
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def get_mouse_position():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

# Sub-pixel accumulator for relative mouse movement
mouse_accum_x = 0.0
mouse_accum_y = 0.0

def move_mouse_relative(dx, dy):
    global mouse_accum_x, mouse_accum_y
    mouse_accum_x += dx
    mouse_accum_y += dy
    
    move_x = int(mouse_accum_x)
    move_y = int(mouse_accum_y)
    
    if move_x != 0 or move_y != 0:
        mouse_accum_x -= move_x
        mouse_accum_y -= move_y
        # MOUSEEVENTF_MOVE = 0x0001
        ctypes.windll.user32.mouse_event(0x0001, move_x, move_y, 0, 0)

def mouse_click(button="left"):
    if button == "left":
        # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.005)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    elif button == "right":
        # MOUSEEVENTF_RIGHTDOWN = 0x0008, MOUSEEVENTF_RIGHTUP = 0x0010
        ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
        time.sleep(0.005)
        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
    elif button == "middle":
        # MOUSEEVENTF_MIDDLEDOWN = 0x0020, MOUSEEVENTF_MIDDLEUP = 0x0040
        ctypes.windll.user32.mouse_event(0x0020, 0, 0, 0, 0)
        time.sleep(0.005)
        ctypes.windll.user32.mouse_event(0x0040, 0, 0, 0, 0)

def mouse_down(button="left"):
    if button == "left":
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
    elif button == "right":
        ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
    elif button == "middle":
        ctypes.windll.user32.mouse_event(0x0020, 0, 0, 0, 0)

def mouse_up(button="left"):
    if button == "left":
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    elif button == "right":
        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
    elif button == "middle":
        ctypes.windll.user32.mouse_event(0x0040, 0, 0, 0, 0)

def mouse_double_click():
    mouse_click("left")
    time.sleep(0.05)
    mouse_click("left")

def mouse_scroll(dy):
    # MOUSEEVENTF_WHEEL = 0x0800
    # dy is scroll offset. Multiplying by 120 maps perfectly to standard WHEEL_DELTA.
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(dy * 120), 0)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
        return os.path.join(base_path, relative_path)
    except Exception:
        # Fallback to local paths
        for p in [relative_path, os.path.join("build_server", relative_path), os.path.join("..", relative_path)]:
            if os.path.exists(p):
                return os.path.abspath(p)
        return os.path.abspath(relative_path)

# ===== CONFIGURATION =====
VERSION = "5.5"
PORT = 8000
APP_NAME = "TSS_PC_Controller"
AUTHORIZED_FILE = os.path.join(os.getenv('APPDATA'), "TSS_PC_Controller", "trusted_devices.json")
os.makedirs(os.path.dirname(AUTHORIZED_FILE), exist_ok=True)
# Global state
stop_event = asyncio.Event()
streaming = {"wifi": False, "usb": False}
client_ready = {}
gui_open = False
IPC_PORT = 65432
tray_icon = None
stream_resolution = "720p"

# Track currently active connections and GUI controls
active_connections = {} # Maps websocket -> device_name
status_label = None
refresh_device_list_callback = None

def show_connection_notification(device_name, device_id=None):
    # Determine display message
    msg = f"Mobile App Connected: {device_name}"
    if device_id:
        msg = f"Mobile App Connected [{device_id}]"

    # Try native Windows Toast notifier using win10toast first
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        # Run in a daemon thread so it dismisses itself silently without blocking the server main loop
        threading.Thread(
            target=lambda: toaster.show_toast(
                "TPC Controller",
                msg,
                duration=4,
                threaded=True
            ),
            daemon=True
        ).start()
        print(f"[TSS] win10toast triggered successfully: {msg}")
        return
    except Exception as winErr:
        print(f"[TSS] win10toast not available: {winErr}")

    # Try native Windows notification using plyer as secondary
    try:
        from plyer import notification
        threading.Thread(
            target=lambda: notification.notify(
                title="TPC Controller",
                message=msg,
                app_name="TPC Controller",
                timeout=4
            ),
            daemon=True
        ).start()
        print(f"[TSS] plyer notification triggered successfully: {msg}")
        return
    except Exception as plyerErr:
        print(f"[TSS] plyer not available: {plyerErr}")

    # 3. Native Windows Balloon Notification via background PowerShell (100% thread-safe & reliable fallback)
    try:
        ps_code = f"""
[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms');
[void][System.Reflection.Assembly]::LoadWithPartialName('System.Drawing');
$bal = New-Object System.Windows.Forms.NotifyIcon;
$bal.Icon = [System.Drawing.SystemIcons]::Information;
$bal.BalloonTipTitle = 'TPC Controller';
$bal.BalloonTipText = '{msg}';
$bal.Visible = $true;
$bal.ShowBalloonTip(4000);
Start-Sleep -Seconds 1;
$bal.Dispose();
"""
        import subprocess
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_code.replace("\n", " ")],
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0x08000000
        )
        print(f"[TSS] PowerShell toast fallback triggered: {msg}")
    except Exception as e:
        print(f"[TSS] PowerShell toast fallback error: {e}")

    # 4. Fallback to pystray notify if icon exists
    global tray_icon
    if tray_icon:
        try:
            tray_icon.notify(msg, "TPC Controller")
        except Exception as e:
            print(f"[TSS] pystray notify fallback error: {e}")

def update_gui_status():
    global status_label, _gui_root, active_connections, refresh_device_list_callback
    if '_gui_root' in globals() and _gui_root and gui_open and status_label:
        try:
            connected_text = "No mobile connected"
            connected_color = "gray"
            if active_connections:
                connected_text = f"Connected: {', '.join(info['name'] for info in active_connections.values())}"
                connected_color = "#00E5FF"
            
            def update():
                status_label.config(text=connected_text, fg=connected_color)
                if refresh_device_list_callback:
                    refresh_device_list_callback()
                    
            _gui_root.after(0, update)
        except: pass

# ===== HELPER FUNCTIONS =====

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except: return socket.gethostbyname(socket.gethostname())

def wait_for_network(timeout=30, check_interval=2):
    """Wait for network connection to get a valid non-loopback IP address."""
    print("[TSS] Waiting for network initialization...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        ip = get_local_ip()
        if ip and ip != "127.0.0.1" and not ip.startswith("169.254"):
            print(f"[TSS] Network initialized! Active IP: {ip}")
            return ip
        time.sleep(check_interval)
    print("[TSS] Network initialization timeout. Using fallback IP.")
    return get_local_ip()

def get_config_path(filename):
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    config_dir = os.path.join(appdata, "TSS_PC_Controller")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, filename)

def load_trusted_devices():
    path = get_config_path("trusted_devices.json")
    if not os.path.exists(path): return {}
    try:
        with open(path, "r") as f: return json.load(f)
    except: return {}

def save_trusted_devices(devices):
    path = get_config_path("trusted_devices.json")
    try:
        with open(path, "w") as f: json.dump(devices, f)
    except: pass

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def run_as_admin():
    if not is_admin():
        if getattr(sys, 'frozen', False):
            executable = sys.executable
            params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        else:
            executable = sys.executable
            script = os.path.abspath(sys.argv[0])
            params = f'"{script}" ' + ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
            
        try:
            ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
        except Exception as e:
            print(f"[TSS] Elevation request failed: {e}")
        sys.exit(0)

def disable_secure_desktop():
    if not is_admin():
        return False
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE) as reg_key:
            winreg.SetValueEx(reg_key, "PromptOnSecureDesktop", 0, winreg.REG_DWORD, 0)
        print("[TSS] PromptOnSecureDesktop set to 0 in Registry successfully")
        return True
    except Exception as e:
        print(f"[TSS] Failed to set PromptOnSecureDesktop in Registry: {e}")
        return False

# ===== PERSISTENCE LOGIC =====

def self_install():
    """Establishes startup persistence in the Windows Registry and Scheduled Tasks to boot when the PC turns on"""
    if not getattr(sys, 'frozen', False): return
    try:
        current_exe = sys.executable
        is_in_appdata = "appdata" in os.path.normcase(current_exe)
        
        if is_in_appdata:
            target_exe = current_exe
        else:
            appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
            install_dir = os.path.join(appdata, "TSS_PC_Controller")
            os.makedirs(install_dir, exist_ok=True)
            target_exe = os.path.join(install_dir, f"{APP_NAME}.exe")
            if os.path.normcase(current_exe) != os.path.normcase(target_exe):
                shutil.copy2(current_exe, target_exe)
        
        # Remove from Windows Registry Run key to avoid duplicate startup trigger with Scheduled Tasks
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WRITE) as reg_key:
                try:
                    winreg.DeleteValue(reg_key, APP_NAME)
                    print("[TSS] Cleaned up legacy Windows Registry Run entry to prevent double-start")
                except FileNotFoundError:
                    pass
        except Exception as e:
            print(f"[TSS] Registry cleanup error: {e}")
            
        # Register backup Scheduled Task for UAC bypass
        try:
            task_name = APP_NAME
            subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True, creationflags=0x08000000, capture_output=True)
            subprocess.run(f'schtasks /create /tn "{task_name}" /tr "\\"{target_exe}\\" --startup" /sc onlogon /rl highest /f', shell=True, creationflags=0x08000000, capture_output=True)
            print("[TSS] Registered backup Scheduled Task as alternative auto-start")
        except Exception:
            pass
    except Exception as e:
        print(f"[TSS] Persistence Error: {e}")

def perform_uninstall():
    global tray_icon
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE | winreg.KEY_WRITE) as reg_key:
            winreg.DeleteValue(reg_key, APP_NAME)
        print("[TSS] Removed from startup registry")
    except Exception:
        pass
        
    try:
        task_name = APP_NAME
        subprocess.run(f'schtasks /delete /tn "{task_name}" /f', shell=True, creationflags=0x08000000)
        print("[TSS] Deleted Scheduled Task")
    except Exception:
        pass

    # Search for unins000.exe
    uninstaller = None
    dirs_to_check = [os.getcwd()]
    if getattr(sys, 'frozen', False):
        dirs_to_check.append(os.path.dirname(sys.executable))
    
    for d in dirs_to_check:
        p = os.path.join(d, "unins000.exe")
        if os.path.exists(p):
            uninstaller = p
            break
            
    if uninstaller:
        try:
            # Trigger standard Inno Setup uninstaller, which will handle removing files and shortcuts
            subprocess.Popen(f'"{uninstaller}"', shell=True)
            # Stop the pystray icon if exists
            if tray_icon:
                try:
                    tray_icon.stop()
                except:
                    pass
            os._exit(0)
        except Exception as e:
            print(f"[TSS] Failed to launch uninstaller: {e}")
            messagebox.showerror("Uninstall Error", f"Failed to launch uninstaller: {e}")
    else:
        # Fallback to bat self-delete if unins000.exe not found
        messagebox.showinfo("Uninstall Info", "Uninstaller executable (unins000.exe) not found. Performing basic self-deletion...")
        bat_path = os.path.join(os.environ["TEMP"], "tss_uninstall.bat")
        exe_path = sys.executable
        with open(bat_path, "w") as f:
            f.write("@echo off\n")
            f.write("timeout /t 2 /nobreak > NUL\n")
            f.write(f"del /f /q \"{exe_path}\"\n")
            f.write("del \"%~f0\"\n")
        
        subprocess.Popen(bat_path, creationflags=0x08000000)
        if tray_icon:
            try:
                tray_icon.stop()
            except:
                pass
        os._exit(0)

def show_gui():
    global gui_open
    if gui_open: return
    gui_open = True
    
    def gui_thread():
        global gui_open
        root = tk.Tk()
        root.title("TSS PC Server - Authorized Devices")
        root.geometry("400x500")
        root.configure(bg="#0F0E17")
        root.attributes("-topmost", True)

        # Set Window Icon
        try:
            icon_path = resource_path("App Icon.png")
            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                root.iconphoto(True, img)
        except Exception as e:
            print(f"[TSS] Error loading GUI icon: {e}")

        def on_close():
            global gui_open
            gui_open = False
            root.withdraw()
            print("[TSS] Window hidden, server still running in background")

        root.protocol("WM_DELETE_WINDOW", on_close)
        
        # Store root in a global variable so we can close it from other threads
        global _gui_root
        _gui_root = root

        # Header
        tk.Label(root, text="TSS PC SERVER", font=("Helvetica", 16, "bold"), bg="#0F0E17", fg="#00E5FF").pack(pady=(20, 5))
        tk.Label(root, text=f"IP: {get_local_ip()} | PORT: {PORT}", font=("Helvetica", 10), bg="#0F0E17", fg="white").pack(pady=5)
        
        # Connection Status Label
        global status_label
        connected_text = "No mobile connected"
        connected_color = "gray"
        if active_connections:
            connected_text = f"Connected: {', '.join(info['name'] for info in active_connections.values())}"
            connected_color = "#00E5FF"
        status_label = tk.Label(root, text=connected_text, font=("Helvetica", 10, "italic"), bg="#0F0E17", fg=connected_color)
        status_label.pack(pady=5)

        # Devices Container
        container = tk.Frame(root, bg="#1B1B2F", bd=0)
        container.pack(fill="both", expand=True, padx=20, pady=20)
        
        tk.Label(container, text="AUTHORIZED DEVICES", font=("Helvetica", 10, "bold"), bg="#1B1B2F", fg="#6C63FF").pack(pady=10)
        
        device_list_frame = tk.Frame(container, bg="#1B1B2F")
        device_list_frame.pack(fill="both", expand=True)

        def refresh_list():
            global refresh_device_list_callback
            refresh_device_list_callback = refresh_list
            for widget in device_list_frame.winfo_children(): widget.destroy()
            devices = load_trusted_devices()
            if not devices:
                tk.Label(device_list_frame, text="No devices paired yet", bg="#1B1B2F", fg="gray", font=("Helvetica", 9, "italic")).pack(pady=30)
                return
                
            for dev_id, dev_name in devices.items():
                row = tk.Frame(device_list_frame, bg="#1B1B2F")
                row.pack(fill="x", padx=10, pady=5)
                
                # Check if this device is online
                is_online = any(info['id'] == dev_id for info in active_connections.values())
                display_name = f"{dev_name} (Online)" if is_online else dev_name
                text_color = "#00E5FF" if is_online else "white"
                
                # Show full name with online color if applicable
                tk.Label(row, text=display_name, bg="#1B1B2F", fg=text_color, font=("Helvetica", 10, "bold")).pack(side="left")
                
                def remove_dev(did=dev_id, dname=dev_name):
                    if messagebox.askyesno("Unpair Device", f"Are you sure you want to remove access for:\n{dname}?", parent=root):
                        d = load_trusted_devices()
                        if did in d: del d[did]
                        save_trusted_devices(d)
                        # Instantly drop the WebSocket connection for this device
                        to_close = []
                        for ws, info in active_connections.items():
                            if info.get("id") == did:
                                to_close.append(ws)
                        async def force_unpair_and_close(ws_conn):
                            try:
                                await ws_conn.send(json.dumps({"status": "force_unpair"}))
                                await asyncio.sleep(0.1)
                            except:
                                pass
                            try:
                                await ws_conn.close(code=4003, reason="DEVICE_REMOVED")
                            except:
                                pass

                        for ws in to_close:
                            asyncio.run_coroutine_threadsafe(force_unpair_and_close(ws), main_loop)
                        refresh_list()
                
                tk.Button(row, text="Remove", command=remove_dev, bg="#FF3D71", fg="white", font=("Helvetica", 8, "bold"), relief="flat", padx=10).pack(side="right")

        refresh_list()

        # Action Buttons
        btn_frame = tk.Frame(root, bg="#0F0E17")
        btn_frame.pack(fill="x", pady=(0, 20), padx=20)

        def stop_server():
            if messagebox.askyesno("Stop Server", "Are you sure you want to stop the server?", parent=root):
                global tray_icon
                if tray_icon:
                    try:
                        tray_icon.stop()
                    except:
                        pass
                os._exit(0)

        def uninstall_server():
            if messagebox.askyesno("Uninstall", "This will remove the server from your system. Continue?", parent=root):
                perform_uninstall()

        tk.Button(btn_frame, text="STOP SERVER", command=stop_server, bg="#444", fg="white", font=("Helvetica", 10, "bold"), relief="flat", height=2).pack(fill="x", pady=5)
        tk.Button(btn_frame, text="UNINSTALL SERVER", command=uninstall_server, bg="#222", fg="#888", font=("Helvetica", 9), relief="flat").pack(fill="x")

        print("[TSS] GUI Loop Started")
        root.mainloop()
        print("[TSS] GUI Loop Ended")
        global gui_open
        gui_open = False
    
    # Check if window is already hidden
    if '_gui_root' in globals() and _gui_root:
        try:
            _gui_root.after(0, _gui_root.deiconify)
            _gui_root.after(0, _gui_root.lift)
            _gui_root.after(0, lambda: _gui_root.attributes("-topmost", True))
            gui_open = True
            return
        except: pass

    threading.Thread(target=gui_thread, daemon=True).start()

def ipc_server_task():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(('127.0.0.1', IPC_PORT))
        server.listen(1)
    except OSError:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(('127.0.0.1', IPC_PORT))
            s.sendall(b"SHOW_GUI")
            s.close()
        except: pass
        sys.exit(0)
    
    def listen_ipc():
        while True:
            try:
                conn, addr = server.accept()
                data = conn.recv(1024)
                if data == b"SHOW_GUI":
                    show_gui()
                conn.close()
            except: pass
    threading.Thread(target=listen_ipc, daemon=True).start()

# ===== COMMAND HANDLERS =====

async def handle_system_commands(target):
    print(f"[TSS] Executing System Command: {target}")
    if target == "lock": ctypes.windll.user32.LockWorkStation()
    elif target == "mute": key_press('volumemute')
    elif target == "volume up": key_press('volumeup')
    elif target == "volume down": key_press('volumedown')
    elif target in ["stop", "start", "playpause"]: key_press('playpause')
    elif target == "next": key_press('nexttrack')
    elif target == "previous": key_press('prevtrack')
    elif target == "shutdown":
        print("[TSS] Initiating Safe Shutdown: Closing all windows...")
        os.system('powershell -command "Get-Process | Where-Object {$_.MainWindowHandle -ne 0 -and $_.ProcessName -ne \'explorer\'} | ForEach-Object { $_.CloseMainWindow() }"')
        time.sleep(2)
        os.system("shutdown /s /t 2")
    elif target == "restart":
        print("[TSS] Initiating Safe Restart: Closing all windows...")
        os.system('powershell -command "Get-Process | Where-Object {$_.MainWindowHandle -ne 0 -and $_.ProcessName -ne \'explorer\'} | ForEach-Object { $_.CloseMainWindow() }"')
        time.sleep(2)
        os.system("shutdown /r /t 2")
    elif target == "sleep": os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

async def process_data(data, sender_type="wifi", websocket=None):
    global streaming
    msg_type = data.get("type")
    
    if msg_type == "heartbeat":
        if websocket:
            await websocket.send(json.dumps({"type": "heartbeat"}))
        return
        
    if msg_type == "frame_ack":
        global client_ready
        if websocket:
            client_ready[websocket] = True
        return
    
    if msg_type == "mouse_move":
        try:
            dx = float(data.get("dx", 0))
            dy = float(data.get("dy", 0))
            if dx != 0 or dy != 0:
                move_mouse_relative(dx, dy)
        except: pass

    elif msg_type == "scroll":
        try:
            dy = float(data.get("dy", 0))
            mouse_scroll(dy)
        except: pass
    
    elif msg_type == "mouse_click":
        button = data.get("button", "left")
        mouse_click(button=button)
        
    elif msg_type == "mouse_down":
        button = data.get("button", "left")
        mouse_down(button=button)

    elif msg_type == "mouse_up":
        button = data.get("button", "left")
        mouse_up(button=button)

    elif msg_type == "keyboard":
        key = data.get("key", "")
        if key == "backspace": key_press('backspace')
        elif key == "enter": key_press('enter')
        elif len(key) == 1: key_write(key)
        else: key_press(key)

    elif msg_type == "hotkey":
        keys = data.get("keys", [])
        if keys:
            key_hotkey(*keys)

    elif msg_type == "search":
        query = data.get("query", "")
        if query:
            webbrowser.open(f"https://www.google.com/search?q={query}")

    elif msg_type == "command":
        target = data.get("target", "").lower().strip()
        if target == "double_click": 
            mouse_double_click()
        elif target == "left_click":
            mouse_click('left')
        elif target == "right_click":
            mouse_click('right')
        elif target == "middle_click":
            mouse_click('middle')
        elif target == "close":
            key_hotkey('alt', 'f4')
        elif target == "close all":
            os.system('powershell -command "Get-Process | Where-Object {$_.MainWindowHandle -ne 0 -and $_.ProcessName -ne \'explorer\'} | ForEach-Object { $_.CloseMainWindow() }"')
        elif target == "chrome":
            os.system('start chrome')
        elif target.startswith("open "):
            site = target.replace("open ", "").strip()
            webbrowser.open(f"https://www.{site}.com")
        elif target.startswith("play "):
            # Pause currently playing media before opening a new song
            try:
                key_press('playpause')
                time.sleep(0.5)
            except: pass
            
            song = target.replace("play ", "").strip()
            try:
                import urllib.request
                import urllib.parse
                import re
                
                search_keyword = urllib.parse.quote(song)
                search_url = f"https://www.youtube.com/results?search_query={search_keyword}"
                
                req = urllib.request.Request(
                    search_url, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                )
                
                html = urllib.request.urlopen(req, timeout=5)
                content = html.read().decode()
                video_ids = re.findall(r"watch\?v=(\S{11})", content)
                
                if video_ids:
                    direct_url = f"https://www.youtube.com/watch?v={video_ids[0]}"
                    webbrowser.open(direct_url)
                    print(f"[TSS] Playing: {direct_url}")
                else:
                    # Fallback to search if scrape fails to find video IDs
                    webbrowser.open(search_url)
            except Exception as e:
                print(f"[TSS] Play failed, falling back to search: {e}")
                webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(song)}")
        elif target == "b on":
            os.system('powershell -Command "Add-Type -AssemblyName System.Runtime.WindowsRuntime; $radios = [Windows.Devices.Radios.Radio]::GetRadiosAsync().GetAwaiter().GetResult(); foreach($r in $radios){ if($r.Kind -eq \'Bluetooth\'){ $r.SetStateAsync(\'On\').GetAwaiter().GetResult() } }"')
        elif target == "b off":
            os.system('powershell -Command "Add-Type -AssemblyName System.Runtime.WindowsRuntime; $radios = [Windows.Devices.Radios.Radio]::GetRadiosAsync().GetAwaiter().GetResult(); foreach($r in $radios){ if($r.Kind -eq \'Bluetooth\'){ $r.SetStateAsync(\'Off\').GetAwaiter().GetResult() } }"')
        elif target == "h on":
            os.system('powershell -Command "Add-Type -AssemblyName System.Runtime.WindowsRuntime; $mhs = [Windows.Networking.NetworkOperators.NetworkOperatorAbilityService, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]::GetForNetworkAdapterAsync((Get-NetAdapter | Where-Object {$_.Name -match \'Wi-Fi\'}).InterfaceGuid).GetResults(); if($mhs){$mhs.TryEnableAsync().GetResults()}"')
        elif target == "h off":
             os.system('powershell -Command "Add-Type -AssemblyName System.Runtime.WindowsRuntime; $mhs = [Windows.Networking.NetworkOperators.NetworkOperatorAbilityService, Windows.Networking.NetworkOperators, ContentType=WindowsRuntime]::GetForNetworkAdapterAsync((Get-NetAdapter | Where-Object {$_.Name -match \'Wi-Fi\'}).InterfaceGuid).GetResults(); if($mhs){$mhs.TryDisableAsync().GetResults()}"')
        elif target == "full screen":
            key_press('f')
        elif target == "close full screen":
            key_press('esc')
        elif target == "forward":
            key_press('right')
        elif target == "rewind":
            key_press('left')
        else:
            await handle_system_commands(target)

    elif msg_type == "start_stream":
        print(f"[TSS] Start Stream Requested via {sender_type}")
        streaming[sender_type] = True
        asyncio.create_task(stream_screen(websocket, sender_type))
            
    elif msg_type == "stop_stream":
        print("[TSS] Stop Stream Requested")
        streaming[sender_type] = False

    elif msg_type == "toggle_audio":
        enabled = data.get("enabled", False)
        print(f"[TSS] Toggle Audio Requested: {enabled}")
        global audio_streaming
        if enabled:
            if not audio_streaming:
                audio_streaming = True
        else:
            audio_streaming = False

    elif msg_type == "set_resolution":
        resolution = data.get("resolution", "720p")
        global stream_resolution
        stream_resolution = resolution
        print(f"[TSS] Resolution changed dynamically to: {resolution}")
        return


async def stream_screen(websocket, sender_type):
    global streaming, client_ready
    print(f"[TSS] Real-time Stream Started for {sender_type}")
    
    last_state = None
    client_ready[websocket] = True  # Initialize as ready

    def capture_frame(sct, last_state_tuple):
        monitors = sct.monitors
        mon = monitors[1] if len(monitors) > 1 else monitors[0]
        img = sct.grab(mon)
        pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        
        # 1. Compute fast hash of the screen before drawing mouse
        try:
            tiny_img = pil_img.resize((32, 32), Image.NEAREST)
            f_hash = hash(tiny_img.tobytes())
        except Exception:
            f_hash = 0
        
        # 2. Get mouse position
        try:
            mx, my = get_mouse_position()
            mx_rel, my_rel = mx - mon["left"], my - mon["top"]
        except Exception:
            mx, my = 0, 0
            mx_rel, my_rel = 0, 0
            
        current_state = (f_hash, mx, my)
        
        # If the state matches last state, skip compression and base64 encoding entirely!
        if last_state_tuple and current_state == last_state_tuple:
            return None, current_state
            
        # Draw Virtual Mouse Cursor
        try:
            from PIL import ImageDraw
            draw = ImageDraw.Draw(pil_img)
            r = 6 # cursor radius
            draw.ellipse((mx_rel-r, my_rel-r, mx_rel+r, my_rel+r), fill=(0, 255, 255), outline=(255, 255, 255))
        except Exception:
            pass

        # Dynamically scale resolution based on user preference (720p vs 1080p HD)
        global stream_resolution
        if stream_resolution == "1080p":
            target_res = (1920, 1080)
            quality = 50
        else: # default 720p
            target_res = (1280, 720)
            quality = 42
            
        pil_img.thumbnail(target_res, Image.NEAREST)
            
        buffer = io.BytesIO()
        pil_img.save(buffer, format="JPEG", quality=quality, optimize=False)
        encoded_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        return encoded_str, current_state

    try:
        with mss.mss() as sct:
            while streaming.get(sender_type, False):
                try:
                    # Self-regulating real-time loop: only capture and send if client is ready!
                    if client_ready.get(websocket, True):
                        frame_data, current_state = await asyncio.to_thread(capture_frame, sct, last_state)
                        last_state = current_state
                        if frame_data is not None:
                            client_ready[websocket] = False  # Wait for frame_ack
                            await websocket.send(json.dumps({
                                "type": "screen_frame", 
                                "data": frame_data
                            }))
                    await asyncio.sleep(0.002) # Super responsive check every 2ms
                except Exception as e:
                     print(f"[TSS] Stream Send Error: {e}")
                     break
    except Exception as e:
        print(f"[TSS] Stream Fatal Error: {e}")
    finally:
        streaming[sender_type] = False
        print(f"[TSS] Real-time Stream Stopped for {sender_type}")


# Global audio streaming state
audio_streaming = False

def stream_audio(websocket):
    global audio_streaming, main_loop
    print("[TSS] Audio stream thread started")
    
    p = pyaudio.PyAudio()
    stream = None
    try:
        # Find default WASAPI loopback device
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        loopback_dev = None
        for i in range(p.get_device_count()):
            dev_info = p.get_device_info_by_index(i)
            if dev_info.get('hostApi') == wasapi_info['index'] and dev_info.get('isLoopbackDevice', False):
                loopback_dev = dev_info
                break
                
        if loopback_dev is None:
            print("[TSS] Error: No WASAPI loopback device found")
            return
            
        rate = int(loopback_dev['defaultSampleRate'])
        channels = int(loopback_dev['maxInputChannels'])
        
        stream = p.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=loopback_dev['index']
        )
        
        # Audio streaming loop
        chunk_size = 512
        while audio_streaming:
            try:
                available = stream.get_read_available()
                if available >= chunk_size:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                    if data:
                        # Downsample to 16kHz mono PCM
                        downsample_factor = int(rate / 16000)
                        if downsample_factor < 1:
                            downsample_factor = 1
                        
                        frame_size = channels * 2
                        step = frame_size * downsample_factor
                        
                        mv = memoryview(data)
                        mono_data = b"".join(mv[i : i + 2] for i in range(0, len(mv), step))
                        
                        encoded_str = base64.b64encode(mono_data).decode('utf-8')
                        
                        if main_loop:
                            asyncio.run_coroutine_threadsafe(
                                websocket.send(json.dumps({
                                    "type": "audio_frame",
                                    "data": encoded_str
                                })),
                                main_loop
                            )
                else:
                    time.sleep(0.005)
            except Exception as e:
                print(f"[TSS] Audio record error: {e}")
                break
    except Exception as e:
        print(f"[TSS] Audio stream error: {e}")
    finally:
        if stream:
            try:
                stream.stop_stream()
                stream.close()
            except:
                pass
        p.terminate()
        audio_streaming = False
        print("[TSS] Audio stream thread finished")


# ===== SERVERS =====

async def handle_ws_client(websocket, *args):
    """Compatible with both old (websocket, path) and new (websocket) signatures"""
    global active_connections
    print(f"[TSS] Client Joined: {websocket.remote_address}")
    authorized = False
    device_id = None
    
    try:
        async for message in websocket:
            try:
                print(f"[TSS] Incoming: {message[:100]}...") # Log first 100 chars
                data = json.loads(message)
                msg_type = data.get("type")
                
                # Handling Pairing/Auth
                if msg_type == "pair_request":
                    print(f"[TSS] Pairing request from: {data.get('device_name')}")
                    device_id = data.get("device_id")
                    device_name = data.get("device_name", "Unknown Mobile")
                    
                    if not device_id:
                        await websocket.send(json.dumps({"type": "pair_response", "status": "rejected", "message": "Missing Device ID"}))
                        continue
                        
                    trusted = load_trusted_devices()
                    if device_id in trusted:
                        # Device is already trusted -> silent auto-connect (bypass popup)
                        print(f"[TSS] Device {device_name} is already trusted. Silent auto-connect established.")
                        authorized = True
                        device_name = trusted[device_id]
                        active_connections[websocket] = {"name": device_name, "id": device_id}
                        update_gui_status()
                        await websocket.send(json.dumps({"type": "pair_response", "status": "accepted", "name": socket.gethostname()}))
                        show_connection_notification(device_name, device_id=device_id)
                    else:
                        # First-Time / unrecognized device -> display Yes/No popup on PC
                        print(f"[TSS] Unrecognized Device {device_name} requesting pairing. Displaying confirmation popup...")
                        
                        def ask_native():
                            return ctypes.windll.user32.MessageBoxW(0, 
                                f"Are you sure to connect this mobile on your PC / Laptop to connect TSS PC Controller App??\n\nDevice: {device_name}", 
                                "TSS PC Controller - Pairing Request", 
                                4 | 32 | 262144)
                        
                        res = await asyncio.to_thread(ask_native)
                        if res == 6: # IDYES
                            duplicate_ids = [k for k, v in trusted.items() if v == device_name]
                            for old_id in duplicate_ids:
                                del trusted[old_id]
                                
                            trusted[device_id] = device_name
                            save_trusted_devices(trusted)
                            authorized = True
                            active_connections[websocket] = {"name": device_name, "id": device_id}
                            update_gui_status()
                            await websocket.send(json.dumps({"type": "pair_response", "status": "accepted", "name": socket.gethostname()}))
                            show_connection_notification(device_name, device_id=device_id)
                        else:
                            await websocket.send(json.dumps({"type": "pair_response", "status": "rejected"}))
                    continue

                if msg_type == "unpair":
                    print(f"[TSS] Unpair request from device: {device_name}")
                    trusted = load_trusted_devices()
                    if device_id in trusted:
                        del trusted[device_id]
                        save_trusted_devices(trusted)
                    if websocket in active_connections:
                        del active_connections[websocket]
                    update_gui_status()
                    await websocket.close()
                    continue

                if not authorized:
                    # Ignore all other commands if not authorized
                    await websocket.send(json.dumps({"type": "error", "message": "Unauthorized. Please pair first."}))
                    continue

                await process_data(data, sender_type="wifi", websocket=websocket)
            except Exception as e:
                print(f"[TSS] Data Error: {e}")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"[TSS] WebSocket Closed: {e.code} - {e.reason}")
    except Exception as e:
        print(f"[TSS] WS Client Error: {e}")
    finally:
        global streaming, audio_streaming
        streaming["wifi"] = False
        audio_streaming = False
        if websocket in active_connections:
            del active_connections[websocket]
            update_gui_status()
        print("[TSS] State Cleaned Up")

def start_discovery_broadcast():
    broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    while True:
        try:
            current_ip = get_local_ip()
            message = json.dumps({"type": "tss_discovery", "ip": current_ip, "port": PORT, "name": socket.gethostname()})
            broadcast_sock.sendto(message.encode('utf-8'), ('255.255.255.255', 8001))
            time.sleep(2)
        except:
            time.sleep(2)

# ===== TRAY =====
def setup_tray(ip):
    icon_image = Image.new('RGBA', (64, 64), color=(0, 255, 255, 255))
    def on_stop(icon, item):
        icon.stop()
        os._exit(0)
    
    def on_open(icon, item):
        show_gui()

    menu = pystray.Menu(
        item("IP: " + ip, lambda: None, enabled=False),
        item("Open Server", on_open, default=True),
        item("Exit", on_stop)
    )
    
    # Try to load app icon if exists
    try:
        icon_path = resource_path("App Icon.png")
        if os.path.exists(icon_path):
            icon_img = Image.open(icon_path)
        else:
            icon_img = Image.new('RGBA', (64, 64), color=(0, 255, 255, 255))
    except Exception:
        icon_img = Image.new('RGBA', (64, 64), color=(0, 255, 255, 255))
        
    global tray_icon
    icon = pystray.Icon(APP_NAME, icon_img, "TSS Server", menu)
    tray_icon = icon
    icon.run_detached()

main_loop = None

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    # Activate mouse API immediately to ensure cursor responsiveness
    try:
        move_mouse_relative(0, 0)
    except:
        pass
    
    # Delayed boot handling for network interfaces to connect to routers
    is_startup = "--startup" in sys.argv
    if is_startup:
        print("[TSS] Detected boot startup. Waiting for Windows network interfaces...")
        time.sleep(5)
        
    ip = wait_for_network()
    
    print("="*40)
    print(f"  TSS PC CONTROLLER SERVER V5.5")
    print(f"  STATUS: ONLINE (WIFI ONLY)")
    print(f"  IP ADDRESS: {ip}")
    print(f"  PORT: {PORT}")
    print("="*40)
    
    self_install() # Ensure auto-run on startup
    setup_tray(ip)
    
    # Start dynamic UDP Discovery
    threading.Thread(target=start_discovery_broadcast, daemon=True).start()
    
    try:
        async with websockets.serve(handle_ws_client, "0.0.0.0", PORT, ping_interval=5, ping_timeout=10):
            await stop_event.wait()
    except Exception as e:
        print(f"[TSS] WebSocket Server Error: {e}")
        messagebox.showerror("TSS Server Error", f"Could not start server: {e}")


if __name__ == "__main__":
    if not is_admin():
        run_as_admin()
    
    # Disable secure desktop so UAC prompts can be shown on main desktop and clicked remotely
    disable_secure_desktop()

    ipc_server_task()
    is_startup = "--startup" in sys.argv
    if not is_startup:
        show_gui()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Fatal Error: {e}")