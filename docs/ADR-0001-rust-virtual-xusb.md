# ADR-0001: Rust-native application and self-maintained virtual XUSB driver

Status: **proposed, NOT shipped**
Date: 2026-10-09

## Goal

Replace the existing Python app and retired ViGEmBus dependency with a small native
Windows executable and the minimum independently maintained virtual Xbox device
component needed for real XInput compatibility.

## Non-negotiable constraints

- Real XInput/XUSB compatibility, including Xbox App and legacy games, not only
  generic HID / DirectInput visibility.
- Preserve Windows built-in USB and HID drivers; do not reinvent the OS driver stack.
- A virtual Xbox device still needs a Windows driver integration. Neither Rust,
  a single-file executable, nor a generic virtual HID device automatically
  provides real XInput compatibility.
- Production-ready driver package must meet Microsoft's applicable signing and
  installation requirements. Never instruct end users to disable Secure Boot,
  code-integrity protections, or antivirus for routine installation.
- No broad replacement of global HidHide settings. HidHide may remain optional;
  hiding unrelated devices is not acceptable.
- Rumble requires a supported game-to-virtual-device feedback path plus an
  independently implemented physical Nintendo haptic encoder.
- Driver source (if authored) must be separate from the user-mode application.

## Architecture

    Physical Nintendo USB HID device
       Windows inbox HID class driver
       -> native Rust USB/HID I/O and protocol/handshake
       -> switchprocon2xbox-core [portable pure Rust; this repo]
       -> XUSB backend abstraction
       -> own **signed** Windows virtual-device driver
       -> Windows inbox XUSB/XInput components -> games

Candidate approaches needing Windows VM/WDK proof-of-concept:
1. A self-maintained UMDF2 software-device/XUSB virtual bus implementation.
   HIDMaestro demonstrates the broad class of design, but its C# runtime is
   NOT accepted as a zero-runtime Rust solution. Its driver/XUSB mechanism
   must be independently validated before choosing any licensing approach.
2. UdeCx virtual USB controller/device with Windows's inbox USB/XUSB stack.
   Requires a separately authored, installable, signed client driver and
   exact Xbox USB descriptors/endpoints; it is NOT merely a Rust crate.
3. Generic VHF virtual HID only as an optional DirectInput/WGI mode.
   It does **not** prove XInput compatibility and cannot be the default.

The public Microsoft windows-drivers-rs project remains early-stage and
does not promise production-ready UMDF2/XUSB support out of the box.

## Deliverables and acceptance gates

- [x] Separate driver-free Rust report parser and mapping core.
- [x] Fault-safe virtual pad session abstraction with inactivity neutralization.
- [ ] Native Windows HID transport with Nintendo USB initialization.
- [ ] Switch 2 USB bulk wake path without a browser.
- [ ] Independent, documented virtual XUSB driver + IPC protocol + INF/CAT.
- [ ] Native Rust XUSB backend, virtual controller lifecycle and rumble feedback.
- [ ] Driver package production signing and Windows Secure Boot compatibility.
- [ ] Windows 10/11 x64 verification with physical Switch Pro + Switch 2 Pro.
- [ ] Game input tests: joy.cpl, XInputGetState, Xbox App, Steam, and games.
- [ ] Reconnect, stuck-buttons, haptics, resource-use, installer and rollback tests.
- [ ] Release builds, NOTICE/license review and honest installation documentation.

**Do not merge this project as a working Rust replacement until the gates pass.**

## Packaging goal

Rust executable + embedded verified signed driver package; driver installed
once after elevation. "Single-file distribution" must not be confused with
"zero-driver installation". No invented executable size or latency numbers.

## Primary references

- https://learn.microsoft.com/en-us/windows/win32/xinput/directinput-and-xusb-devices
- https://learn.microsoft.com/en-us/windows-hardware/drivers/usbcon/writing-a-ude-client-driver
- https://learn.microsoft.com/en-us/windows-hardware/drivers/dashboard/driver-signing-offerings
- https://github.com/microsoft/windows-drivers-rs
