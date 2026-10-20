'''
The dialog that asks for a layout heuristic's parameters (see
*layout.LayoutHeuristic.askParameters()*): made from its *PARAMETERS* (see
*layout.LayoutParameter*) -- a relation type, a table of them (see
*RelationTableEditor*), a choice, a number, or a yes/no -- with OK and Cancel.
The form itself (*LayoutForm*) is also what the layout panel's pages show
(see *layoutPanel*).

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
from util.utils import ownDialog
from util.tooltip import CreateToolTip
from sn.view.graphics.layout import LayoutParameter, relationTypes
from sn.view.graphics.relationTable import (RelationTable, RelationRow, TypeNode, SHAPES, PULLS, IGNORED, TERMINALS,
                                            defaultParentEnd, relationTree, shownRelationTypes)

MAX_INT = 10000
"The biggest number the dialog's number fields take."

class LayoutForm(ttk.Frame):
  '''
  A form for some of a layout heuristic's parameters: a row for each (see the
  module doc). It's what *LayoutDialog* shows, and the layout panel's pages
  (see *layoutPanel.LayoutPanel*).
  '''
  def __init__(self, parent:tk.Misc, cls:Any, asked:list[LayoutParameter], values:dict[str, Any], view:Any,
               wrap:int=360, compact:bool=False):
    '''
    :param parent: What it's in.
    :param cls: The layout heuristic's class (see *LayoutHeuristic.parameterChanged()*).
    :type cls: type[LayoutHeuristic]
    :param asked: The parameters to ask for.
    :param values: All its parameters' values to start with (a relation as a *Relation* or its name).
    :param view: The view it's for: its model's relation types are the choices for a relation.
    :type view: SNGView
    :param wrap: How wide (pixels) the parameters' notes are, before they wrap (see *setWrap()*).
    :param compact: Whether it's laid out narrow: each parameter's name above its entry, and a table of
      relation types a type on two lines (see *RelationTableEditor*).
    '''
    super().__init__(parent)
    self.cls, self.view, self.asked = cls, view, asked
    self.values:dict[str, Any] = dict(values)
    self.relations = {str(r.name): r for r in relationTypes(view.model)}
    self.vars:dict[str, tk.Variable] = {}
    self.tables:dict[str, RelationTableEditor] = {}
    self.notes:list[ttk.Label] = []
    self._widgets:dict[str, Any] = {} # (a relation's or a choice's or a number's entry, by name)
    pad:dict[str, Any] = dict(padx=8, pady=3)
    row = 0
    for p in asked:
      v = self.values.get(p.name)
      if p.kind == "relations":
        ttk.Label(self, text=p.label + ":").grid(row=row, column=0, columnspan=2, sticky=tk.W, **pad)
        row += 1
        table = v if isinstance(v, RelationTable) else RelationTable.decode(v) if isinstance(v, str) else RelationTable.single("isa")
        editor = RelationTableEditor(self, table, view.model, shownRelationTypes(view), compact=compact)
        editor.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=(4, 0) if compact else 16)
        self.tables[p.name] = editor
        row += 1
        if p.note:
          note = ttk.Label(self, text=p.note, foreground="gray40", wraplength=wrap)
          note.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=24)
          self.notes.append(note)
          row += 1
        continue
      if p.kind == "bool":
        var:tk.Variable = tk.BooleanVar(value=bool(v))
        ttk.Checkbutton(self, text=p.label, variable=var, command=partial(self.changed, p.name)) \
          .grid(row=row, column=0, columnspan=2, sticky=tk.W, **pad)
      else:
        ttk.Label(self, text=p.label + ":").grid(row=row, column=0, columnspan=2 if compact else 1, sticky=tk.W, **pad)
        if compact: # (its entry below it)
          row += 1
        width = 16 if compact else 20
        if p.kind == "relation":
          var = tk.StringVar(value=str(getattr(v, "name", v) or ""))
          w:tk.Widget = ttk.Combobox(self, textvariable=var, values=list(self.relations), state="readonly", width=width,
                                     postcommand=partial(self._relationNames, p.name))
          w.bind("<<ComboboxSelected>>", partial(self._selected, p.name))
        elif p.kind == "choice":
          var = tk.StringVar(value=str(v))
          w = ttk.Combobox(self, textvariable=var, values=list(p.choices), state="readonly", width=width)
          w.bind("<<ComboboxSelected>>", partial(self._selected, p.name))
        else: # int
          var = tk.StringVar(value=str(v))
          w = ttk.Spinbox(self, from_=0, to=MAX_INT, textvariable=var, width=8)
        if compact:
          w.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=(24, 8), pady=(0, 3))
        else:
          w.grid(row=row, column=1, sticky=tk.W, **pad)
        self._widgets[p.name] = w
      self.vars[p.name] = var
      row += 1
      if p.note:
        note = ttk.Label(self, text=p.note, foreground="gray40", wraplength=wrap)
        note.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=24)
        self.notes.append(note)
        row += 1

  def setWrap(self, wrap:int) -> None:
    '''
    :param wrap: How wide (pixels) the parameters' notes are now, before they wrap.
    '''
    for note in self.notes:
      if int(str(note.cget("wraplength")) or 0) != wrap:
        note.configure(wraplength=wrap)

  def _relationNames(self, name:str) -> None:
    'Fill a relation\'s list (just before it drops down: the model may have changed since the form was made).'
    self.relations = {str(r.name): r for r in relationTypes(self.view.model)}
    w = self._widgets.get(name)
    if w is not None:
      w.configure(values=list(self.relations))

  def read(self, complain:bool=True) -> dict[str, Any]|None:
    '''
    :param complain: Whether to say why, if a number isn't one.
    :returns: All the parameters' values, with those asked for as shown -- or
      None if a number isn't one.
    '''
    ret = dict(self.values)
    for p in self.asked:
      if p.kind == "relations":
        ret[p.name] = self.tables[p.name].table()
        continue
      v = self.vars[p.name].get()
      if p.kind == "relation":
        ret[p.name] = self.relations.get(str(v))
      elif p.kind == "int":
        try:
          ret[p.name] = int(v)
          if not 0 <= ret[p.name] <= MAX_INT:
            raise ValueError
        except ValueError:
          if complain:
            messagebox.showerror(self.winfo_toplevel().title() or "Layout",
                                 f'"{p.label}" must be a number from 0 to {MAX_INT}.', parent=self.winfo_toplevel())
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
    '''
    values = self.read()
    if values is None:
      return
    self.values = self.cls.parameterChanged(self.view, name, values)
    for p in self.asked:
      v = self.values.get(p.name)
      if p.kind == "relations":
        if isinstance(v, RelationTable) and v != self.tables[p.name].table():
          self.tables[p.name].setTable(v)
        continue
      self.vars[p.name].set(str(getattr(v, "name", v)) if p.kind != "bool" else bool(v))

