'''
The animation layout's (see *animatedLayouts*) settings, as the layout panel's
"animate" page shows them (see *layoutPanel*): the current's direction and the
relation type it follows, sliders for the most important numbers, and whether
a run ends by placing the labels. (The panel's top has the start/stop button
and what the layout's doing: see *statusText()*.)

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
"The sliders."

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
"Tooltips for the other controls (and the panel's start/stop button and status)."

def statusText(layout:Any) -> str:
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

class AnimationControls(ttk.Frame):
  '''
  The animation layout's settings, for a view: see the module doc. A row for
  each: its name, its control, and (for a slider) its value.
  '''
  def __init__(self, master:tk.Misc, view:SNGView):
    '''
    :param master: The widget it's in: the layout panel's page.
    :type master: tk.Misc
    :param view: The view whose animation layout it sets.
    :type view: SNGView
    '''
    super().__init__(master)
    self.view = view
    self._refreshing = False
    tip = lambda widgets, text: [CreateToolTip(w, text, wrapLength=300) for w in widgets]
    pad:dict[str, Any] = dict(padx=(0, 6), pady=3)
    self.columnconfigure(1, weight=1)
    row = 0

    label = ttk.Label(self, text="current")
    label.grid(row=row, column=0, sticky=tk.W, **pad)
    self.direction = tk.StringVar(self)
    self.directionBox = ttk.Combobox(self, textvariable=self.direction, state="readonly", width=12,
                                     values=["none", *FLOW_DIRECTIONS])
    self.directionBox.bind("<<ComboboxSelected>>", lambda _e: self._setDirection())
    self.directionBox.grid(row=row, column=1, columnspan=2, sticky=tk.W, **pad)
    tip([label, self.directionBox], TIPS["current"])
    row += 1

    label = ttk.Label(self, text="follows")
    label.grid(row=row, column=0, sticky=tk.W, **pad)
    self.relation = tk.StringVar(self)
    self.relationBox = ttk.Combobox(self, textvariable=self.relation, state="readonly", width=16,
                                    postcommand=self._relationNames)
    self.relationBox.bind("<<ComboboxSelected>>", lambda _e: self._setRelation())
    self.relationBox.grid(row=row, column=1, columnspan=2, sticky=tk.W, **pad)
    tip([label, self.relationBox], TIPS["follows"])
    row += 1

    self.sliders:dict[str, tuple[ttk.Scale, ttk.Label, str|Callable[[float], str]]] = {}
    for text, attr, lo, hi, fmt, tiptext in SLIDERS:
      label = ttk.Label(self, text=text)
      label.grid(row=row, column=0, sticky=tk.W, **pad)
      scale = ttk.Scale(self, from_=lo, to=hi, length=100, command=lambda v, a=attr: self._setSlider(a, float(v)))  # type: ignore[misc]
      scale.grid(row=row, column=1, sticky=tk.EW, **pad)
      value = ttk.Label(self, width=6)
      value.grid(row=row, column=2, sticky=tk.W, pady=3)
      self.sliders[attr] = (scale, value, fmt)
      tip([label, scale, value], tiptext)
      row += 1

    self.placeLabels = tk.BooleanVar(self, value=True)
    labels = ttk.Checkbutton(self, text="place labels", variable=self.placeLabels, command=self._setPlaceLabels)
    labels.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(8, 3))
    tip([labels], TIPS["labels"])
    row += 1

    reset = ttk.Button(self, text="Reset", width=6, command=self.reset)
    reset.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))
    tip([reset], TIPS["reset"])

    self.refresh()

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
    if not self._refreshing: # (not when refresh() itself sets the slider)
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

  # ---- layout -> controls ----------------------------------------------------

  def refresh(self) -> None:
    'Show the layout\'s settings (eg: changed from the menu).'
    layout = self.layout
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
