'''
The hooks (see *sn.hooks*) that the KNet kernel model (knet.snm: see
tools/makeKnetRules.py) names on *knode*, for Gaines's truth marks -- a node
is true (T: what it stands for holds), false (F), both (Belnap's "both":
inconsistent), or unmarked:

  - ``vis/sideBars`` (*markBars()*): a vertical bar beside a node that's
    marked true, and a horizontal one over a node that's marked false, as
    Gaines draws them, in the colour of how it got the mark (see
    *MARK_COLORS*);
  - ``.menu/Mark/True``, ``.menu/Mark/False`` (*markTrue()*, *markFalse()*):
    assert a mark on the selected nodes, and ``.menu/Mark/Clear``
    (*clearMarks()*): take back the marks asserted on them;
  - ``.menu/Probes...`` (*showProbes()*): show the probes of the node's net
    (see *probes*);
  - ``.menu/Net/Minimal form``, ``.menu/Net/Maximal form`` (*minimalForm()*,
    *maximalForm()*): put the node's net in Gaines's canonical forms (see
    *forms*): take out the links the rest imply, or assert those they do;
  - ``.menu/Net/Saturate`` (*saturate()*): add the net's admissible probes,
    as nodes linked to it (see *forms.saturate()*);
  - ``.menu/Net/Check merge with...`` (*checkMerge()*): what merging another
    net (a model, or a Rep Plus net file) into it would do (see
    *forms.checkMerge()*), in a window (see *showMerge()*);
  - ``.menu/Mark/Abduce`` (*abduce()*): KNet's abductive inference from the
    node: the marks that hold whatever explains it (see *abduction*);
  - ``.menu/Expand/Anonymous node below``, ``.menu/Expand/Anonymous node
    above`` (*addAnonymousBelow()*, *addAnonymousAbove()*): Gaines's
    single-node expansion (see *expansion.addAnonymous()*);
  - ``.menu/Net/Expand protoconnectives`` (*expandProtoconnectives()*): its
    nodes whose labels group others' replaced by them (see
    *expansion.expandProtoconnectives()*);
  - ``.menu/Net/Factor`` (*factor()*): anonymous nodes interpolated to carry
    the links some nodes each have to each of some others (see
    *expansion.factor()*);
  - ``.menu/Existence/Essentially top``, ``.menu/Existence/Essentially
    bottom``, ``.menu/Existence/Unspecified`` (*essentiallyTop()*,
    *essentiallyBottom()*, *unspecified()*): specify what the selected nodes
    essentially are, and ``.menu/Net/Existence...`` (*showExistence()*): the
    existential status of the net's nodes, in a window (see *existence*).

A mark is two attributes, *MARK_TRUE* and *MARK_FALSE*, each saying how the
node got it: "asserted" (by these menu items, or a net's file), or by the
kernel's rules -- "included" (it's included by something true), "excluded"
(it excludes something true), "coexcluded" (it coexcludes something false),
or "irrelevant" (Rep Plus's name: it includes something false). The
reasoners conclude those (see knet.snm's mark rules); "reason" shows them.
Or "abduced", by abduction (see *abduce()*): until the next "reason".

Created on Nov 11, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
from typing import Any
import sn
from sn.hooks import hook, HookContext

logger:sn.SNLogger = sn.getLogger(__name__)

MARK_TRUE, MARK_FALSE = "markTrue", "markFalse"
"The attributes that mark a node true or false: their values say how it got the mark (see the module doc)."

ASSERTED = "asserted"
"How a mark the user (or a net's file) gives a node got there."

MARK_COLORS = {"asserted": "#693804", "included": "#000000", "irrelevant": "#a9a9a9", "excluded": "#00a000",
               "coexcluded": "#0000ff", "definition": "#ff0000", "necessary": "#ff0000", "default": "#800080",
               "abduced": "#800080"}
'''Each way a node gets a mark -> its bar's colour: Rep Plus's mark kinds'
(Gaines's paper's: brown asserted, black and blue true, grey and green
false; KNet draws what it abduces as defaults). Another (eg: a net's own
mark kind) is drawn black.'''

SIDES = {MARK_TRUE: "right", MARK_FALSE: "top"}
"Where each mark's bar goes (see *sn.view.graphics.decorators.SideBars*): true's beside the node, false's over it."

def marks(obj:Any) -> dict[str, str]:
  '''
  :returns: *obj*'s marks: *MARK_TRUE* and/or *MARK_FALSE* -> how it got it.
  '''
  ret = {}
  for key in SIDES:
    try:
      v = obj.get(key, None)
    except Exception:
      v = None
    if v not in (None, "", False):
      ret[key] = str(v)
  return ret

@hook
def markBars(obj:Any, _context:HookContext) -> str:
  '''
  :returns: *obj*'s marks as side bars (see the module doc): eg,
    "right:#693804" for a node asserted true.
  '''
  return " ".join(f"{SIDES[key]}:{MARK_COLORS.get(how.lower(), '#000000')}" for key, how in marks(obj).items())

def _markable(mo:Any) -> bool:
  '''
  :returns: Whether a mark can be asserted on the model object *mo*: a node
    (not one the reasoner made, or a variable).
  '''
  from sn.model.model import Node
  return isinstance(mo, Node) and not getattr(mo, "inferred", False) and not mo.isVariable()

def _targets(obj:Any, context:HookContext) -> list[Any]:
  '''
  :returns: What a menu item acts on: the selection's nodes that can be
    marked (see *_markable()*), or just *obj*.
  '''
  ret = [vo.modelObject for vo in context.selection if _markable(getattr(vo, "modelObject", None))]
  return ret or [obj]

def _canMark(obj:Any, _context:HookContext) -> bool:
  "The mark menu items' *appliesTo*: an individual node that can be marked (see *_markable()*: a type's instances are marked, not it)."
  try:
    return obj.isIndividual() and _markable(obj)
  except Exception:
    return False

def _asserted(obj:Any) -> list[str]:
  '''
  :returns: The marks asserted on *obj* itself: its own (not inferred) *MARK_TRUE* and *MARK_FALSE*.
  '''
  ret = []
  for key in SIDES:
    a = obj.getLocalAttr(key)
    if a is not None and not getattr(a, "inferred", False):
      ret.append(key)
  return ret

def _setMarks(obj:Any, context:HookContext, add:list[str], clear:list[str]) -> None:
  '''
  Assert the marks *add* (as *ASSERTED*) on the nodes the menu item acts on
  (see *_targets()*), and take back their asserted marks *clear*: as one
  command (undone in one go), if there's a view to do it in.
  '''
  from util.attribute import Attribute, VAR
  targets = _targets(obj, context)
  view = context.view
  ctx = getattr(view, "context", None)
  def do(setAttr, delAttr) -> None:
    for mo in targets:
      for key in clear:
        if key in _asserted(mo):
          delAttr(mo, key)
      for key in add:
        local = mo.getLocalAttr(key)
        if local is None or getattr(local, "inferred", False) or local.value != ASSERTED: # (a whole record: an inferred one is replaced)
          setAttr(mo, key, Attribute(ASSERTED, str, VAR))
  if ctx is None: # (not from a view: eg, a test)
    do(lambda mo, k, a: mo.setAttr(k, a), lambda mo, k: mo.__delitem__(k))
    return
  from util.commandParser import CompositeCommandMgr
  with CompositeCommandMgr(ctx):
    do(lambda mo, k, a: ctx.set_attribute(mo, k, a), lambda mo, k: ctx.delete_attribute(mo, k))

@hook(appliesTo=_canMark)
def markTrue(obj:Any, context:HookContext) -> None:
  "Mark the selected nodes true (asserted): Gaines's vertical bar. (A node marked false too is both.)"
  _setMarks(obj, context, [MARK_TRUE], [])

@hook(appliesTo=_canMark)
def markFalse(obj:Any, context:HookContext) -> None:
  "Mark the selected nodes false (asserted): Gaines's horizontal bar. (A node marked true too is both.)"
  _setMarks(obj, context, [MARK_FALSE], [])

def _hasAsserted(obj:Any, context:HookContext) -> bool:
  "*clearMarks()*'s *appliesTo*: something it acts on has a mark asserted on it."
  try:
    return any(_asserted(mo) for mo in _targets(obj, context))
  except Exception:
    return False

@hook(appliesTo=_hasAsserted)
def clearMarks(obj:Any, context:HookContext) -> None:
  "Take back the marks asserted on the selected nodes (those the reasoners concluded go when they no longer follow)."
  _setMarks(obj, context, [], list(SIDES))

@hook(appliesTo=_canMark) # (a node of the net)
def showProbes(obj:Any, context:HookContext) -> Any:
  '''
  Show the probes of the node's net -- KNet's probes, probe sets and
  reconstruction -- in a window of their own (see *probes.ProbesDialog*).

  :returns: The window's *ProbesDialog*.
  '''
  from .probes import ProbesDialog
  model = obj.model
  return ProbesDialog(getattr(context.view, "canvas", None), model, title=_netName(model)) # (over the view's window)

def _context(context:HookContext) -> Any:
  ''':returns: The view's *ModelContext* (to change the model as one command, undone in one go), if there's a view.'''
  return getattr(context.view, "context", None)

def _describe(r:Any) -> str:
  ''':returns: A link, as its ends' names and its relation type's: eg, "dog Includes animal".'''
  from .probes import name
  return f"{name(r.src)} {r.getParents()[0].name} {name(r.dst)}"

def _netCommand(obj:Any, context:HookContext, what:str, do:Any, done:str) -> list[Any]:
  '''
  Do *do* (with the view's context, if any: see *_context()*) to the node's
  net, and say what it did in the view's window's terminal (or why it
  couldn't, as an error).

  :param what: What it is (eg: "Minimal form").
  :param do: Does it: *do(context)* returns the links it changed.
  :param done: What it did to them (eg: "took out").
  :returns: The links.
  '''
  from sn.model.reasoner import EngineMissing
  net = _netName(obj.model) or str(obj.model.name)
  try:
    links = list(do(_context(context)))
  except (EngineMissing, RuntimeError, ValueError) as ex:
    logger.error(f"{what} of {net}: {ex}")
    return []
  print(f"{what} of {net}: {done} {len(links)} link{'' if len(links) == 1 else 's'}" + (":" if links else "."))
  for r in links:
    print(f"  {_describe(r)}")
  return links

@hook(appliesTo=_canMark)
def minimalForm(obj:Any, context:HookContext) -> list[Any]:
  '''
  Put the node's net in Gaines's minimal canonical form: take out its links
  that the rest imply (see *forms.minimalForm()*).

  :returns: The links taken out.
  '''
  from . import forms
  return _netCommand(obj, context, "Minimal form", lambda ctx: forms.minimalForm(obj.model, ctx), "took out")

@hook(appliesTo=_canMark)
def maximalForm(obj:Any, context:HookContext) -> list[Any]:
  '''
  Put the node's net in Gaines's maximal canonical form: assert the kernel's
  links that it implies (see *forms.maximalForm()*).

  :returns: The links asserted.
  '''
  from . import forms
  return _netCommand(obj, context, "Maximal form", lambda ctx: forms.maximalForm(obj.model, ctx), "asserted")

@hook(appliesTo=_canMark)
def saturate(obj:Any, context:HookContext) -> list[Any]:
  '''
  Saturate the node's net: add its admissible probes, as nodes that include
  the nodes true in them and exclude those false (see *forms.saturate()*).

  :returns: What was added: the probes, then their links.
  '''
  from sn.model.reasoner import EngineMissing, TooManyProbes
  from sn.model.model import Relation
  from . import forms
  net = _netName(obj.model) or str(obj.model.name)
  try:
    added = forms.saturate(obj.model, context=_context(context))
  except TooManyProbes as ex:
    logger.error(f"Saturate {net}: {ex} Probes of nodes that aren't linked are every combination of theirs: "
                 "try a smaller net (see its probes: Probes... on a node's menu).")
    return []
  except (EngineMissing, RuntimeError, ValueError) as ex:
    logger.error(f"Saturate {net}: {ex}")
    return []
  probes = [o for o in added if not isinstance(o, Relation)]
  print(f"Saturated {net}: added {len(probes)} admissible probe{'' if len(probes) == 1 else 's'}"
        f"{': ' + ', '.join(str(p.name) for p in probes) if probes else '.'}")
  return added

NET_FILES = [("Nets", "*.snm *.rnet"), ("Models", "*.snm"), ("Rep Plus nets", "*.rnet"), ("All files", "*")]
"What *checkMerge()* asks for: another net, as a model or a Rep Plus net file."

def askNet(parent:Any) -> str:
  '''
  Ask for the net to merge in (see *checkMerge()*).

  :returns: Its file's path, or "" if none was chosen.
  '''
  from tkinter import filedialog
  return filedialog.askopenfilename(parent=parent, title="Check a merge with which net?", filetypes=NET_FILES) or ""

def openNet(path:str) -> tuple[Any, str|None]:
  '''
  :param path: A model (.snm) or a Rep Plus net file (.rnet).
  :returns: Its model -- the one in memory, if it's open -- and, if it was
    made just now from a net file (not saved), the folder it was made in: to
    let go of both once it's used (see *sn.model.model.Model.unload()*).
  '''
  import os
  import tempfile
  from pathlib import Path
  from sn.model.model import Model
  if path.lower().endswith(".rnet"):
    from . import rnet, reader
    folder = tempfile.mkdtemp(prefix="snNet-")
    return reader.buildModel(rnet.parse(path), os.path.join(folder, Path(path).stem + ".snm")).model, folder
  return Model.getDB(Path(path).resolve().as_uri()), None

@hook(appliesTo=_canMark)
def checkMerge(obj:Any, context:HookContext) -> Any:
  '''
  Ask for another net (see *askNet()*), and show what merging it into the
  node's net would do (see *showMerge()*).

  :returns: The window's *ReportWindow*, or None if no net was chosen (or it
    couldn't be read: said, as an error).
  '''
  parent = getattr(context.view, "canvas", None)
  path = askNet(parent)
  if not path:
    return None
  return showMerge(parent, obj.model, path)

def showMerge(parent:Any, model:Any, path:str) -> Any:
  '''
  Show what merging the net at *path* into *model*'s would do (see
  *forms.checkMerge()*), in a window of its own.

  :param parent: The window it's opened over, if any.
  :returns: The window's *ReportWindow*, or None if the net couldn't be read
    (said, as an error).
  '''
  import os
  import shutil
  from sn.model.reasoner import EngineMissing
  from util.reportWindow import ReportWindow
  from . import forms
  try:
    other, folder = openNet(path)
  except Exception as ex:
    logger.error(f'Couldn\'t read "{path}" to check merging it: {ex}')
    return None
  net, theirs = _netName(model) or str(model.name), os.path.splitext(os.path.basename(path))[0]
  window = ReportWindow(parent, f"Merge: {theirs} into {net}")
  try:
    with window.busy():
      if other is model:
        raise ValueError(f"{theirs} is {net}: choose another net to merge with it.")
      text = forms.checkMerge(model, other).report()
  except (EngineMissing, RuntimeError, ValueError) as ex:
    text = str(ex)
  finally:
    if folder is not None: # (made from a net file just now: let go of)
      other.unload()
      shutil.rmtree(folder, ignore_errors=True)
  window.show(text)
  return window

def _netName(model:Any) -> str:
  ''':returns: The name of *model*'s file, without its folder or extension (eg: "patterns").'''
  import os
  from urllib.parse import unquote, urlparse
  url = str(getattr(model, "url", "") or "")
  return os.path.splitext(os.path.basename(unquote(urlparse(url).path)))[0]

def _say(obj:Any, what:str, made:list[Any]) -> None:
  '''
  Say, in the view's window's terminal, what a command that makes nodes and
  links (see *expansion*) made.

  :param what: What it is (eg: "Factor").
  '''
  from sn.model.model import Relation
  from .probes import name
  net = _netName(obj.model) or str(obj.model.name)
  nodes = [o for o in made if not isinstance(o, Relation)]
  links = [o for o in made if isinstance(o, Relation)]
  print(f"{what} in {net}: made {len(nodes)} node{'' if len(nodes) == 1 else 's'}"
        f"{' (' + ', '.join(name(n) for n in nodes) + ')' if nodes else ''} and {len(links)} link{'' if len(links) == 1 else 's'}"
        + (":" if links else "."))
  for r in links:
    print(f"  {_describe(r)}")

@hook(appliesTo=_canMark)
def addAnonymousBelow(obj:Any, context:HookContext) -> list[Any]:
  '''
  Add an anonymous node below the node: one that includes it (Gaines's
  single-node expansion: see *expansion.addAnonymous()*).

  :returns: The node made, and its link.
  '''
  from . import expansion
  made = expansion.addAnonymous(obj, below=True, context=_context(context))
  _say(obj, "Anonymous node", made)
  return made

@hook(appliesTo=_canMark)
def addAnonymousAbove(obj:Any, context:HookContext) -> list[Any]:
  '''
  Add an anonymous node above the node: one it includes (see *expansion.addAnonymous()*).

  :returns: The node made, and its link.
  '''
  from . import expansion
  made = expansion.addAnonymous(obj, below=False, context=_context(context))
  _say(obj, "Anonymous node", made)
  return made

@hook(appliesTo=_canMark)
def expandProtoconnectives(obj:Any, context:HookContext) -> list[Any]:
  '''
  Expand the protoconnectives of the node's net (its nodes whose labels
  group others': see *expansion.expandProtoconnectives()*), and say which,
  and why any can't be.

  :returns: What was made: the member nodes, then the links.
  '''
  from . import expansion
  from .probes import name
  made, plan = expansion.expandProtoconnectives(obj.model, _context(context))
  net = _netName(obj.model) or str(obj.model.name)
  print(f"Expand protoconnectives in {net}: expanded {len(plan.groups)}"
        + (f" ({', '.join(name(g) for g in plan.groups)})" if plan.groups else "") + ".")
  for n, why in plan.kept:
    print(f"  kept {name(n)}: {why}")
  if plan.groups:
    _say(obj, "Expand protoconnectives", made)
  return made

@hook(appliesTo=_canMark)
def factor(obj:Any, context:HookContext) -> list[Any]:
  '''
  Factor the node's net: interpolate anonymous nodes for the links that
  some nodes each have to each of some others (see *expansion.factor()*).

  :returns: What was made: each anonymous node, then its links.
  '''
  from . import expansion
  from .probes import name
  made, plan = expansion.factor(obj.model, _context(context))
  net = _netName(obj.model) or str(obj.model.name)
  if not plan:
    print(f"Factor {net}: nothing to factor (no nodes each with a link to each of some others, in fewer links).")
    return made
  for f in plan:
    print(f"Factor {net}: {', '.join(name(n) for n in f.tails)} -- {f.kind} -- {', '.join(name(n) for n in f.heads)}: "
          f"{len(f.links)} links become {len(f.tails) + len(f.heads)}")
  _say(obj, "Factor", made)
  return made

def _specify(obj:Any, context:HookContext, what:str|None) -> None:
  '''Specify what the selected nodes (see *_targets()*) essentially are (see *existence.specify()*), as one command.'''
  from . import existence
  targets = _targets(obj, context)
  ctx = _context(context)
  if ctx is None:
    for mo in targets:
      existence.specify(mo, what)
    return
  from util.commandParser import CompositeCommandMgr
  with CompositeCommandMgr(ctx):
    for mo in targets:
      existence.specify(mo, what, ctx)

@hook(appliesTo=_canMark)
def essentiallyTop(obj:Any, context:HookContext) -> None:
  "Specify that the selected nodes are essentially top nodes: categorical existence (see *existence*)."
  from .existence import TOP
  _specify(obj, context, TOP)

@hook(appliesTo=_canMark)
def essentiallyBottom(obj:Any, context:HookContext) -> None:
  "Specify that the selected nodes are essentially bottom nodes: singular existence (see *existence*)."
  from .existence import BOTTOM
  _specify(obj, context, BOTTOM)

@hook(appliesTo=_canMark)
def unspecified(obj:Any, context:HookContext) -> None:
  "Take back what the selected nodes are specified to be essentially (see *existence*)."
  _specify(obj, context, None)

@hook(appliesTo=_canMark)
def showExistence(obj:Any, context:HookContext) -> Any:
  '''
  Show the existential status of the node's net's nodes (see
  *existence.report()*), in a window of its own.

  :returns: The window's *ReportWindow*.
  '''
  from sn.model.reasoner import EngineMissing
  from util.reportWindow import ReportWindow
  from . import existence
  model = obj.model
  window = ReportWindow(getattr(context.view, "canvas", None), f"Existence: {_netName(model) or model.name}", width=80)
  try:
    with window.busy():
      text = existence.report(model)
  except (EngineMissing, RuntimeError, ValueError) as ex:
    text = str(ex)
  window.show(text)
  return window

@hook(appliesTo=_canMark)
def abduce(obj:Any, context:HookContext) -> Any:
  '''
  KNet's abductive inference from the node (see *abduction*): the net
  reasoned over as it is (see *sn.model.reasoner.reason()*), and the marks
  that are the same whatever explains the node given to the nodes with none
  (as inferences: the next "reason" takes them out); and what it found said
  in the view's window's terminal.

  :returns: What it found (an *abduction.Abduction*), or None if it couldn't (said, as an error).
  '''
  from sn.model.reasoner import EngineMissing, reason
  from . import abduction
  model = obj.model
  try:
    reason(model, silent=True)
    found = abduction.abduce(model, obj)
  except (EngineMissing, RuntimeError, ValueError) as ex:
    logger.error(f"Abduce from {obj.name}: {ex}")
    return None
  abduction.markAbduced(found)
  print(found.report())
  return found
