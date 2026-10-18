'''
What a graphical view hides or erases (*VisibilityMixin*): one of the parts of
*sn.view.graphics.sngView.SNGView* (see *viewBase*).

Created on Oct 18, 2026 (from sngView.py)

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
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
import sn
from sn.model import names
from sn.model.constraints import ConstraintError, CONSTRAINTS, mergeConstraints, CONSTRAINTS_NOTE, splitWhere
from util.attribute import Attribute, VAR
from sn.model.model import GraphObject, Relation, IsaIndividual, Node
from contextlib import contextmanager
from typing import Iterator, Iterable
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import nodeNamed, nodeTypes, relationNamed, relationTypes
from util.commandParser import CompositeCommandMgr
from sn.view.graphics.viewBase import ViewBase

logger:sn.SNLogger = sn.getLogger(__name__)

RELATION_CATEGORY = "relations: "
"How a relation type's category (for hiding or erasing its relations) is named: see *SNGView.relationCategory()*."

NODE_CATEGORY = "nodes: "
"How a node type's category (for hiding or erasing its individuals) is named: see *SNGView.nodeCategory()*."

class VisibilityMixin(ViewBase):
  '''
  What a view (*sn.view.graphics.sngView.SNGView*) shows: the categories of
  model objects (eg: types, rules, a relation type's relations) it hides or
  erases (saved with the view), what's exempt for now, what's hidden in a
  collapsed window, and doing it all in one pass over the canvas.
  '''

  def isFiltered(self, mo:GraphObject, modes:Iterable[str]=("hide", "erase")) -> bool:
    '''
    True iff *mo* is in a category currently in one of *modes* (see *hides*).

    :param mo:
    :type mo: GraphObject
    :param modes:
    :type modes: Iterable[str]
    :returns:
    :rtype: bool
    '''
    active = [c for c, mode in self.hides.items() if mode in modes and c in self.categories.keys()]
    try:
      return bool(active) and self.categories.isCategory(mo, active)
    except Exception: # (eg: a half-built object)
      return False

  def _erasedRelation(self, rel:Relation) -> bool:
    '''
    Whether a new relation shouldn't be shown: it would bring an end in an
    erased category back into the view. (A relation that's in an erased
    category itself is shown, as anything made is: see *_exemptIfFiltered()*.)

    :param rel:
    :type rel: Relation
    :returns:
    :rtype: bool
    '''
    return any(e is not None and self.findViewObjectForGraphObject(e) is None and self.isFiltered(e, ("erase",))
               for e in (rel.localSrc, rel.localDst))

  def _exemptIfFiltered(self, vo:VObject) -> None:
    '''
    *vo* was just made (or shown explicitly): if it's in a hidden or erased
    category, show it anyway -- hiding is "soft": it applies to what was there
    when the category was hidden, and hiding the category again hides this too
    -- and say so (one message for everything made at once).

    :param vo:
    :type vo: VObject
    '''
    mo = vo.modelObject
    if mo is None or vo.categoryExempt or not self.isFiltered(mo):
      return
    vo.categoryExempt = True
    cats = [c for c, mode in self.hides.items() if c in self.categories.keys() and self.categories.isCategory(mo, [c])]
    pending = self.__dict__.setdefault("_exemptPending", {})
    if not pending and self.canvas:
      self.canvas.after_idle(self._reportExempt)
    label = vo.name or type(mo).__name__
    src, dst = getattr(mo, "localSrc", None), getattr(mo, "localDst", None)
    if src is not None and dst is not None: # (a relation: by its ends, eg: "isa (tom → person)")
      label = f"{label} ({src.name} → {dst.name})"
    for c in cats:
      pending.setdefault(c, []).append(label)
    vo._applyHidden()

  def _reportExempt(self) -> None:
    pending = self.__dict__.pop("_exemptPending", {})
    for c, labels in pending.items():
      shown = ", ".join(dict.fromkeys(labels)) # (once each, in order)
      mode = "hidden" if self.hides.get(c) == "hide" else "erased"
      menu = "hide" if mode == "hidden" else "erase"
      logger.warning(f'{shown}: in the {mode} category "{c}", but shown anyway, as it was just made (or asked for). '
                     f'To {menu} it too, {menu} "{c}" again: uncheck and re-check it in the {menu} menu.')

  def shouldHide(self, vo:VObject) -> bool:
    '''
    Whether *vo* shouldn't be drawn just now: it's in a hidden category; or
    it's a relation to or from something hidden (it would lead nowhere), or a
    containment drawn as being inside its window (see *VRelation.inWindow()*);
    or it's inside a hidden context's window.

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
    '''
    mo = vo.modelObject
    if mo is None:
      return False
    if self._inCollapsedWindow(vo):
      return True
    if self.isFiltered(mo, ("hide",)) and not vo.categoryExempt and not self._inShownContext(vo):
      return True
    if isinstance(vo, VRelation):
      if vo.inWindow():
        return True
      if any(isinstance(e, VObject) and e is not vo and e._isConnected() and e.isHidden() for e in (vo.src, vo.dst)):
        return True
    if self.hides: # (windows are only hidden by a category)
      for w in self.contextWindows():
        if w is not vo and w.isHidden() and w.paneAt(vo.centerPt()) is not None and w.containmentOf(mo):
          return True
    return False

  def _inCollapsedWindow(self, vo:VObject) -> bool:
    '''
    Whether *vo* is drawn inside a collapsed context window (see *VObject.setCollapsed()*), and so not shown.

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
    '''
    mo = vo.modelObject
    return any(w.collapsed and w is not vo and w.paneAt(vo.centerPt()) is not None and w.containmentOf(mo)
               for w in self.contextWindows())

  def _inShownContext(self, vo:VObject) -> bool:
    '''
    Whether *vo* is part of a shown context window's content (eg: an isa link
    in a rule's consequent): it's then shown whatever its category -- it's
    what the rule says, not clutter.

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
    '''
    mo = vo.modelObject
    return any(not w.isHidden() and not w.collapsed and w is not vo and w.containmentOf(mo) for w in self.contextWindows())

  def applyVisibility(self) -> None:
    'Bring every object into line with the current *hides* (see *VObject._applyHidden()*).'
    vos = [vo for vo in self.values() if vo is not None and vo._isConnected()]
    for vo in sorted(vos, key=lambda vo: isinstance(vo, VRelation)): # (nodes first: relations follow their ends)
      vo._applyHidden()

  def _visibilityMenu(self, mode:str) -> tk.Menu:
    '''
    A checkbox per category for *mode* ("hide" or "erase"): checking it sets
    that category to *mode* (so unchecks it in the other menu); unchecking it
    shows the category again. The relation and node types' categories (see
    *relationCategory()*, *nodeCategory()*) are listed only while they're
    hidden or erased; "relation types..." and "node types..." choose them (see
    *chooseRelationCategories()*, *chooseNodeCategories()*).

    :param mode:
    :type mode: str
    :returns:
    :rtype: tk.Menu
    '''
    menu = tk.Menu(self.canvas)
    self._visibilityVars = getattr(self, "_visibilityVars", {}) # (keep the variables alive)
    for name in self.categories.keys():
      if name.startswith((RELATION_CATEGORY, NODE_CATEGORY)) and name not in self.hides:
        continue
      var = tk.BooleanVar(value=self.hides.get(name) == mode)
      self._visibilityVars[(mode, name)] = var
      menu.add_checkbutton(label=name, variable=var, onvalue=True, offvalue=False,
                           command=lambda n=name, v=var: self.context.visibility(n, mode if v.get() else "show")) #type: ignore[misc]
    menu.add_separator()
    menu.add_command(label="relation types...", command=lambda: self.chooseRelationCategories(mode))
    menu.add_command(label="node types...", command=lambda: self.chooseNodeCategories(mode))
    return menu

  def relationCategory(self, typ:Relation|str) -> str:
    '''
    The category of the relations of a relation type, and of its subtypes
    (not the type itself, nor isa links: see the "isa individuals" category),
    for hiding or erasing (see *visibility()*): made the first time it's
    asked for.

    :param typ: The relation type, or its name.
    :type typ: Relation | str
    :returns: The category's name: *RELATION_CATEGORY* and the type's: eg: "relations: imports".
    :rtype: str
    '''
    name = str(typ if isinstance(typ, str) else typ.name)
    category = RELATION_CATEGORY + name
    if category not in self.categories.keys():
      found:dict[str, Relation|None] = {}
      def test(mo:GraphObject) -> bool:
        if "t" not in found: # (looked up when first needed: eg: a view read before its model's super-models)
          found["t"] = typ if isinstance(typ, Relation) else relationNamed(self.model, name)
        t = found["t"]
        return t is not None and isinstance(mo, Relation) and not isinstance(mo, IsaIndividual) \
               and mo.isIndividual() and mo.isa(t)
      self.categories.addCategory(category, test)
    return category

  def nodeCategory(self, typ:Node|str) -> str:
    '''
    The category of the individuals of a node type, and of its subtypes (not
    the types themselves: see the "types" category; nor relations), for
    hiding or erasing (see *visibility()*): made the first time it's asked
    for.

    :param typ: The node type, or its name.
    :type typ: Node | str
    :returns: The category's name: *NODE_CATEGORY* and the type's: eg: "nodes: person".
    :rtype: str
    '''
    name = str(typ if isinstance(typ, str) else typ.name)
    category = NODE_CATEGORY + name
    if category not in self.categories.keys():
      found:dict[str, Node|None] = {}
      def test(mo:GraphObject) -> bool:
        if "t" not in found: # (looked up when first needed: eg: a view read before its model's super-models)
          found["t"] = typ if isinstance(typ, Node) else nodeNamed(self.model, name)
        t = found["t"]
        return t is not None and isinstance(mo, Node) and not isinstance(mo, Relation) \
               and mo.isIndividual() and mo.isa(t)
      self.categories.addCategory(category, test)
    return category

  def _setHides(self, text:str) -> None:
    '''
    Put back the hidden and erased categories saved with the view (see
    *hides*), making those of relation and node types (see
    *relationCategory()*, *nodeCategory()*).

    :param text: What was saved: eg: "types=hide,relations: imports=erase".
    :type text: str
    '''
    self.hides = dict(kv.split("=", 1) for kv in text.split(",") if "=" in kv)
    for category in self.hides:
      if category.startswith(RELATION_CATEGORY):
        self.relationCategory(category[len(RELATION_CATEGORY):])
      elif category.startswith(NODE_CATEGORY):
        self.nodeCategory(category[len(NODE_CATEGORY):])

  def _shownModelObjects(self) -> set[int]:
    ":returns: The ids of the model objects shown in the view (not erased: hidden ones too)."
    return {id(vo.modelObject) for vo in self.values() if vo is not None and vo._isConnected() and vo.modelObject is not None}

  def showRelationsOfTypes(self) -> None:
    '''
    "show" > "relations...": choose relation types in a dialog, and show
    their relations (and their subtypes') between the nodes in the view --
    and, if asked, with the nodes at their other ends too. Shown even if
    they're in a hidden or erased category (they were asked for by type: see
    *_exemptIfFiltered()*). One undoable command (see *represent()*).
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    ENDS = "and the nodes at their other ends (if those aren't shown)"
    types = [t for t in relationTypes(self.model) if t is not self.model.ISA]
    d = TypesDialog(self.canvas, "Show relations", types, set(), options=[(ENDS, False)], # type: ignore[arg-type]
                    note="Show the relations of these types (and their subtypes) between what's shown. (Isa links: "
                         "the \"isa individuals\" category.)")
    chosen = d.show()
    if not chosen:
      return
    chosenTypes = [t for t in types if id(t) in chosen]
    shown = self._shownModelObjects()
    nodes:list[GraphObject] = []
    rels:list[GraphObject] = []
    for r in self.model.values():
      if not isinstance(r, Relation) or isinstance(r, IsaIndividual) or not r.isIndividual() or id(r) in shown \
         or not r._isConnected() or not any(r.isa(t) for t in chosenTypes):
        continue
      ends = [e for e in (r.src, r.dst) if e is not None]
      missing = [e for e in ends if id(e) not in shown]
      if missing and not d.options[ENDS]:
        continue
      for e in missing:
        if e not in nodes:
          nodes.append(e)
      rels.append(r)
    self._showObjects(nodes + rels, "relations of those types")

  def showNodesOfTypes(self) -> None:
    '''
    "show" > "nodes...": choose node types in a dialog, and show their
    individuals (and their subtypes') -- and, if asked (the default), their
    relations to what's shown, and to each other (not those in a hidden or
    erased category). The nodes are shown even if they're in a hidden or
    erased category (they were asked for by type: see *_exemptIfFiltered()*).
    One undoable command (see *represent()*).
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    RELATIONS = "and their relations to what's shown"
    types = nodeTypes(self.model)
    d = TypesDialog(self.canvas, "Show nodes", types, set(), options=[(RELATIONS, True)], # type: ignore[arg-type]
                    note="Show the individuals of these types (and their subtypes).")
    chosen = d.show()
    if not chosen:
      return
    chosenTypes = [t for t in types if id(t) in chosen]
    shown = self._shownModelObjects()
    nodes:list[GraphObject] = [n for n in self.model.values() if isinstance(n, Node) and not isinstance(n, Relation)
                               and n.isIndividual() and n._isConnected() and id(n) not in shown and any(n.isa(t) for t in chosenTypes)]
    rels:list[GraphObject] = []
    if d.options[RELATIONS] and nodes:
      ends = shown | {id(n) for n in nodes}
      new = {id(n) for n in nodes}
      for r in self.model.values():
        if isinstance(r, Relation) and not isinstance(r, IsaIndividual) and r.isIndividual() and r._isConnected() \
           and id(r) not in shown and r.src is not None and r.dst is not None \
           and id(r.src) in ends and id(r.dst) in ends and (id(r.src) in new or id(r.dst) in new) and not self.isFiltered(r):
          rels.append(r)
    self._showObjects(nodes + rels, "nodes of those types")

  def _showObjects(self, objects:list[GraphObject], what:str) -> None:
    '''
    Show *objects* in the view, as one undoable command (see *represent()*) --
    or, if there are none, say so.

    :param objects: Model objects: nodes before relations.
    :type objects: list[GraphObject]
    :param what: What they are, for the message if there are none: eg: "relations of those types".
    :type what: str
    '''
    if not objects:
      from tkinter import messagebox
      messagebox.showinfo("Show", f"There are no {what} to show: they're all shown already.", parent=self.window)
      return
    self.context.represent(objects)

  def chooseRelationCategories(self, mode:str) -> None:
    '''
    "relation types...": choose, in a dialog, the relation types whose
    relations (and their subtypes') to hide or erase (*mode*); those
    unchecked that were are shown again. Done as one undoable command.

    :param mode: "hide" or "erase".
    :type mode: str
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    types = [t for t in relationTypes(self.model) if t is not self.model.ISA]
    checked = {id(t) for t in types if self.hides.get(RELATION_CATEGORY + str(t.name)) == mode}
    verb = "Hide" if mode == "hide" else "Erase"
    chosen = TypesDialog(self.canvas, f"{verb} relations", types, checked, # type: ignore[arg-type]
                                 note=f"{verb} the relations of these types (and their subtypes). "
                                      f"(Isa links: the \"isa individuals\" category.)").show()
    if chosen is None:
      return
    changes = [(self.relationCategory(t), mode if id(t) in chosen else "show") for t in types
               if (id(t) in chosen) != (id(t) in checked)]
    if not changes:
      return
    with CompositeCommandMgr(self.context):
      for category, m in changes:
        self.context.visibility(category, m)

  def chooseNodeCategories(self, mode:str) -> None:
    '''
    "node types...": choose, in a dialog, the node types whose individuals
    (and their subtypes') to hide or erase (*mode*) -- and with them, their
    relations; those unchecked that were are shown again. Done as one
    undoable command.

    :param mode: "hide" or "erase".
    :type mode: str
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    types = nodeTypes(self.model)
    checked = {id(t) for t in types if self.hides.get(NODE_CATEGORY + str(t.name)) == mode}
    verb = "Hide" if mode == "hide" else "Erase"
    chosen = TypesDialog(self.canvas, f"{verb} nodes", types, checked, # type: ignore[arg-type]
                                 note=f"{verb} the individuals of these types (and their subtypes), and their relations. "
                                      f"(The types themselves: the \"types\" category.)").show()
    if chosen is None:
      return
    changes = [(self.nodeCategory(t), mode if id(t) in chosen else "show") for t in types
               if (id(t) in chosen) != (id(t) in checked)]
    if not changes:
      return
    with CompositeCommandMgr(self.context):
      for category, m in changes:
        self.context.visibility(category, m)

  def _applyWhere(self, mo:GraphObject) -> None:
    '''
    A new object's name was typed with constraints, eg: "?p :where: alive":
    make them its "constraints" attribute. Only variables have constraints;
    for anything else, or constraints that can't be read, the name stays as
    typed (and a message says why).

    :param mo:
    :type mo: GraphObject
    '''
    name, text = splitWhere(mo.name)
    if not names.isVariableName(name):
      logger.error(f'"{mo.name}": only variables have constraints ({names.grammar.describe()}).')
      return
    try:
      merged = mergeConstraints(None, text or "")
    except ConstraintError as ex:
      logger.error(f'"{mo.name}": the constraints can\'t be read ({ex}).')
      return
    mo["name"] = name
    if merged:
      mo.setAttr(CONSTRAINTS, Attribute(merged, str, VAR, CONSTRAINTS_NOTE))

  @contextmanager
  def batchedItemStates(self) -> Iterator[None]:
    '''
    Within it, objects' hiding and showing their canvas items (see
    *VObject._hideItems()*, *VObject._showItems()*) is put off, and done at
    the end in one pass over the canvas -- instead of a search of the whole
    canvas for each object's items, which is slow for many objects in a big
    view (eg: *doEraseOthers()*, or a model's notification that takes many
    out, or puts them back: see *SNGView.update()*). Nested, only the outermost does it.
    '''
    if self.__dict__.get("_pendingItemStates") is not None:
      yield
      return
    self.__dict__["_pendingItemStates"] = {}
    try:
      yield
    finally:
      pending:dict[int, tuple[VObject, bool]] = self.__dict__.pop("_pendingItemStates")
      if pending:
        byTag = {vo.tag: (vo, hide) for vo, hide in pending.values()}
        c = self.canvas
        for i in c.find_all():
          for t in c.gettags(i):
            if t in byTag:
              vo, hide = byTag[t]
              vo._hideItem(i) if hide else vo._showItem(i)
        for vo, hide in byTag.values():
          if not hide:
            vo.__dict__["_itemsHidden"] = False
