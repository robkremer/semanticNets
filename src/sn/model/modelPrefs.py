'''
A model's own preferences (see *ModelPrefs*), saved with it, and edited with
"Edit | Model preferences..." -- as the application's are in *sn.snPrefs*.

Created on Oct 4, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
from typing import Any, override
from util.attribute import AttributedObject, Attribute, VAR_DEFAULTED

SUPER_MODELS = "superModels"
"The preference listing a model's super-models (see *Model.superModelPaths()*)."

MODEL_PREFS:dict[str, tuple[Any, Any, str]] = {
  # key: (type, default, note)
  SUPER_MODELS: ("list[str]", [],
    "The models this one builds on: their contents are used as though they were its own (eg: the reasoner "
    "reasons over them, and their rules apply), though they aren't changed through it. In order: a name that "
    "could mean objects in more than one is looked up in the first first. Paths are relative to this model's "
    "file. (The system model, sn, always comes first, and isn't listed.)"),
}
'''
A model's preferences: key -> (type, default, note), as *sn.PREFS* is the
application's. Each is in a model's *ModelPrefs* from the start (see
*initModelPrefs()*).

*superModels* is shown, and edited, but its value isn't kept here: a model's
super-models are its *superDBs* (saved by *PRDb*) -- see *Model.superModelPaths()*
and *Model.setSuperModels()*.
'''

class ModelPrefs(AttributedObject):
  '''
  A model's preferences: a flat set of attributes (no supertypes), saved with
  the model (see *Model.prefs*).
  '''

  @override
  def getSupers[T:AttributedObject](self) -> list[T]:
    '''
    :returns: None: preferences don't inherit.
    :rtype: list[T]
    '''
    return []

  @override
  def isIndividual(self) -> bool:
    '''
    :returns: False (as for *sn.SNPrefs*: so their types are their own).
    :rtype: bool
    '''
    return False

def initModelPrefs(prefs:ModelPrefs) -> None:
  '''
  Put each of *MODEL_PREFS* in *prefs*: with its default, if it isn't there;
  and its note, unless the user has written their own (as *sn.initPrefs()*).

  :param prefs: A model's preferences.
  :type prefs: ModelPrefs
  '''
  for key, (typ, default, note) in MODEL_PREFS.items():
    attr = dict.get(prefs, key) # (the stored Attribute itself: getAttr() gives a copy)
    if attr is None:
      prefs.setAttr(key, Attribute(list(default) if isinstance(default, list) else default, typ, VAR_DEFAULTED, note))
    elif not (getattr(attr, "userNote", False) and attr.note):
      attr.note = note
      attr.userNote = False
