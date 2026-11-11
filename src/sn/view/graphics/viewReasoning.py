'''
What a graphical view shows of reasoning (*ReasoningMixin*): one of the parts
of *sn.view.graphics.sngView.SNGView* (see *viewBase*).

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
import sys
import tkinter as tk
import sn
from sn.model.model import IsaIndividual, GraphObject, Relation
from typing import Any, Callable, cast, TYPE_CHECKING
from functools import partial
from html import escape
from sn.view.graphics.viewBase import ViewBase
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView
  from sn.model.reasoner import EngineMissing
  from util.actionDialog import ActionDialog

logger:sn.SNLogger = sn.getLogger(__name__)

def _hidesImplied(rel:GraphObject) -> bool:
  "Whether *rel*'s type says to leave it out of a view when it's implied by what's shown (\"vis/hideImplied\")."
  try:
    return bool(rel.get("vis/hideImplied", False))
  except Exception: # (eg: a half-built object)
    return False

def _typeDepth(rel:GraphObject) -> int:
  ":returns: How deep *rel*'s type is in the isa hierarchy (its own types: 1)."
  depth, todo, seen = 0, [(t, 1) for t in rel.getParents()], set()
  while todo:
    t, d = todo.pop()
    if id(t) not in seen:
      seen.add(id(t))
      depth = max(depth, d)
      todo += [(p, d + 1) for p in t.getParents()]
  return depth

def _names(objects:list[GraphObject]) -> str:
  '''
  :returns: *objects*, for a message: eg: "carol", "carol and bob", "carol, bob and alice", or "5 objects".
  '''
  names = [o.name for o in objects]
  if len(names) > 3:
    return f"{len(names)} objects"
  return " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)

def showEngineMissing(parent:tk.Misc, missing:str|EngineMissing, *, purpose:str="", chosen:bool=False,
                      instead:Callable[[str], None]|None=None) -> ActionDialog:
  '''
  Say that a reasoner engine isn't installed (or won't load), in a dialog with a
  link to how to install it (*sn.model.reasoner.INSTALL_HELP*, in the User
  Guide) -- and, if it's the one the "reasoner/engine" setting picks, links to
  pick an installed one instead.

  :param parent: What it's shown over.
  :param missing: The engine's name, or the error saying it's missing (see *sn.model.reasoner.Reasoner.create()*).
  :param purpose: What it was wanted for, as a sentence: eg, "Explaining a conclusion needs it."
  :param chosen: It was just chosen in Settings.
  :param instead: Called with an installed engine's name to use it this time
    (eg: to reason with it): if given, there's a link for each.
  :returns: The dialog.
  '''
  from util.actionDialog import ActionDialog
  from sn.model.reasoner import EngineMissing, INSTALL_HELP, defaultEngine, setDefaultEngine, installedEngines
  from sn.view.graphics import guiApp
  engine = missing.engine if isinstance(missing, EngineMissing) else missing
  detail = missing.detail if isinstance(missing, EngineMissing) else ""
  others = [e for e in installedEngines() if e != engine]
  actions:dict[str, Callable[[], None]] = {"help": lambda: guiApp.showHelp(INSTALL_HELP)}
  lines = [f'<b>The "{escape(engine)}" reasoner engine isn\'t {"working" if detail else "installed"}.</b>']
  if detail:
    lines.append(f"It seems to be installed, but won\'t load: {escape(detail)}")
  if chosen:
    lines.append("Settings now says to reason with it: reasoning will ask for it until it\'s installed.")
  if purpose:
    lines.append(escape(purpose))
  if getattr(sys, "frozen", False): # (the app: its own Python can't have it installed, but one on the computer can)
    lines.append(f"The app can use it installed for a Python {sys.version_info[0]}.{sys.version_info[1]} on this computer.")
  lines.append('<a id="help">How to install it</a> (in the User Guide)')
  for e in others:
    if instead is not None:
      actions[f"use:{e}"] = partial(instead, e)
      lines.append(f'<a id="use:{escape(e)}">Use {escape(e)} this time</a>')
    if defaultEngine() == engine:
      actions[f"pref:{e}"] = partial(setDefaultEngine, e)
      lines.append(f'<a id="pref:{escape(e)}">Use {escape(e)} from now on</a> (the reasoner/engine setting)')
  dialog = ActionDialog(cast(Any, parent), "Reasoner engine not installed",
                        lines[0] + "<br><br>" + "<br>".join(lines[1:]), actions, width=70)
  dialog.geometry("") # (its own size: just the few lines it has)
  return dialog

class ReasoningMixin(ViewBase):
  '''
  Reasoning, as a view (*sn.view.graphics.sngView.SNGView*) shows it: the
  reasoning toolbar, running the reasoner over the view's model (see
  *sn.model.reasoner*), showing what it inferred and the problems it found --
  and taking them away again.
  '''

  def _reasoningToolbarShown(self) -> tk.BooleanVar:
    '''
    :returns: Whether this view's reasoning toolbar is shown -- what "View | Reasoning toolbar" shows (and sets).
    '''
    var = self.__dict__.get("_reasoningToolbarVar")
    if var is None:
      var = self._reasoningToolbarVar = tk.BooleanVar(self.canvas, value=False)
    return var

  def showReasoningToolbar(self, show:bool=True, changed:bool=True) -> None:
    '''
    Show (or hide) the reasoning toolbar (see *reasoningToolbar*) across the
    bottom of this view's window.

    :param show: True to show it; False to hide it.
    :param changed: Whether it's a change to the view (it's saved with it), not the view being set up.
    '''
    from sn.view.graphics.reasoningToolbar import ReasoningToolbar
    if getattr(self, "_closed", False):
      return
    bar = self.__dict__.get("_reasoningToolbar")
    if show:
      if bar is None:
        bar = self._reasoningToolbar = ReasoningToolbar(self.window, cast("SNGView", self)) # (this part of it: see viewBase)
      bar.pack(side=tk.BOTTOM, fill=tk.X, before=self.window.appPanedWidget)
      bar.refresh()
    elif bar is not None:
      bar.pack_forget()
    if self._reasoningToolbarShown().get() != show:
      self._reasoningToolbarShown().set(show)
      if changed:
        self.setDirty() # (saved with the view)

  def reasoningSummary(self) -> str:
    '''
    :returns: What the model's last "reason" found, in a line -- eg: "inferred:
      3 relations, 4 new objects; 1 error, 2 warnings" -- or "" if it hasn't
      been reasoned over (or that's been retracted).
    '''
    from sn.model.reasoner import summary
    return summary(self.model)

  @property
  def reasoning(self) -> Any:
    '''
    The *sn.model.reasoner.Inferences* from the last "reason" over this view's
    model -- whether run from this view's menu, another view of the same model,
    or the command line (see *sn.model.reasoner.reason()*) -- or None.
    '''
    from sn.model.reasoner import reasoningFor
    return reasoningFor(self.model)

  def reason(self, engine:str|None=None, silent:bool=False, about:list[GraphObject]|None=None) -> None:
    '''
    Run the reasoner over this view's model and print the report to this
    window's terminal. The results are kept with the model, so this and every
    other view of it show them (see *_showReasoning()*), as they do when
    "reason" is typed at the command line.

    :param engine: The reasoner engine; by default the preference's (see *sn.model.reasoner.defaultEngine()*).
    :param silent: See *reasonSilently()*.
    :param about: Objects to reason about (eg: the selection: see
      *VObject.reasonAbout()*): only what's inferred about them is added to
      what's shown, and only their problems to what's marked; the report is
      about them. By default, the whole model. See *sn.model.reasoner.reason()*.
    '''
    from sn.model.reasoner import reason, summary, defaultEngine, EngineMissing
    if engine is None:
      engine = defaultEngine()
    try:
      result = reason(self.model, engine, silent=silent, about=about)
    except EngineMissing as ex: # (said, with a link to how to install it -- or to use another this time)
      logger.error(str(ex))
      showEngineMissing(self.canvas, ex, instead=lambda other: self.reason(other, silent=silent, about=about))
      return
    except RuntimeError as ex: # (eg: rules that can't be compiled: said, not a traceback -- and the summary's left as it was)
      logger.error(f'Couldn\'t reason over {self.model.name}: {ex}')
      return
    what = self.model.name if about is None else f'{_names(about)} in {self.model.name}'
    if silent:
      print(f'Reasoned {"over" if about is None else "about"} {what} (silently): {summary(self.model)}')
      return
    print(f'Reasoning {"over" if about is None else "about"} {what}:')
    print((result if about is None else result.about(about)).report(self.model))

  def reasonSilently(self, about:list[GraphObject]|None=None) -> None:
    '''
    Reason (see *reason()*) without cluttering the views: what's inferred
    isn't added to them (those already shown stay), and only a summary is
    printed -- the problems are still marked. Eg: so that queries find what
    the rules conclude (and show those they find: see *VObject.answerQuery()*).

    :param about: Objects to reason about (see *reason()*); by default, the whole model.
    '''
    self.reason(silent=True, about=about)

  def retractReasoning(self, about:list[GraphObject]) -> None:
    '''
    Take back what the model's reasoning results say about *about* (eg: the
    selection: see *VObject.retractAbout()*), in every view of the model: the
    inferred objects about them go, and their problems aren't marked. (See
    *sn.model.reasoner.retractReasoning()*; *clearReasoning()* takes back everything.)
    '''
    from sn.model.reasoner import retractReasoning
    retractReasoning(self.model, about)

  def clearReasoning(self) -> None:
    'Forget the last "reason" results for this view\'s model (in every view of it).'
    from sn.model.reasoner import clearReasoning
    clearReasoning(self.model)

  def _showReasoning(self, showInferred:bool=True, only:list[GraphObject]|None=None) -> None:
    '''
    Show the model's current reasoning results (or their absence): violations
    in the objects' status reports (their error markers and "show error
    report"), and the inferred objects (see *_showInferred()*) -- unless
    *showInferred* is False (eg: it was reasoned over silently: see
    *reasonSilently()*), when only those already shown stay.
    Called when the model reports a "reasoned", "reasoning retracted" or
    "reasoning cleared" topic. Not a change to the view: it's left as clean
    (or dirty) as it was.

    :param only: If given, show just these of the inferred objects (eg: those
      about the objects reasoned about: see *reason()*'s *about*).
    '''
    dirty = self.isDirty()
    self._refreshStatusReports()
    if showInferred:
      self._showInferred(only)
    bar = self.__dict__.get("_reasoningToolbar")
    if bar is not None:
      bar.refresh()
    if not dirty:
      self.setDirty(False)

  def _showInferred(self, only:list[GraphObject]|None=None) -> None:
    '''
    Show what the model's last "reason" inferred (see *GraphObject.inferred*),
    for what this view shows: each object a rule concluded exists that's
    related to something shown (beside it), and each inferred relation (and
    a new object's isa links) between objects shown -- those that don't have
    view objects yet. They're drawn in their usual look, faded; relations
    with dashed lines (dotted if inherited). Those no longer inferred go when
    the model removes them. None of this makes the view dirty: they aren't
    saved with it.

    :param only: If given, show just these of the inferred objects (and a new
      object's isa links, with it).
    '''
    from sn.model.reasoner import _inferredRelations
    if not self.canvas:
      return
    dirty = self.isDirty()
    shown = lambda o: o is not None and self.findViewObjectForGraphObject(o) is not None
    def show(o:GraphObject, atPoint=None) -> None:
      # (by its categories: hidden ones are made hidden, erased ones not made at all -- not
      # exempted, as something the user made would be: see _exemptIfFiltered())
      if self.isFiltered(o, ("erase",)):
        return
      try:
        vo = self.makeViewObjectForGraphObject(o, atPoint=atPoint)
        if vo is not None:
          vo._applyHidden()
          if atPoint is not None and not vo.isHidden():
            vo.adjustPos() # (a free place, beside it)
      except Exception:
        logger.exception(f"Couldn't show the inferred {o.name}")
    inferred = [o for o in self.model.inferredObjects() if o._isConnected()]
    if only is not None:
      ids = {id(o) for o in only}
      ids |= {id(r) for o in only if getattr(o, "inferredKind", None) == "new"
                    for r, _ in o._getOutgoing(lambda r: isinstance(r, IsaIndividual) and r.inferred)}
      inferred = [o for o in inferred if id(o) in ids]
    for node in [o for o in inferred if getattr(o, "inferredKind", None) == "new" and not shown(o)]:
      for r, other in [*node._getOutgoing(lambda r: r.inferred and not isinstance(r, IsaIndividual)),
                       *node._getIncoming(lambda r: r.inferred and not isinstance(r, IsaIndividual))]:
        if shown(other):
          x1, y1, x2, y2 = self.findViewObjectForGraphObject(other).boundingBox() # type: ignore[union-attr, arg-type]
          show(node, (x2 + 60, y1))
          break
    rels = [r for r in _inferredRelations(self.model).values() if only is None or id(r) in ids] \
         + [r for o in inferred if getattr(o, "inferredKind", None) == "new"
              for r, _ in o._getOutgoing(lambda r: isinstance(r, IsaIndividual) and r.inferred)] # (a new object's types)
    rels.sort(key=lambda r: -_typeDepth(r) if _hidesImplied(r) else 0) # (subtypes' first: they imply their types')
    for rel in rels:
      if rel._isConnected() and not shown(rel) and shown(rel.localSrc) and shown(rel.localDst) and not self._impliedByShown(rel):
        show(rel)
    if not dirty:
      self.setDirty(False)

  def _impliedByShown(self, rel:GraphObject) -> bool:
    '''
    :returns: Whether the inferred relation *rel* says what this view already
      shows, and its type says to leave such out ("vis/hideImplied"): it's
      from an object to itself, or a relation of its type (or a subtype)
      joins the same two objects here, the same way round -- or either way
      round, if either type is symmetric. (Eg: the KNet kernel's: cycles of
      inclusions would loop every node in them, and every exclusion would
      be drawn twice.)
    '''
    if not _hidesImplied(rel):
      return False
    src, dst = rel.localSrc, rel.localDst
    if src is dst:
      return True
    types = [t for t in rel.getParents() if isinstance(t, Relation)]
    symmetric = any(t._hasRelationalProperty("symmetric") for t in types)
    for end, other, sameWay in ((src, dst, True), (dst, src, False)):
      for r, o in end._getOutgoing(lambda r: r is not rel and not isinstance(r, IsaIndividual)):
        if o is other and self.findViewObjectForGraphObject(r) is not None \
           and any(r.isa(t) for t in types) \
           and (sameWay or symmetric or any(p._hasRelationalProperty("symmetric") for p in r.getParents() if isinstance(p, Relation))):
          return True
    return False

  def _refreshStatusReports(self) -> None:
    for vo in list(self._db.values()):
      if vo is not None:
        vo.clearStatusReport()
    self.validate(refresh=True)
    self.repaint()
