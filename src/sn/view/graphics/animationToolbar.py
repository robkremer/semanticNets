'''
The animation toolbar: a strip across the top of a view's window with the
animation layout's (see *animatedLayouts*) controls -- a start/stop button and
the most important settings -- so it can be watched and adjusted as it runs,
without going through the menus. Shown and hidden with "View | Animation
toolbar" (see *SNGView.toggleAnimationToolbar()*).

Settings take effect at once, even while it's running: the layout reads them
at every step.

Created on Oct 1, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
#################################################################################
# (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
#                                                                               #
# Permission is hereby granted, free of charge, to any person obtaining a copy  #
# of this software and associated documentation files (the "Software"), to deal #
# in the Software without restriction, including without limitation the rights  #
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     #
# copies of the Software, and to permit persons to whom the Software is         #
# furnished to do so, subject to the following conditions:                      #
#                                                                               #
# The above copyright notice and this permission notice shall be included in all#
# copies or substantial portions of the Software.                               #
#                                                                               #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE #
# SOFTWARE.                                                                     #
#################################################################################
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from math import log10
from typing import Any, Callable, TYPE_CHECKING
from sn.model.model import Relation
from sn.view.graphics.animatedLayouts import FLOW_DIRECTIONS
from util.tooltip import CreateToolTip
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

DEFAULTS:dict[str, float] = {"flowStrength": 6.0, "e": 1000.0, "k": 0.005, "heat": 6.0, "cooling": 0.7, "leaps": 0.05}
"The settings *Reset* puts back (the animation layout's own defaults)."

def coolingLoss(cooling:float) -> str:
  '''
  :param cooling: The layout's *cooling*: what the temperature is multiplied by at each cool-down.
  :type cooling: float
  :returns: How it's shown: the share of the temperature lost, eg: "30%".
  :rtype: str
  '''
  return f"{(1.0 - cooling) * 100:.2g}%"

SCALED:dict[str, tuple[Callable[[float], float], Callable[[float], float]]] = {
  # (layout attribute: (its value -> the slider's position, the slider's position -> its value))
  "cooling": (lambda c: log10(max(1e-6, 1.0 - c)), lambda pos: round(1.0 - 10.0 ** pos, 6)),
}
'''
The sliders that aren't the layout's attribute itself. *cooling* is on a log
scale of the share of the temperature lost at each cool-down -- from 50%
down to 0.1%, where a run goes on for half an hour or more.
'''

SLIDERS:list[tuple[str, str, float, float, str|Callable[[float], str], str]] = [
  # (label, layout attribute, from, to (the slider's: see SCALED), value format, tooltip)
  ("strength",  "flowStrength", 0.0,    15.0,  "{:.1f}",
   "How hard the current pulls things into their layers (the most it moves an object in a step)."),
  ("repulsion", "e",            100.0,  3000.0, "{:.0f}",
   "How strongly objects push one another apart, like similarly charged particles (measured between their edges)."),
  ("springs",   "k",            0.0005, 0.02,  "{:.4f}",
   "How stiff relations are: how strongly they pull the objects they connect together, like elastic bands."),
  ("heat",      "heat",         0.0,    15.0,  "{:.1f}",
   "With a current: random jiggling, which fades as the layout settles. It shakes the layout out of dead ends "
   "(eg: a tree pointing against the current). More heat: livelier, but slower to settle."),
  ("cooling",   "cooling",      log10(0.001), log10(0.5), coolingLoss,
   "How fast it cools: how much of the temperature (T) it loses each time it stops making progress. "
   "Slide it left for a run that goes on a long time -- down at 0.1%, with a current, an hour or so -- "
   "exploring for a better layout; right, to settle sooner."),
  ("leaps",     "leaps",        0.0,    0.2,   lambda v: f"{v * 100:.0f}%",
   "The chance, in a step, of a leap: like a mutation, an object picked at random (likeliest one with a long "
   "relation, eg: stuck behind a wall of other objects) is thrown somewhere else entirely -- across the graph, "
   "or out into the space around it -- and pulled back in by another way, upsetting what it's related to as it "
   "comes. It gets the layout out of dead ends. It fades as the layout cools, and stops near the end, but "
   "the last leaps may be left out of place (run again with 0%, or move them). 0% for none."),
]
"The toolbar's sliders."

TIPS:dict[str, str] = {
  "play": "Start the animation layout (or stop it). A whole run is one undo.",
  "status": "What the animation layout is doing: arranging (the current puts things into layers), settling "
            "(cooling down until nothing moves much), straightening (the layers' lines), or stopped. "
            "T is the temperature: how far things may move in a step, falling as it settles. "
            "Leaps: how many objects have leapt this run (see leaps).",
  "current": "A current across the workspace (or none): it lines up the relations it follows -- their "
             "destinations upstream of their sources -- in layers. Eg: isa, flowing down: a class diagram, "
             "superclasses above their subclasses.",
  "follows": "The relation type the current lines up (by default, isa).",
  "reset": "Put the sliders back to their defaults.",
  "labels": "Whether a run ends by finding free places for the relations' labels -- which can take a while in "
            "a crowded view. Turn it off while starting run after run; turning it on (between runs) places "
            "them straight away.",
}
"Tooltips for the toolbar's other controls."

class AnimationToolbar(ttk.Frame):
  '''
  The animation toolbar for a view: see the module doc.
  '''
  PADDING = 4
  "The toolbar's padding (pixels) at its left and right."
  POLL_MS = 250
  "How often (ms) the toolbar shows the layout's state (and any settings changed elsewhere, eg: the menu)."

  def __init__(self, master:tk.Misc, view:SNGView):
    '''
    :param master: The widget it's in: the view's window.
    :type master: tk.Misc
    :param view: The view whose animation layout it controls.
    :type view: SNGView
    '''
    super().__init__(master, padding=(self.PADDING, 2))
    self.view = view
    self._polling = False
    self._refreshing = False
    self._rows:list[list[ttk.Frame]] = []
    self._rowHeights:list[int] = []
    self.groups:list[ttk.Frame] = []
    "The toolbar's groups of controls, in order: laid out in rows, as many as fit across (see *_reflow()*)."
    tip = lambda widgets, text: [CreateToolTip(w, text, wrapLength=300) for w in widgets]

    g = self._group()
    self.playButton = ttk.Button(g, width=7, command=self.view.toggleAnimationLayout)
    self.playButton.pack(side=tk.LEFT)
    self.status = ttk.Label(g, width=30, foreground="gray35")
    self.status.pack(side=tk.LEFT, padx=(4, 0))
    tip([self.playButton], TIPS["play"]); tip([self.status], TIPS["status"])

    g = self._group()
    label = ttk.Label(g, text="current")
    label.pack(side=tk.LEFT)
    self.direction = tk.StringVar(self)
    self.directionBox = ttk.Combobox(g, textvariable=self.direction, state="readonly", width=9,
                                     values=["none", *FLOW_DIRECTIONS])
    self.directionBox.bind("<<ComboboxSelected>>", lambda _e: self._setDirection())
    self.directionBox.pack(side=tk.LEFT, padx=(3, 0))
    tip([label, self.directionBox], TIPS["current"])

    g = self._group()
    label = ttk.Label(g, text="follows")
    label.pack(side=tk.LEFT)
    self.relation = tk.StringVar(self)
    self.relationBox = ttk.Combobox(g, textvariable=self.relation, state="readonly", width=10,
                                    postcommand=self._relationNames)
    self.relationBox.bind("<<ComboboxSelected>>", lambda _e: self._setRelation())
    self.relationBox.pack(side=tk.LEFT, padx=(3, 0))
    tip([label, self.relationBox], TIPS["follows"])

    self.sliders:dict[str, tuple[ttk.Scale, ttk.Label, str|Callable[[float], str]]] = {}
    for text, attr, lo, hi, fmt, tiptext in SLIDERS:
      g = self._group()
      label = ttk.Label(g, text=text)
      label.pack(side=tk.LEFT)
      scale = ttk.Scale(g, from_=lo, to=hi, length=70, command=lambda v, a=attr: self._setSlider(a, float(v)))  # type: ignore[misc]
      scale.pack(side=tk.LEFT, padx=(3, 0))
      value = ttk.Label(g, width=6)
      value.pack(side=tk.LEFT, padx=(2, 0))
      self.sliders[attr] = (scale, value, fmt)
      tip([label, scale, value], tiptext)

    g = self._group()
    self.placeLabels = tk.BooleanVar(self, value=True)
    labels = ttk.Checkbutton(g, text="place labels", variable=self.placeLabels, command=self._setPlaceLabels)
    labels.pack(side=tk.LEFT)
    tip([labels], TIPS["labels"])

    g = self._group()
    reset = ttk.Button(g, text="Reset", width=6, command=self.reset)
    reset.pack(side=tk.LEFT)
    tip([reset], TIPS["reset"])

    self.bind("<Configure>", lambda _e: self._reflow())
    self.refresh()
    self._reflow()

  def _group(self) -> ttk.Frame:
    '''
    :returns: A new group of controls, at the end of the toolbar.
    :rtype: ttk.Frame
    '''
    g = ttk.Frame(self)
    self.groups.append(g)
    return g

  def _reflow(self) -> None:
    '''
    Lay the groups out in rows: left to right, starting a new row whenever the
    next one wouldn't fit in the width there is -- so it's one row in a wide
    window, and more in a narrow one.
    '''
    width = self.winfo_width()
    if width <= 1: # (not shown yet: the window's width)
      width = self.master.winfo_width()
    width -= 2 * self.PADDING # (the room inside the toolbar's padding)
    gap = 10
    rows:list[list[ttk.Frame]] = [[]]
    used = 0
    for g in self.groups:
      w = g.winfo_reqwidth()
      if rows[-1] and used + gap + w > width:
        rows.append([])
        used = 0
      used += (gap if rows[-1] else 0) + w
      rows[-1].append(g)
    heights = [max(g.winfo_reqheight() for g in row) for row in rows]
    # (the heights too: before the toolbar is first shown, its groups don't know theirs yet -- 1 --
    # and the toolbar's own height would stay that small)
    if rows == self._rows and heights == self._rowHeights:
      return
    self._rows, self._rowHeights = rows, heights
    # (placed by hand: each row on its own, left to right -- grid would line the rows' columns up)
    y = 0
    for row, height in zip(rows, heights):
      x = 0
      for g in row:
        g.place(x=x, y=y + (height - g.winfo_reqheight()) // 2)
        x += g.winfo_reqwidth() + gap
      y += height + 2
    self.configure(height=y + 4)

  @property
  def layout(self) -> Any:
    '''
    :returns: The view's animation layout.
    :rtype: FieldsLayout_threaded
    '''
    return self.view.animationLayout()

  # ---- settings -> layout ----------------------------------------------------

  def _setDirection(self) -> None:
    'The current\'s direction was chosen.'
    d = self.direction.get()
    self.view.setAnimationSetting("flowDirection", None if d == "none" else d)

  def _relationTypes(self) -> list[Relation]:
    '''
    :returns: The relation types the current can follow: "isa" first, then the
      model's own and its super-models' (eg: an ontology's), by name (see
      *layout.relationTypes()*).
    :rtype: list[Relation]
    '''
    from sn.view.graphics.layout import relationTypes
    return relationTypes(self.view.model)

  def _relationNames(self) -> None:
    'Fill the "follows" list (just before it drops down: the model may have changed).'
    self.relationBox.configure(values=[r.name for r in self._relationTypes()])

  def _setRelation(self) -> None:
    'The relation type the current follows was chosen.'
    name = self.relation.get()
    t = next((r for r in self._relationTypes() if r.name == name), None)
    self.view.setAnimationSetting("flowRelation", None if t is None or t is self.view.model.ISA else t)

  def _setSlider(self, attr:str, value:float) -> None:
    '''
    A slider was moved.

    :param attr: The layout's attribute it sets.
    :type attr: str
    :param value: Its new position (the layout's value, but see *SCALED*).
    :type value: float
    '''
    if attr in SCALED:
      value = SCALED[attr][1](value)
    if not self._refreshing: # (not when the toolbar itself sets the slider: see refresh())
      self.view.setAnimationSetting(attr, value)
    _scale, label, fmt = self.sliders[attr]
    label.configure(text=self._format(fmt, value))

  @staticmethod
  def _format(fmt:str|Callable[[float], str], value:float) -> str:
    '''
    :param fmt: A slider's value format (see *SLIDERS*).
    :type fmt: str|Callable[[float], str]
    :param value: The layout's value.
    :type value: float
    :returns: The value, as the slider shows it.
    :rtype: str
    '''
    return fmt(value) if callable(fmt) else fmt.format(value)

  def _setPlaceLabels(self) -> None:
    '''
    "place labels" was checked or unchecked. Checked between runs, the labels
    are placed straight away; during a run, the end of the run places them.
    '''
    on = self.placeLabels.get()
    self.view.setAnimationSetting("placeLabels", on)
    if on and not self.layout.active:
      self.layout.settleLabels()

  def reset(self) -> None:
    'Put the sliders\' settings back to their defaults.'
    for attr, value in DEFAULTS.items():
      self.view.setAnimationSetting(attr, value)
    self.refresh()

  # ---- layout -> toolbar -----------------------------------------------------

  def refresh(self) -> None:
    'Show the layout\'s state and settings (eg: changed from the menu, or by the run ending).'
    layout = self.layout
    self.playButton.configure(text="■ Stop" if layout.active else "▶ Start")
    self.status.configure(text=self._statusText(layout))
    d = layout.flowDirection or "none"
    if self.direction.get() != d:
      self.direction.set(d)
    r = (layout.flowRelation or self.view.model.ISA).name
    if self.relation.get() != r:
      self.relation.set(r)
    if self.placeLabels.get() != layout.placeLabels:
      self.placeLabels.set(layout.placeLabels)
    self._refreshing = True # (a ttk scale calls its command when it's set, too)
    try:
      for attr, (scale, label, fmt) in self.sliders.items():
        v = float(getattr(layout, attr))
        pos = SCALED[attr][0](v) if attr in SCALED else v
        if abs(float(scale.get()) - pos) > 1e-9:
          scale.set(pos)
        label.configure(text=self._format(fmt, v))
    finally:
      self._refreshing = False

  @staticmethod
  def _statusText(layout:Any) -> str:
    '''
    :param layout: The animation layout.
    :type layout: FieldsLayout_threaded
    :returns: What it's doing, eg: "running: settling (T=0.49)".
    :rtype: str
    '''
    if not layout.active:
      return "stopped"
    if getattr(layout, "_straightening", 0) > 0:
      phase = "straightening"
    elif layout.flowDirection in FLOW_DIRECTIONS and not getattr(layout, "_arranged", True):
      phase = "arranging"
    else:
      phase = "settling"
    leaps = getattr(layout, "leapCount", 0)
    return f"running: {phase} (T={layout.temperature:.2f})" + (f", {leaps} leaps" if leaps else "")

  def startPolling(self) -> None:
    'Keep the toolbar up to date while it\'s shown (see *POLL_MS*).'
    if not self._polling:
      self._polling = True
      self._poll()

  def stopPolling(self) -> None:
    'Stop keeping the toolbar up to date (it\'s hidden).'
    self._polling = False

  def _poll(self) -> None:
    if not self._polling or not self.winfo_exists():
      self._polling = False
      return
    try:
      self.refresh()
    finally:
      self.after(self.POLL_MS, self._poll)
