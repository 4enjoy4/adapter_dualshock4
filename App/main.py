import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import time


def diagnose(seconds):
    import hid
    from adapter.controller import Controller
    from adapter.windows import GameGuard
    report = {'devices': [{key: d.get(key) for key in ('vendor_id', 'product_id', 'product_string', 'usage_page', 'usage', 'bus_type')}
                          for d in hid.enumerate(0x054C, 0)], 'reports': 0, 'seconds': seconds}
    controller = Controller()
    try:
        report['opened'] = controller.connect()
        latest = None
        end = time.monotonic() + seconds
        while controller.device and time.monotonic() < end:
            state, had_data = controller.read()
            if state:
                latest = state
                report['reports'] += 1
            if not had_data:
                time.sleep(.004)
        if latest:
            report.update(transport=latest.transport, battery=latest.battery,
                          sticks=[latest.lx, latest.ly, latest.rx, latest.ry],
                          buttons=sorted(latest.buttons))
        report['steam_library_count'] = len(GameGuard().roots)
        report['success'] = report['reports'] > 0
    except Exception as exc:
        report.update(success=False, error=str(exc))
    finally:
        controller.close()
    return report


def main():
    parser = argparse.ArgumentParser(description='DualShock 4 desktop adapter for Windows')
    parser.add_argument('--minimized', action='store_true')
    parser.add_argument('--diagnose', action='store_true', help='Read controller without generating input')
    parser.add_argument('--seconds', type=float, default=3)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--smoke-seconds', type=float, default=0, help='Run UI for a bounded integration test')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('This adapter runs on Windows 10/11.')
    from adapter import settings
    from adapter.windows import dpi_aware, single_instance, CloseHandle, FindWindowW, ShowWindow, SetForegroundWindow
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[
        RotatingFileHandler(settings.DATA_DIR / 'adapter.log', maxBytes=300000, backupCount=2, encoding='utf-8')])
    dpi_aware()
    if args.diagnose:
        report = diagnose(max(.1, min(60, args.seconds)))
        text = json.dumps(report, indent=2)
        if args.output:
            args.output.write_text(text, encoding='utf-8')
        if sys.stdout:
            print(text)
        return 0 if report['success'] else 1
    mutex, first = single_instance()
    if not first:
        hwnd = FindWindowW(None, 'DS4 Desktop Adapter')
        if hwnd:
            ShowWindow(hwnd, 9)
            SetForegroundWindow(hwnd)
        CloseHandle(mutex)
        return 0
    from adapter.service import Service
    from adapter.ui import App
    service = Service(settings.load())
    try:
        app = App(service, service.settings.copy(), args.minimized)
        service.start()
        if args.smoke_seconds:
            def finish():
                if args.output:
                    args.output.write_text(json.dumps(service.snapshot(), indent=2), encoding='utf-8')
                app.quit()
            app.root.after(int(args.smoke_seconds * 1000), finish)
        app.run()
    except Exception:
        logging.exception('Application stopped unexpectedly')
        raise
    finally:
        if service.is_alive():
            service.stop()
        CloseHandle(mutex)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
