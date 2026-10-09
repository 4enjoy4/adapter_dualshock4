"""Keyboard geometry and directional selection, independent of Windows/Tk."""
from dataclasses import dataclass, replace


@dataclass
class Selection:
    row: int = 1
    col: int = 1
    preferred_x: float | None = None


class KeyboardModel:
    def __init__(self, dual=False):
        self.shift = False
        self.caps = False
        self.language = 'EN'
        self.dual = dual
        self.active = 'left'
        self.cursors = {'left': Selection(), 'right': Selection(col=6)}

    @property
    def row(self):
        return self.cursors[self.active].row

    @property
    def col(self):
        return self.cursors[self.active].col

    def columns(self, row, side):
        count = len(self.rows()[row])
        if not self.dual:
            return list(range(count))
        split = 4 if row == 4 else 6
        return list(range(split) if side == 'left' else range(split, count))

    def select_at(self, row, col):
        if self.dual:
            self.active = 'left' if col in self.columns(row, 'left') else 'right'
        cursor = self.cursors[self.active]
        cursor.row, cursor.col, cursor.preferred_x = row, col, None

    def positions(self):
        sides = ('left', 'right') if self.dual else (self.active,)
        return {side: (self.cursors[side].row, self.cursors[side].col) for side in sides}

    def rows(self):
        letters = ('qwertyuiop[]\\', "asdfghjkl;'", 'zxcvbnm,./') if self.language == 'EN' else ('йцукенгшщзхъ', 'фывапролджэ', 'ячсмитьбю.')
        upper = self.shift != self.caps
        shifted = dict(zip("[]\\;',./", '{}|:"<>?'))
        def convert(c):
            return c.upper() if c.isalpha() and upper else shifted.get(c, c) if self.shift and not c.isalpha() else c
        digits = '~!@#$%^&*()_+' if self.shift else '`1234567890-='
        if self.language == 'RU':
            digits = ('Ё' if upper else 'ё') + digits[1:]
        return [
            [(c, ('text', c), 1) for c in digits] + [('⌫', ('key', (8,)), 1.8)],
            [('Tab', ('key', (9,)), 1.3)] + [(convert(c), ('text', convert(c)), 1) for c in letters[0]],
            [('Caps', ('caps', None), 1.4)] + [(convert(c), ('text', convert(c)), 1) for c in letters[1]] + [('Enter', ('key', (13,)), 1.6)],
            [('Shift', ('shift', None), 1.7)] + [(convert(c), ('text', convert(c)), 1) for c in letters[2]] + [('Shift', ('shift', None), 1.7)],
            [('EN/RU', ('language', None), 1.5), ('Ctrl+A', ('key', (17,65)), 1.3), ('Copy', ('key', (17,67)), 1.2), ('Paste', ('key', (17,86)), 1.2),
             ('Space', ('text',' '), 4), ('←', ('key',(37,)), 1), ('→', ('key',(39,)), 1), ('Del', ('key',(46,)), 1)],
        ]

    @staticmethod
    def centers(row):
        total, x, centers = sum(k[2] for k in row), 0, []
        for _, _, weight in row:
            centers.append((x + weight / 2) / total)
            x += weight
        return centers

    def move(self, direction, side=None):
        if side is not None:
            self.active = side
        cursor = replace(self.cursors[self.active])
        rows = self.rows()
        def available(row):
            return self.columns(row, self.active) if side is not None else list(range(len(rows[row])))
        columns = available(cursor.row)
        cursor.col = min(columns, key=lambda col: abs(col-cursor.col))
        if direction in ('left', 'right'):
            index = columns.index(cursor.col)
            cursor.col = columns[(index + (1 if direction == 'right' else -1)) % len(columns)]
            cursor.preferred_x = None
        else:
            if cursor.preferred_x is None:
                cursor.preferred_x = self.centers(rows[cursor.row])[cursor.col]
            cursor.row = max(0, min(len(rows) - 1, cursor.row + (1 if direction == 'down' else -1)))
            cursor.col = min(available(cursor.row),
                             key=lambda i: abs(self.centers(rows[cursor.row])[i] - cursor.preferred_x))
        if self.dual and side is None:
            self.active = 'left' if cursor.col in self.columns(cursor.row, 'left') else 'right'
        self.cursors[self.active] = cursor

    def selected(self, side=None):
        if side is not None:
            self.active = side
        cursor = self.cursors[self.active]
        rows = self.rows()
        cursor.col = min(self.columns(cursor.row, self.active), key=lambda col: abs(col-cursor.col))
        return rows[cursor.row][cursor.col][1]


def panel_geometry(work, scale, size='compact', dock='bottom'):
    """Stay inside the monitor work area, excluding the Windows taskbar."""
    left, top, right, bottom = work
    ww, hh = right-left, bottom-top
    factor = .83 if size == 'small' else 1.0 if size == 'compact' else 1.18
    width = min(round(760 * scale * factor), round(ww * .78))
    height = min(round(width * .32), round(hh * .36))
    gap = max(8, round(10 * scale))
    x = left + (ww-width)//2
    y = top+gap if dock == 'top' else bottom-height-gap
    return x, y, width, height
