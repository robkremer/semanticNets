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
    (*clearMarks()*): take back the marks asserted on them.

A mark is two attributes, *MARK_TRUE* and *MARK_FALSE*, each saying how the
node got it: "asserted" (by these menu items, or a net's file), or by the
kernel's rules -- "included" (it's included by something true), "excluded"
(it excludes something true), "coexcluded" (it coexcludes something false),
or "irrelevant" (Rep Plus's name: it includes something false). The
reasoners conclude those (see knet.snm's mark rules); "reason" shows them.

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
               "coexcluded": "#0000ff", "definition": "#ff0000", "necessary": "#ff0000", "default": "#800080"}
'''Each way a node gets a mark -> its bar's colour: Rep Plus's mark kinds'
(Gaines's paper's: brown asserted, black and blue true, grey and green
false). Another (eg: a net's own mark kind) is drawn black.'''

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