class LayoutDialog(tk.Toplevel):
  '''
  Asks for some of a layout heuristic's parameters, with a *LayoutForm*.
  Modal; *result* is all of its parameters' values (as keyword arguments for
  its constructor: a relation as a *Relation*) if OK'd, else None.
  '''
  def __init__(self, parent:tk.Misc, title:str, cls:Any, asked:list[LayoutParameter], values:dict[str, Any], view:Any):
    '''
    :param parent: The window it's over.
    :param cls: The layout heuristic's class (see *LayoutHeuristic.parameterChanged()*).
    :type cls: type[LayoutHeuristic]
    :param asked: The parameters to ask for.
    :param values: All its parameters' values to start with (a relation as a *Relation* or its name).
    :param view: The view it's for: its model's relation types are the choices for a relation.
    :type view: SNGView
    '''
    super().__init__(parent)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.title(title)
    self.result:dict[str, Any]|None = None
    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    self.form = LayoutForm(frame, cls, asked, values, view)
    self.form.pack(fill=tk.BOTH, expand=True)
    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(buttons, text="OK", command=self.ok, default="active").pack(side=tk.RIGHT, padx=6)
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=6)
    self.bind("<Return>", lambda _e: self.ok())
    self.bind("<Escape>", lambda _e: self.destroy())
    self.update_idletasks()
    try:
      self.grab_set()
    except tk.TclError: # (not viewable yet)
      pass
    self.focus_force()
    self.wait_window()

  def ok(self) -> None:
    values = self.form.read()
    if values is None:
      return
    self.result = values
    self.destroy()

