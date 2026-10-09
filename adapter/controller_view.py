"""Controller-first guide using Sony's real DS4 product photograph."""
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageTk

BG, CARD, TEXT, MUTED = '#0b1423', '#142238', '#edf4ff', '#99aecb'


class ControllerView(tk.Canvas):
    def __init__(self, parent, scale):
        super().__init__(parent, bg=BG, highlightthickness=0, height=390*scale)
        self.mode, self.buttons = 'Desktop', frozenset()
        self.source = Image.open(Path(__file__).resolve().parents[1] / 'assets' / 'dualshock4-front.png')
        self.photo, self.photo_size = None, None
        self.bind('<Configure>', lambda event: self.draw())

    def update_state(self, mode=None, buttons=None):
        mode = mode or self.mode
        buttons = self.buttons if buttons is None else frozenset(buttons)
        if (mode, buttons) != (self.mode, self.buttons):
            self.mode, self.buttons = mode, buttons
            self.draw()

    def draw(self):
        self.delete('all')
        s = min(self.winfo_width()/1000, self.winfo_height()/390)
        if s <= .05:
            return
        def box(x,y,w,h,color):
            self.create_rectangle(x*s,y*s,(x+w)*s,(y+h)*s,fill=color,outline='')
        def text(x,y,value,size=12,color=TEXT,anchor='w',bold=False):
            self.create_text(x*s,y*s,text=value,anchor=anchor,fill=color,
                             font=('Segoe UI Semibold' if bold else 'Segoe UI',-round(size*s)))
        box(0,0,620,300,'#ffffff')
        size = (round(620*s),round(349*s))
        if size != self.photo_size:
            self.photo = ImageTk.PhotoImage(self.source.resize(size,Image.Resampling.LANCZOS))
            self.photo_size = size
        self.create_image(0,-20*s,image=self.photo,anchor='nw')
        box(0,308,620,21,BG)
        # Photo coordinates are from the unmodified 1200 x 675 front view.
        points = {'triangle':(832,177),'circle':(884,232),'cross':(832,287),
                  'square':(777,232),'share':(455,160),'options':(752,159),
                  'l3':(486,334),'r3':(719,334),'touch_click':(606,187),
                  'up':(377,193),'down':(377,270),'left':(338,231),'right':(416,231)}
        for button in self.buttons:
            if button in points:
                x,y = points[button]
                x,y = x*620/1200*s,(y*620/1200-20)*s
                r = 17*s
                self.create_oval(x-r,y-r,x+r,y+r,outline='#1682e8',width=max(2,3*s))
        box(0,281,620,27,'#ffffff')
        text(18,292,'DUALSHOCK 4',10,'#44566e',bold=True)
        text(600,292,'LIVE BUTTON VIEW',9,'#66809a',anchor='e')
        box(638,0,362,308,CARD)
        text(659,26,{'Desktop':'YOUR DESKTOP, ON A CONTROLLER','Keyboard':'TYPE WITHOUT THE TOUCHPAD','Shortcuts':'HOLD SHARE + PRESS'}[self.mode],11,'#80c7ff',bold=True)
        text(659,51,{'Desktop':'X selects. Circle goes back.','Keyboard':'Move to a key. Press X to type.','Shortcuts':'Everyday shortcuts, in familiar places.'}[self.mode],12)
        labels = {'Desktop':['Keyboard','Back / Esc','Click / hold','Backspace'],
                  'Keyboard':['Space','Close keyboard','Type key','Backspace'],
                  'Shortcuts':['Paste','Cut','Select all','Copy']}[self.mode]
        for (name,glyph,x,y,color), label in zip([
            ('triangle','△',819,98,'#64dbbd'),('circle','○',923,171,'#ff8596'),
            ('cross','×',819,232,'#81b9ff'),('square','□',715,171,'#e99edf')],labels):
            r=23
            self.create_oval((x-r)*s,(y-r)*s,(x+r)*s,(y+r)*s,fill='#294460' if name in self.buttons else '#0b1423',outline=color,width=2*s)
            text(x,y,glyph,30,color,'center')
            text(x,y+37,label,11,TEXT,'center',True)
        facts = {
            'Desktop':[('POINT & SCROLL','Right stick / touchpad · pointer','Left stick · scroll'),('CLICK & NAVIGATE','X / R2 · click     L2 · right click','D-pad · arrows     L1 / R1 · tabs'),('OPEN THE KEYBOARD','Options / Triangle · keyboard','Share + Options · hold to pause')],
            'Keyboard':[('MOVE BETWEEN KEYS','D-pad / left stick · selection','X · type selected key'),('FAST TYPING','L1 · Shift     R1 · Enter','Square · delete     Triangle · space'),('KEEP YOUR SPACE','Drag the header to move','Size / Top-bottom · fit your screen')],
            'Shortcuts':[('EDIT TEXT','Share + Square · Ctrl+C','Share + Triangle · Ctrl+V'),('SELECT & CUT','Share + X · Ctrl+A','Share + Circle · Ctrl+X'),('UNDO & SWITCH TABS','Share + L1 / R1 · undo / redo','Share + ← / → · previous / next tab')],
        }[self.mode]
        for i,(title,line1,line2) in enumerate(facts):
            x=i*339
            box(x,321,322,69,CARD)
            text(x+13,337,title,10,'#80c7ff',bold=True)
            text(x+13,357,line1,11)
            text(x+13,375,line2,11,MUTED)
