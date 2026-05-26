# TSS PC Controller Server Companion (Open-Source)

This is the open-source companion desktop server for the **TSS PC Controller** mobile application. It allows you to remote control your Windows PC from your paired mobile device over a secure local Wi-Fi connection.

## Features
- **Remote Mouse & Keyboard:** Zero-latency relative mouse movement, clicking, scrolling, and unicode keyboard input.
- **Real-Time Live Screen Sharing:** Fast, lightweight JPEG screen stream with dynamic optimization for crisp mobile display.
- **Administrative Utilities:** Remote command execution, UAC prompt control, shutdown, restart, and sleep triggers.
- **Local Connection & Pair Verification:** UDP-based auto-discovery and native PC popups for paired authorizations.
- **Windows System Tray Notifications:** Temporary Windows tray toast notifications appear whenever a paired device auto-connects to guarantee transparent, visible remote operations.
- **Background Silent Auto-Start:** Silent boot auto-run persistence via Windows Scheduled Tasks.

## Build and Package
To compile this project into a standalone executable:
```bash
pip install -r requirements.txt
pyinstaller --clean TSS_PC_Controller.spec
```
Then run Inno Setup on `setup_v5.5.iss` to package the executable into a complete Windows installer setup.

## Licensing
This companion server is licensed under the **GNU General Public License v3 (GPL v3)** to fully comply with all copyleft open-source package dependencies, including `pystray`.
