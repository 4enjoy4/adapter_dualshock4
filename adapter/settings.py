import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'DS4DesktopAdapter'
DEFAULTS = {
    'pointer_speed': 1100.0,
    'touch_sensitivity': 1.25,
    'scroll_speed': 9.0,
    'deadzone': 0.18,
    'auto_fullscreen': True,
    'auto_steam_games': True,
    'game_apps': [],
    'desktop_apps': [],
    'mode': 'auto',
    'keyboard_type': 'adapter',
    'keyboard_size': 'compact',
    'keyboard_dock': 'bottom',
}


def validate(data):
    result = DEFAULTS.copy()
    for key, bounds in {'pointer_speed': (150, 3000), 'touch_sensitivity': (.2, 4),
                        'scroll_speed': (1, 25), 'deadzone': (.08, .4)}.items():
        value = data.get(key, result[key])
        if isinstance(value, (float, int)) and bounds[0] <= value <= bounds[1]:
            result[key] = float(value)
    for key in ('auto_fullscreen', 'auto_steam_games'):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    for key in ('game_apps', 'desktop_apps'):
        value = data.get(key, [])
        result[key] = sorted({s.lower() for s in value if isinstance(s, str) and s.endswith('.exe')}) if isinstance(value, list) else []
    if data.get('mode') in ('auto', 'gaming'):
        result['mode'] = data['mode']
    if data.get('keyboard_type') in ('adapter', 'windows'):
        result['keyboard_type'] = data['keyboard_type']
    for key, choices in {'keyboard_size': ('small','compact','large'), 'keyboard_dock': ('top','bottom')}.items():
        if data.get(key) in choices:
            result[key] = data[key]
    return result


def load():
    try:
        data = json.loads((DATA_DIR / 'settings.json').read_text(encoding='utf-8'))
        return validate(data if isinstance(data, dict) else {})
    except (OSError, ValueError):
        return validate({})


def save(settings):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = DATA_DIR / 'settings.tmp'
    temporary.write_text(json.dumps(validate(settings), indent=2), encoding='utf-8')
    temporary.replace(DATA_DIR / 'settings.json')
