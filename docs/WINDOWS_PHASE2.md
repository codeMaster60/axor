# Axor Phase 2: Windows support (design document, NOT implemented)

Status: planning only. Phase 1 (macOS) is built and tested. Nothing below exists in code yet.

## Goal
Same Axor commands and UI on Windows 10/11, reusing the Flask server, rule router, SQLite store, sync and dashboard unchanged.

## What is platform-specific today (all in `server.py`, behind `IS_MAC`)
| Capability | macOS now | Windows plan |
|---|---|---|
| Open/close apps | `open -a`, `osascript` quit | `os.startfile` / `start`, `taskkill /IM` |
| Text to speech | `say` (Daniel/Tara) | `pyttsx3` (SAPI5 voices) |
| Volume/mute | `osascript` | `pycaw` (Core Audio) |
| Battery | `pmset` | `psutil.sensors_battery()` |
| Screenshot | `screencapture` | `PIL.ImageGrab` |
| Lock screen | pmset/osascript | `rundll32 user32.dll,LockWorkStation` |
| Meetings offline | `.ics` into Calendar.app | `.ics` opens in Outlook/Calendar app |
| WhatsApp send | Contacts + AppleScript | WhatsApp Desktop URI `whatsapp://send?phone=` (manual send) |
| Default browser | Arc | system default via `webbrowser` |

## Approach
1. Extract the above into a `platform/` package with `mac.py` and `win.py` exposing the same functions; `server.py` imports by `sys.platform`.
2. Keep every command regex and the router untouched.
3. Add `start.bat` (venv + both servers) and a Windows section in SETUP.md.
4. Test: extend the stubbed suites with a Windows adapter; manual smoke test on a Windows machine (none is available to us yet).

## Risks
Microphone permissions and audio device selection in browsers differ; `pycaw` needs Windows-only wheels; WhatsApp auto-send has no equivalent of AppleScript, so it would open the chat prefilled and need one click.

## Estimate
About 2 to 3 days of work plus testing on real hardware.