class RelationTableEditor(ttk.Frame):
  '''
  Edits a relation table (see *relationTable.RelationTable*) as a tree of
  relation types (see *relationTable.relationTree()*): those shown in the
  view, and their supertypes, each subtype indented under its supertype (▸
  and ▾ close and open a supertype: it's closed unless one of its subtypes
  has a row of its own), and the relation types' own ends (see
  *relationTable.TERMINALS*). Each has a role (see *CHOICES*): its own row's,
  or -- "as <supertype>" -- the nearest supertype's that has a row (a row
  stands for its subtypes: so one for a supertype can do for all of them).
  ↑ and ↓ move a type among its siblings (with its subtypes): the higher rows
  win. Compact (eg: in the layout panel), each is on two lines: its name, and
  below it its role.
  '''
  INDENT = 12
  "How far (pixels) a subtype's indented under its supertype."

  CHOICES:dict[str, tuple[str, str]] = {"parent: source": (SHAPES, "source"), "parent: destination": (SHAPES, "destination"),
                                        PULLS: (PULLS, ""), IGNORED: (IGNORED, "")}
  '''The roles a type's own row can have: the choice, and its role and parent
  end ("parent: ...": it shapes the trees, with that end the parent).'''

  TIPS = {"up": "Move it up, with its subtypes: the higher rows win (eg: for a node related to two parents).",
          "down": "Move it down, with its subtypes: the higher rows win.",
          "open": "Show or hide its subtypes.",
          "role": "Its role: shapes the trees (with which end is the parent), pulls things together, or is ignored -- "
                  "or, \"as\" one of its supertypes, whatever that one's row does."}

  def __init__(self, parent:tk.Misc, table:RelationTable, model:Any, shown:list[Any], compact:bool=False):
    '''
    :param parent: What it's in.
    :param table: The table to start with.
    :param model: The view's model.
    :type model: Model
    :param shown: The relation types of the relations shown in the view (see *relationTable.shownRelationTypes()*).
    :type shown: list[Relation]
    :param compact: Whether it's laid out narrow, a type on two lines.
    '''
    super().__init__(parent)
    self.compact = compact
    self.model, self.shown = model, list(shown)
    self.boxes:dict[str, ttk.Combobox] = {}
    "Each type's role drop-down, by its name, as shown now."
    self.setTable(table)

  def setTable(self, table:RelationTable) -> None:
    ":param table: The table to show now."
    self.rows:dict[str, RelationRow] = {r.relation: r for r in table.rows}
    "The types' own rows, by name."
    self.roots:list[TypeNode] = relationTree(table, self.model, self.shown)
    self.open:set[str] = {n.name for root in self.roots for n in root.walk()
                          if any(d.name in self.rows for c in n.children for d in c.walk())}
    "The types whose subtypes are shown."
    self._build()

  def table(self) -> RelationTable:
    ":returns: The table, as it's shown now: the types' own rows, in the tree's order."
    return RelationTable([self.rows[n.name] for root in self.roots for n in root.walk() if n.name in self.rows])

  def covering(self, node:TypeNode) -> TypeNode|None:
    ''':returns: The nearest supertype of *node* (in the tree) that has a row of its own, if any.'''
    up = node.parent
    while up is not None and up.name not in self.rows:
      up = up.parent
    return up

  def choiceOf(self, node:TypeNode) -> str:
    ''':returns: What *node*'s drop-down says: its own row's role (see *CHOICES*), or what it has as one of its supertypes'.'''
    row = self.rows.get(node.name)
    if row is not None:
      return f"parent: {row.parentEnd}" if row.role == SHAPES else row.role
    return self.inherited(node)

  def inherited(self, node:TypeNode) -> str:
    ''':returns: The choice that gives *node* no row of its own: "as <supertype>" (see *covering()*), or, if none has one, as no row does.'''
    up = self.covering(node)
    return f"as {up.name}" if up is not None else f"as no row: {PULLS}"

  def _visible(self) -> list[tuple[TypeNode, int, list[TypeNode]]]:
    ''':returns: The types shown (their supertypes open), in order: each with its depth and its siblings.'''
    ret:list[tuple[TypeNode, int, list[TypeNode]]] = []
    def visit(level:list[TypeNode], depth:int) -> None:
      for n in level:
        ret.append((n, depth, level))
        if n.name in self.open:
          visit(n.children, depth + 1)
    visit(self.roots, 0)
    return ret

  def _icon(self, parent:tk.Misc, text:str, command:Any, enabled:bool, tip:str) -> ttk.Label:
    ''':returns: A small clickable icon (narrower than a button): greyed, and doing nothing, if not *enabled*.'''
    icon = ttk.Label(parent, text=text, foreground="black" if enabled else "gray75", cursor="hand2" if enabled else "")
    if enabled:
      icon.bind("<Button-1>", lambda _e: command())
      CreateToolTip(icon, tip, wrapLength=300)
    return icon

  def _build(self) -> None:
    "(Re)make the types' widgets."
    for w in self.winfo_children():
      w.destroy()
    self.boxes = {}
    if self.compact:
      ttk.Label(self, text="Each relation type's role (\"parent: ...\" shapes the trees):", foreground="gray40",
                wraplength=220).pack(side=tk.TOP, anchor=tk.W, pady=(0, 2))
    for i, (node, depth, siblings) in enumerate(self._visible()):
      if self.compact:
        line = ttk.Frame(self)
        line.pack(side=tk.TOP, fill=tk.X, pady=(4, 0))
        where:tk.Misc = line
      else:
        where = self
      k = siblings.index(node)
      up = self._icon(where, "↑", partial(self._move, node, siblings, -1), k > 0, self.TIPS["up"])
      down = self._icon(where, "↓", partial(self._move, node, siblings, 1), k < len(siblings) - 1, self.TIPS["down"])
      name = ttk.Frame(where)
      ttk.Frame(name, width=max(1, depth * self.INDENT)).pack(side=tk.LEFT) # (indented under its supertype)
      if node.children:
        self._icon(name, "▾" if node.name in self.open else "▸", partial(self._toggle, node), True, self.TIPS["open"]) \
          .pack(side=tk.LEFT)
      else:
        ttk.Frame(name, width=self.INDENT).pack(side=tk.LEFT) # (room for one)
      label = ttk.Label(name, text=node.name, wraplength=200)
      if node.name == TERMINALS:
        label.configure(font=("TkDefaultFont", 11, "italic"))
      label.pack(side=tk.LEFT, padx=(2, 0))
      choices = list(self.CHOICES) if node.name == TERMINALS else [self.inherited(node)] + list(self.CHOICES)
      choice = tk.StringVar(value=self.choiceOf(node))
      box = ttk.Combobox(self, textvariable=choice, values=choices, state="readonly", width=19)
      box.bind("<<ComboboxSelected>>", partial(self._chosen, node, choice))
      CreateToolTip(box, self.TIPS["role"], wrapLength=300)
      self.boxes[node.name] = box
      if self.compact:
        up.pack(side=tk.LEFT)
        down.pack(side=tk.LEFT, padx=(1, 0))
        name.pack(side=tk.LEFT, padx=(2, 0))
        box.pack(side=tk.TOP, anchor=tk.W, padx=(16 + depth * self.INDENT, 0), pady=(1, 0))
      else:
        up.grid(row=i, column=0, padx=(4, 0), pady=1)
        down.grid(row=i, column=1, padx=(1, 4), pady=1)
        name.grid(row=i, column=2, sticky=tk.W, pady=1)
        box.grid(row=i, column=3, sticky=tk.W, padx=8, pady=1)

  def _chosen(self, node:TypeNode, choice:tk.StringVar, _event:tk.Event|None=None) -> None:
    "*node*'s role was chosen: a row of its own, or none (as its supertype's)."
    picked = self.CHOICES.get(choice.get())
    if picked is None:
      self.rows.pop(node.name, None)
    else:
      role, end = picked
      self.rows[node.name] = RelationRow(node.name, role, end or defaultParentEnd(node.name))
    self._build() # (its subtypes' "as ..." may have changed)

  def _toggle(self, node:TypeNode) -> None:
    "Show or hide *node*'s subtypes."
    self.open.symmetric_difference_update({node.name})
    self._build()

  def _move(self, node:TypeNode, siblings:list[TypeNode], by:int) -> None:
    "Move *node* (with its subtypes) up (*by* -1) or down (1) among its *siblings*."
    i = siblings.index(node)
    j = i + by
    if 0 <= j < len(siblings):
      siblings[i], siblings[j] = siblings[j], siblings[i]
      self._build()
