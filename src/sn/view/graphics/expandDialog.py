'''
"expand by relation...": choosing which of an object's relations to follow
when expanding it (see *VObject.expand()*), and how far.

The choices are the relation types the object's relations are of, each way
round -- "has-mother ->" (its mother) is not "<- has-mother" (its children)
-- with how many of each there are; a symmetric type (eg: has-sibling) once,
both ways. A type includes its subtypes (has-parent follows has-father and
has-mother too), and a type that two or more of the types are kinds of is a
choice too (eg: has-parent, when there are has-father and has-mother). Or:
all of them, all outgoing, or all incoming -- which, unlike the types, follow
any relation (that way) at every step, not just the types this object has.

Relations in a hidden or erased category (see *SNGView.visibility()*: eg: isa
links, often hidden) are choices too, greyed and marked "hidden": ticked, they
and what they lead to are shown anyway (see *VObject.expand()*) -- they were
asked for by name. "All", "all outgoing" and "all incoming" leave them hidden.

Created on Oct 10, 2026

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
from dataclasses import dataclass
from typing import Any, Callable
import tkinter as tk
from tkinter import ttk
from util.utils import ownDialog
from sn.model.model import GraphObject, Relation, IsaIndividual

OUT, IN, BOTH = "out", "in", "both"
"Which way round a relation is, from the object it's attached to (*BOTH*: symmetric)."

ARROWS = {OUT: "{} →", IN: "← {}", BOTH: "{} ↔"}
"How a choice is labelled, by direction: eg: \"has-mother ->\"."

MAX_LEVELS = 20
"The most levels the dialog offers."

@dataclass
class Choice:
  '''
  One way of following relations: those of type *type* (or a subtype), going
  *direction* (out from the object, in to it, or -- symmetric -- both).
  '''
  type:Relation
  direction:str
  count:int = 0
  "How many of the object's relations it follows."
  hidden:int = 0
  "How many of those are in a hidden or erased category (or lead to something that is)."

  def label(self) -> str:
    what = ARROWS[self.direction].format(self.type.name or "?")
    if self.hidden == 0:
      return f"{what} ({self.count})"
    if self.hidden == self.count:
      return f"{what} ({self.count}, hidden)"
    return f"{what} ({self.count}; {self.hidden} hidden)"

def _types(rel:Relation) -> list[Relation]:
  '''
  :returns: *rel*'s own types (an isa link's is isa).
  :rtype: list[Relation]
  '''
  if isinstance(rel, IsaIndividual):
    return [rel.model.ISA]
  return [t for t in rel.getParents() if isinstance(t, Relation)]

def _direction(rel:Relation, mo:GraphObject) -> str:
  '''
  :returns: Which way *rel* goes from *mo*: *OUT*, *IN*, or *BOTH* (symmetric).
  :rtype: str
  '''
  try:
    if not isinstance(rel, IsaIndividual) and rel.isSymmetric():
      return BOTH
  except Exception:
    pass
  return OUT if rel.localSrc is mo else IN

def follows(rel:Relation, mo:GraphObject, typ:Relation, direction:str) -> bool:
  '''
  :returns: Whether *rel*, attached to *mo*, is of *typ* (or a subtype) and goes *direction* from it.
  :rtype: bool
  '''
  d = _direction(rel, mo)
  return (d == direction or d == BOTH or direction == BOTH) and any(t is typ or t.isa(typ) for t in _types(rel))

def relationChoices(mo:GraphObject, rels:list[Relation], hidden:Callable[[Relation], bool]=lambda _r: False) -> list[Choice]:
  '''
  :param mo: The object being expanded.
  :type mo: GraphObject
  :param rels: Its relations (eg: those the view would follow: see *VObject.expandableRelations()*).
  :type rels: list[Relation]
  :param hidden: Whether a relation is in a hidden or erased category, or leads to something that is (see *Choice.hidden*).
  :type hidden: Callable[[Relation], bool]
  :returns: The choices for "expand by relation...": each type and way round
    that *rels* are, and each type that two or more of those types (the same
    way round) are kinds of -- but not the system's *relation* -- with how
    many of *rels* each follows; by name.
  :rtype: list[Choice]
  '''
  model = mo.model
  top = {id(getattr(model, "RELATION", None)), id(getattr(model, "TOP", None))}
  direct:dict[tuple[int, str], Choice] = {}
  for r in rels:
    d = _direction(r, mo)
    for t in _types(r):
      direct.setdefault((id(t), d), Choice(t, d))
  # supertypes shared by two or more of them (the same way round)
  shared:dict[tuple[int, str], Choice] = {}
  for (_, d), c in direct.items():
    for s in c.type.getSupers():
      if isinstance(s, Relation) and id(s) not in top and (id(s), d) not in direct:
        under = [o for (_, d2), o in direct.items() if d2 == d and (o.type is s or o.type.isa(s))]
        if len({id(o.type) for o in under}) >= 2:
          shared.setdefault((id(s), d), Choice(s, d))
  ret = list(direct.values()) + list(shared.values())
  for c in ret:
    mine = [r for r in rels if follows(r, mo, c.type, c.direction)]
    c.count, c.hidden = len(mine), sum(1 for r in mine if hidden(r))
  return sorted(ret, key=lambda c: (c.type.name or "", [OUT, BOTH, IN].index(c.direction)))

def choiceFilter(mode:str, chosen:list[Choice]) -> Callable[[Any, Relation], bool]:
  '''
  :param mode: "all", "all outgoing", "all incoming", or "chosen".
  :type mode: str
  :param chosen: For "chosen": the choices to follow.
  :type chosen: list[Choice]
  :returns: A filter for *VObject.expand()*: whether to follow a relation
    from the object being expanded (at each step: the same choices again).
    For "chosen", it has a true "showsHidden": the types were asked for by
    name, so they're followed, and shown, even in a hidden category.
  :rtype: Callable[[Any, Relation], bool]
  '''
  def f(vo:Any, rel:Relation) -> bool:
    mo = vo.modelObject
    if mo is None:
      return False
    if mode == "all":
      return True
    if mode in ("all outgoing", "all incoming"):
      d = _direction(rel, mo)
      return d == BOTH or d == (OUT if mode == "all outgoing" else IN)
    return any(follows(rel, mo, c.type, c.direction) for c in chosen)
  f.showsHidden = mode == "chosen" #type: ignore[attr-defined]
  return f

class ExpandDialog(tk.Toplevel):
  '''
  The "expand by relation..." dialog: which relations to follow (see
  *relationChoices()*), and how many levels. Modal; *result* is (filter,
  levels) if OK'd (see *choiceFilter()*), else None.
  '''
  def __init__(self, parent:tk.Misc, title:str, choices:list[Choice], levels:int=1):
    '''
    :param parent:
    :type parent: tk.Misc
    :param title:
    :type title: str
    :param choices:
    :type choices: list[Choice]
    :param levels: The levels to start with.
    :type levels: int
    '''
    super().__init__(parent)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.parent = parent
    self.title(title)
    self.choices = choices
    self.result:tuple[Callable[[Any, Relation], bool], int]|None = None
    self.mode = tk.StringVar(value="chosen" if choices else "all")
    self.checks:list[tk.BooleanVar] = [tk.BooleanVar(value=False) for _ in choices]
    self.levels = tk.IntVar(value=levels)
    pad:dict[str, Any] = dict(padx=10, pady=2)
    frame = ttk.Frame(self, padding=8)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text="Follow:").grid(row=0, column=0, sticky=tk.W, **pad)
    row = 1
    for value, text in (("all", "all relations"), ("all outgoing", "all outgoing relations"), ("all incoming", "all incoming relations"),
                        ("chosen", "these:")):
      ttk.Radiobutton(frame, text=text, value=value, variable=self.mode).grid(row=row, column=0, columnspan=2, sticky=tk.W, **pad)
      row += 1
    style = ttk.Style(self)
    style.configure("Hidden.TCheckbutton", foreground="gray50") # (in a hidden category: see Choice.hidden)
    for c, var in zip(choices, self.checks):
      ttk.Checkbutton(frame, text=c.label(), variable=var, command=lambda: self.mode.set("chosen"),
                      style="Hidden.TCheckbutton" if c.hidden == c.count and c.count else "TCheckbutton") \
        .grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=(36, 10), pady=1)
      row += 1
    if not choices:
      ttk.Label(frame, text="(it has no relations)", foreground="gray50").grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=(36, 10))
      row += 1
    ttk.Separator(frame).grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=6)
    row += 1
    ttk.Label(frame, text="Levels:").grid(row=row, column=0, sticky=tk.W, **pad)
    ttk.Spinbox(frame, from_=1, to=MAX_LEVELS, textvariable=self.levels, width=4).grid(row=row, column=1, sticky=tk.W, **pad)
    row += 1
    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=10)
    ttk.Button(buttons, text="Expand", command=self.ok, default="active").pack(side=tk.RIGHT, padx=10)
    self.bind("<Return>", lambda _e: self.ok())
    self.bind("<KP_Enter>", lambda _e: self.ok())
    self.bind("<Escape>", lambda _e: self.destroy())
    self.protocol("WM_DELETE_WINDOW", self.destroy)
    self.resizable(False, False)

  def ok(self) -> None:
    '''
    Expand (the dialog's result), unless "these" is chosen and none of them are.
    '''
    mode = self.mode.get()
    chosen = [c for c, v in zip(self.choices, self.checks) if v.get()]
    if mode == "chosen" and not chosen:
      self.bell()
      return
    try:
      levels = max(1, min(MAX_LEVELS, int(self.levels.get())))
    except (tk.TclError, ValueError):
      self.bell()
      return
    self.result = (choiceFilter(mode, chosen), levels)
    self.destroy()

  def show(self) -> tuple[Callable[[Any, Relation], bool], int]|None:
    '''
    Show it (over its parent's window, in front), and wait for an answer.

    :returns: *result*.
    :rtype: tuple[Callable[[Any, Relation], bool], int] | None
    '''
    self.update_idletasks()
    top = self.parent.winfo_toplevel()
    if top.winfo_viewable():
      w, h = self.winfo_reqwidth(), self.winfo_reqheight()
      x = top.winfo_rootx() + max(0, (top.winfo_width() - w) // 2)
      y = top.winfo_rooty() + max(0, (top.winfo_height() - h) // 3)
      self.geometry(f"+{x}+{y}")
    try:
      self.wait_visibility()
      self.grab_set()
      self.lift()
      self.focus_force()
    except tk.TclError:
      pass
    self.wait_window()
    return self.result
