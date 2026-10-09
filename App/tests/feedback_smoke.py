"""Send one short Enter pulse to the connected DS4, then verify input and stop."""
from pathlib import Path
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapter.controller import Controller
from adapter.feedback import Feedback

controller = Controller()
feedback = Feedback(controller.set_rumble)
result = {}
try:
    result['connected'] = controller.connect()
    if not result['connected']:
        raise RuntimeError('Connect the controller before this optional test.')
    result['transport'] = 'Bluetooth' if controller.bluetooth else 'USB'
    feedback.pulse('enter', time.monotonic(), .65)
    result['pulse_write_accepted'] = feedback.active and not feedback.failed
    reports = 0
    deadline = time.monotonic() + .5
    while time.monotonic() < deadline:
        sample, had_data = controller.read()
        reports += bool(sample)
        feedback.tick(time.monotonic())
        if not had_data:
            time.sleep(.005)
    result['stop_write_accepted'] = not feedback.active and not feedback.failed and not controller.rumble_active
    result['input_reports_after_pulse'] = reports
    result['success'] = result['pulse_write_accepted'] and result['stop_write_accepted'] and reports > 0
except Exception as exc:
    result.update(success=False,error=str(exc))
finally:
    feedback.stop()
    controller.close()
Path('feedback-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
raise SystemExit(0 if result.get('success') else 1)
