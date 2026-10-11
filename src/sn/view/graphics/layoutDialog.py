'''
The dialog that asks for a layout heuristic's parameters (see
*layout.LayoutHeuristic.askParameters()*): made from its *PARAMETERS* (see
*layout.LayoutParameter*) -- a relation type, a choice, a number, or a
yes/no -- with OK and Cancel.

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
from functools import partial
from typing import Any
import tkinter as tk
from tkinter import ttk, messagebox
from sn.view.graphics.layout import LayoutParameter, relationTypes

MAX_INT = 10000
"The biggest number the dialog's number fields take."

class LayoutDialog(tk.Toplevel):
  '''
  Asks for some of a layout heuristic's parameters. Modal; *result* is all
  of its parameters' values (as keyword arguments for its constructor: a
  relation as a *Relation*) if OK'd, else None.
  '''
  def __init__(self, parent:tk.Misc, title:str, cls:Any, asked:list[LayoutParameter], values:dict[str, Any], view:Any):
    '''
    :param parent: The window it's over.
    :type parent: tk.Misc
    :param title:
    :type title: str
    :param cls: The layout heuristic's class (see *LayoutHeuristic.parameterChanged()*).
    :type cls: type[LayoutHeuristic]
    :param asked: The parameters to ask for.
    :type asked: list[LayoutParameter]
    :param values: All its parameters' values to start with (a relation as a *Relation* or its name).
    :type values: dict[str, Any]
    :param view: The view it's for: its model's relation types are the choices for a relation.
    :type view: SNGView
    '''
    super().__init__(parent)
    self.title(title)
    self.cls, self.view, self.asked = cls, view, asked
    self.values:dict[str, Any] = dict(values)
    self.result:dict[str, Any]|None = None
    self.relations = {str(r.name): r for r in relationTypes(view.model)}
    self.vars:dict[str, tk.Variable] = {}
    pad:dict[str, Any] = dict(padx=8, pady=3)
    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    row = 0
    for p in asked:
      v = self.values.get(p.name)
      if p.kind == "bool":
        var:tk.Variable = tk.BooleanVar(value=bool(v))
        ttk.Checkbutton(frame, text=p.label, variable=var, command=partial(self.changed, p.name)) \
          .grid(row=row, column=0, columnspan=2, sticky=tk.W, **pad)
      else:
        ttk.Label(frame, text=p.label + ":").grid(row=row, column=0, sticky=tk.W, **pad)
        if p.kind == "relation":
          var = tk.StringVar(value=str(getattr(v, "name", v) or ""))
          w:tk.Widget = ttk.Combobox(frame, textvariable=var, values=list(self.relations), state="readonly", width=28)
          w.bind("<<ComboboxSelected>>", partial(self._selected, p.name))
        elif p.kind == "choice":
          var = tk.StringVar(value=str(v))
          w = ttk.Combobox(frame, textvariable=var, values=list(p.choices), state="readonly", width=28)
          w.bind("<<ComboboxSelected>>", partial(self._selected, p.name))
        else: # int
          var = tk.StringVar(value=str(v))
          w = ttk.Spinbox(frame, from_=0, to=MAX_INT, textvariable=var, width=8)
        w.grid(row=row, column=1, sticky=tk.W, **pad)
      self.vars[p.name] = var
      row += 1
      if p.note:
        ttk.Label(frame, text=p.note, foreground="gray40", wraplength=360).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=24)
        row += 1
    buttons = ttk.Frame(frame)
    buttons.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=(10, 0))
    ttk.Button(buttons, text="OK", command=self.ok, default="active").pack(side=tk.RIGHT, padx=6)
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=6)
    self.bind("<Return>", lambda _e: self.ok())
    self.bind("<Escape>", lambda _e: self.destroy())
    self.transient(parent) #type: ignore[call-overload] # (a window)
    self.update_idletasks()
    try:
      self.grab_set()
    except tk.TclError: # (not viewable yet)
      pass
    self.focus_force()
    self.wait_window()

  def read(self) -> dict[str, Any]|None:
    '''
    :returns: All the parameters' values, with those asked for as shown -- or
      None (having said why) if a number isn't one.
    :rtype: dict[str, Any] | None
    '''
    ret = dict(self.values)
    for p in self.asked:
      v = self.vars[p.name].get()
      if p.kind == "relation":
        ret[p.name] = self.relations.get(str(v))
      elif p.kind == "int":
        try:
          ret[p.name] = int(v)
          if not 0 <= ret[p.name] <= MAX_INT:
            raise ValueError
        except ValueError:
          messagebox.showerror(self.title(), f'"{p.label}" must be a number from 0 to {MAX_INT}.', parent=self)
          return None
      else:
        ret[p.name] = v
    return ret

  def _selected(self, name:str, _event:tk.Event) -> None:
    self.changed(name)

  def changed(self, name:str) -> None:
    '''
    The user changed parameter *name*: let the layout change the others to
    suit (see *LayoutHeuristic.parameterChanged()*).

    :param name:
    :type name: str
    '''
    values = self.read()
    if values is None:
      return
    self.values = self.cls.parameterChanged(self.view, name, values)
    for p in self.asked:
      v = self.values.get(p.name)
      self.vars[p.name].set(str(getattr(v, "name", v)) if p.kind != "bool" else bool(v))

  def ok(self) -> None:
    values = self.read()
    if values is None:
      return
    self.result = values
    self.destroy()
