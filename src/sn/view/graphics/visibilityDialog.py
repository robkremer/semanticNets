'''
Choosing types in a dialog (*TypesDialog*): a checkbox for each, its
subtypes indented under it -- eg: "hide by category" / "erase by category" >
"relation types..." (which relation types' relations to hide or erase: see
*SNGView.chooseRelationCategories()*), and "show" > "relations..." and
"nodes..." (see *SNGView.showRelationsOfTypes()*, *SNGView.showNodesOfTypes()*).

Created on Oct 12, 2026

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
from sn.model.model import GraphObject
from util.utils import ownDialog, VerticalScrolledFrame

MAX_HEIGHT = 420
"The tallest the list of relation types gets (screen pixels): more scrolls."

def typeTree[T: GraphObject](types:list[T]) -> list[tuple[T, int]]:
  '''
  :param types: Types (eg: relation types).
  :type types: list[T]
  :returns: Them in tree order: each followed by its subtypes (those of
    *types* it's the first supertype of, among *types*), indented one more
    (the depth); siblings by name.
  :rtype: list[tuple[T, int]]
  '''
  ids = {id(t) for t in types}
  byId = {id(t): t for t in types}
  def parentOf(t:T) -> T|None:
    return next((byId[id(p)] for p in t.getParents() if id(p) in ids and p is not t), None)
  kids:dict[int, list[T]] = {}
  roots:list[T] = []
  for t in types:
    p = parentOf(t)
    if p is None:
      roots.append(t)
    else:
      kids.setdefault(id(p), []).append(t)
  ret:list[tuple[T, int]] = []
  def walk(t:T, depth:int) -> None:
    ret.append((t, depth))
    for k in sorted(kids.get(id(t), []), key=lambda r: str(r.name).lower()):
      walk(k, depth + 1)
  for r in sorted(roots, key=lambda r: str(r.name).lower()):
    walk(r, 0)
  return ret

class TypesDialog(tk.Toplevel):
  '''
  Which types (eg: relation types, whose relations to hide): a checkbox for
  each, subtypes indented under their types; and, below, any other options.
  Modal; *result* is the set of types checked (by id) if OK'd, else None;
  *options* the options' values then.
  '''
  INDENT = 18
  "Screen pixels a subtype's checkbox is indented, per level."

  def __init__(self, parent:tk.Misc, title:str, types:list[GraphObject], checked:set[int], note:str="",
               options:list[tuple[str, bool]]=[]):
    '''
    :param parent: The window it's over.
    :type parent: tk.Misc
    :param title:
    :type title: str
    :param types: The types to offer.
    :type types: list[GraphObject]
    :param checked: The ids of those checked to start with.
    :type checked: set[int]
    :param note: Said above the list, if anything.
    :type note: str
    :param options: Other choices, below the list: (label, checked to start with).
    :type options: list[tuple[str, bool]]
    '''
    super().__init__(parent)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.parent = parent
    self.title(title)
    self.result:set[int]|None = None
    self.vars:list[tuple[GraphObject, tk.BooleanVar]] = []
    self.optionVars:dict[str, tk.BooleanVar] = {label: tk.BooleanVar(value=on) for label, on in options}
    self.options:dict[str, bool] = {label: on for label, on in options}
    "The options' values, as OK'd."
    frame = ttk.Frame(self, padding=8)
    frame.pack(fill=tk.BOTH, expand=True)
    if note:
      ttk.Label(frame, text=note, foreground="gray40", wraplength=320).pack(anchor=tk.W, padx=6, pady=(0, 6))
    tree = typeTree(types)
    holder:tk.Misc
    if len(tree) > 16:
      scrolled = VerticalScrolledFrame(frame)
      scrolled.pack(fill=tk.BOTH, expand=True)
      holder = scrolled.interior
    else:
      holder = ttk.Frame(frame)
      holder.pack(fill=tk.BOTH, expand=True)
    for t, depth in tree:
      var = tk.BooleanVar(value=id(t) in checked)
      self.vars.append((t, var))
      ttk.Checkbutton(holder, text=str(t.name), variable=var).pack(anchor=tk.W, padx=(6 + self.INDENT * depth, 6), pady=1)
    if not tree:
      ttk.Label(holder, text="(there are none)", foreground="gray50").pack(anchor=tk.W, padx=6)
    if self.optionVars:
      ttk.Separator(frame).pack(fill=tk.X, pady=6)
      for label, var in self.optionVars.items():
        ttk.Checkbutton(frame, text=label, variable=var).pack(anchor=tk.W, padx=6, pady=1)
    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(8, 0))
    ttk.Button(buttons, text="OK", command=self.ok, default="active").pack(side=tk.RIGHT, padx=6)
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=6)
    ttk.Button(buttons, text="None", command=self.clear).pack(side=tk.LEFT, padx=6)
    self.bind("<Return>", lambda _e: self.ok())
    self.bind("<Escape>", lambda _e: self.destroy())

  def clear(self) -> None:
    "Uncheck them all."
    for _, var in self.vars:
      var.set(False)

  def ok(self) -> None:
    self.result = {id(t) for t, v in self.vars if v.get()}
    self.options = {label: var.get() for label, var in self.optionVars.items()}
    self.destroy()

  def show(self) -> set[int]|None:
    '''
    Show it (over its parent's window, in front), and wait for an answer.

    :returns: *result*.
    :rtype: set[int] | None
    '''
    self.update_idletasks()
    if self.winfo_reqheight() > MAX_HEIGHT + 120:
      self.geometry(f"{max(260, self.winfo_reqwidth())}x{MAX_HEIGHT + 120}")
    top = self.parent.winfo_toplevel()
    if top.winfo_viewable():
      w, h = self.winfo_reqwidth(), min(self.winfo_reqheight(), MAX_HEIGHT + 120)
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

RelationTypesDialog = TypesDialog
"(Its name when it was only for relation types.)"
