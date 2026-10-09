# DS4 Desktop Adapter

Use a DualShock 4 as a mouse and keyboard on Windows 10 or 11. Move the pointer, click, scroll, type with an on-screen keyboard, and use common shortcuts. Desktop controls pause for detected games. Fullscreen videos stay controllable.

## Start

You need a DualShock 4 connected by Bluetooth or a micro-USB data cable. Running the source requires Python 3.10 or newer.

1. Download this repository and extract it.
2. Open PowerShell in the project folder and run `./setup.ps1`.
3. Double-click `Start Adapter.cmd`.
4. Wait for the controller to connect, then release its buttons and sticks.

If the app says it is waiting for a controller, press the PS button to wake it. If PowerShell blocks the setup script, run these commands instead:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Closing the window keeps the adapter running in the system tray. Choose Quit to stop it. Start at sign-in is available in Settings and is off by default.

## Where is Share?

Share is the small button immediately to the left of the touchpad, above the left stick. It is labeled SHARE.

The PS logo button is below the touchpad, between the sticks. That is a different button.

Options is the small button on the right side of the touchpad.

## Copy and paste

The Desktop, Keyboard, and Shortcuts buttons in the app only change the instructions you see. You do not need to open the Shortcuts page to use a shortcut.

Hold Share first, tap the other button, then release both:

* Share + Square: copy selected text, like Ctrl+C.
* Share + Triangle: paste, like Ctrl+V.
* Share + X: select all in the focused text field, like Ctrl+A.
* Share + Circle: cut selected text, like Ctrl+X.
* Share + L1: undo, like Ctrl+Z.
* Share + R1: redo, like Ctrl+Y.
* Share + D-pad left or right: switch to the previous or next browser tab.

Copy needs selected text. To copy everything from one text field to another:

1. Move the pointer to the source field and click R2.
2. Hold Share, tap X, then release both to select all.
3. Hold Share, tap Square, then release both to copy.
4. Close the keyboard with Options if it is open, then click the destination field with R2.
5. Hold Share, tap Triangle, then release both to paste.

Pressing Square without Share sends Backspace. Shortcuts are disabled while the adapter is paused for gaming.

## Desktop controls

* Right stick or touchpad: move the pointer.
* X or R2: left click. Hold to drag.
* L2: right click.
* Left stick up or down: scroll.
* D-pad: arrow keys.
* Circle: Escape.
* Square: Backspace.
* Triangle: open the keyboard.
* Options: show or hide the keyboard when released.
* L1 or R1: previous or next browser tab.
* Hold L3: slower pointer movement.
* R3: middle click.
* Touchpad click: left click.

## Type with the controller

Click a text field with R2, then press and release Options to open the keyboard. Fast mode gives each hand its own selection so you do not have to cross the whole keyboard for every letter.

* Left stick: move the blue selection through the left half. L2 types that key.
* Right stick: move the green selection through the right half. R2 types that key.
* D-pad: move the active selection across the whole keyboard.
* X: type the active key, marked with a white outline.
* Circle: close the keyboard.
* Square: Backspace. Hold to keep deleting.
* Triangle: Space.
* L1: toggle Shift.
* R1: Enter.

Release a trigger between letters. Holding a direction repeats navigation, then speeds up for longer moves. Adjust Navigation speed in the Typing & vibration tab. Use Fast / Classic in the keyboard header to switch modes. Classic keeps the familiar left stick or D-pad selection and X confirmation, with the right stick controlling the pointer.

In Fast mode, the sticks and triggers belong to the keyboard. The touchpad still moves and clicks the pointer. Close the keyboard to restore normal mouse controls.

The panel also supports pointer selection, English and Russian layouts, Caps, punctuation, and clipboard buttons. It keeps the text field focused while you type. Share shortcuts work while the panel is open.

Drag the keyboard header to move it. Size cycles through small, compact, and large. Top / bottom changes its position. The keyboard fits inside the monitor work area so it stays above the Windows taskbar. Size and position preferences are saved.

The optional Windows keyboard in Settings supports pointer use. Stick and D-pad key selection work with the included adapter keyboard. Windows may block simulated clicks on its own accessibility keyboard.

## Vibration feedback

Typing gives a light pulse. Enter gives a stronger confirmation. Copy, paste, editing, and opening or closing the keyboard have short cues too. Cues are sent after Windows accepts the input; they cannot verify what the receiving app does with it.

