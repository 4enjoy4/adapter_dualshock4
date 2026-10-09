"""Keyboard geometry and directional selection, independent of Windows/Tk."""
class KeyboardModel:
    def __init__(self):
        self.shift = False
        self.caps = False
        self.language = 'EN'
        self.row, self.col = 1, 1
        self.preferred_x = None

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

    def move(self, direction):
        rows = self.rows()
        self.col = min(self.col, len(rows[self.row]) - 1)
        if direction in ('left', 'right'):
            self.col = (self.col + (1 if direction == 'right' else -1)) % len(rows[self.row])
            self.preferred_x = None
        else:
            if self.preferred_x is None:
                self.preferred_x = self.centers(rows[self.row])[self.col]
            self.row = max(0, min(len(rows) - 1, self.row + (1 if direction == 'down' else -1)))
            self.col = min(range(len(rows[self.row])), key=lambda i: abs(self.centers(rows[self.row])[i] - self.preferred_x))

    def selected(self):
        rows = self.rows()
        self.col = min(self.col, len(rows[self.row]) - 1)
        return rows[self.row][self.col][1]


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