Open Typing & vibration to change the strength, disable feedback, or press Test vibration while holding the controller. Small overlapping cues are skipped so feedback does not build up behind your typing.

The adapter stops its vibration when controls pause, focus changes, the controller disconnects, or the app closes. It does not change the lightbar. If a controller rejects vibration output, desktop input continues and the app shows a warning. Reconnect to retry.

## Playing games

Automatic mode pauses desktop controls for Steam games detected by their installation folder and programs added in the Games tab. Being fullscreen alone does not pause the adapter by default.

To leave fullscreen video, press Circle for Escape. If the adapter keyboard is open, the first Circle closes it; press Circle again to send Escape. Players that use a different fullscreen shortcut can still be controlled with the pointer and their on-screen buttons.

For other games, add their executable in Games or hold Share + Options for about one second to pause manually. Repeat the combination after playing to return to Automatic mode. Ctrl+Alt+F12 does the same thing from the laptop keyboard.

The keyboard closes when gaming pause starts. Release all buttons and sticks before returning to desktop control. The adapter also releases held synthetic clicks after a focus change, disconnection, or shutdown.

Settings includes an optional pause for other fullscreen apps. Common browsers and video players stay controllable unless you explicitly add them to Games. Upgrading an older settings file turns the broad fullscreen pause off to avoid trapping you in videos.

This app leaves the controller available to games. It does not emulate an Xbox controller. Games that require XInput may need Steam Input or another compatibility tool. Automatic game detection can miss some windowed games, so use manual pause when needed.

If Steam or another mapper also moves the pointer, disable its desktop mapping to avoid duplicate input. The adapter does not change Steam settings.

## Settings and limitations

Settings and rotating connection logs are stored in `%LOCALAPPDATA%\DS4DesktopAdapter`. Typed text is not logged. No account or network service is required.

Administrator prompts, the Windows sign-in screen, and some elevated applications may require the laptop keyboard or touchpad.

## Build and test

Build a Windows package with `./build.ps1`. The result is `dist\DS4DesktopAdapter\DS4DesktopAdapter.exe`. Keep that executable together with its accompanying files. Build output is not stored in this repository.

Run the automated tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run the interactive keyboard check:

```powershell
.\.venv\Scripts\python.exe tests/panel_smoke.py
```

Activate the temporary test window if requested. This check exercises typing with both sticks and triggers, X confirmation, clipboard shortcuts, focus preservation, keyboard placement, and leaving fullscreen with Circle in its own window.

To test vibration on a connected controller, hold it and run:

```powershell
.\.venv\Scripts\python.exe tests/feedback_smoke.py
```

Automated checks cover input mappings, navigation, USB and Bluetooth output packets, vibration timing, focus changes, and fullscreen detection. Windows integration checks passed for typing and leaving a fullscreen test window. A Bluetooth DualShock 4 accepted vibration start and stop reports while input continued. Physical USB vibration, typing speed with human participants, and a full gaming session have not been tested.

## Project files

* `main.py`: application entry point and diagnostics.
* `adapter/controller.py`: USB and Bluetooth input and output.
* `adapter/feedback.py`: vibration packets and short cues.
* `adapter/engine.py`: controller mappings and pause behavior.
* `adapter/keyboard.py`: keyboard panel.
* `adapter/keyboard_model.py`: key layout and navigation.
* `adapter/navigation.py`: shared direction handling and repeat timing.
* `adapter/service.py`: background input service.
* `adapter/ui.py`: settings and controls window.
* `adapter/windows.py`: Windows input and foreground detection.
* `tests`: automated and interactive checks.

## Design references

The two selections and matching triggers follow the dual QWERTY approach studied in [Text Entry Using a Dual Joystick Game Controller](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/10/Text-Entry-Using-a-Dual-Joystick-Game-Controller.pdf). That study informs the layout; it is not a speed measurement of this app.

Vibration packet formats follow Sony's implementation in the [Linux PlayStation HID driver](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c). Windows output handling accounts for the report padding described in [HIDAPI's known issues](https://github.com/libusb/hidapi/wiki/Known-Issues).

## Image credit

The controller photograph comes from [Sony's DualShock 4 product page](https://www.playstation.com/en-us/accessories/dualshock-4-wireless-controller/). The photograph and PlayStation marks belong to their respective owners. This is an independent project and is not affiliated with Sony.
