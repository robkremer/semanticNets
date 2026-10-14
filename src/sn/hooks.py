'''
Hooks: Python functions named by attributes, so that a program that makes a
model (eg: pythonParser) can give its objects behaviour -- menu items, parts
of their tooltips, ... -- that lasts when the model's saved and read back.

An attribute names a hook by a *reference*: a string ``module:function``
(eg: ``sn.exampleApps.pythonParser.hooks:showSource``) -- a function, or a
class's method by its qualified name (``module:Class.method``). It's found
(*resolve()*) only when it's first used:

  - A function can be called only if it's been made a hook, by the *hook*
    decorator. So a model (one read from the web, say) can't name just any
    function (eg: ``os:system``): only those that are meant to be called this
    way.
  - If its module hasn't been imported (eg: the model's opened without the
    program that made it), it's imported -- but only if it's *trusted*: in sn
    itself, or in one of the modules or packages listed by the
    "hooks/trustedModules" preference (see *trusted()*).

A hook that can't be found, or fails, isn't an error to the user: it's logged
(once), and whatever uses it does without (see *call()*).

Each hook is called the same way: ``fn(obj, context)`` -- the model object
(eg: the node whose menu it's on), and a *HookContext* saying how it's used.
What it returns depends on what it's used for (eg: the text, for a tooltip).

Eg, in a module of its own (not a program's __main__: see *hook*)::

    from sn.hooks import hook, HookContext

    @hook
    def showSource(obj, context:HookContext) -> None:
      ...

and on a type: ``.menu/Show source`` = ``mypackage.hooks:showSource``.

Created on Oct 13, 2026

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
import importlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, TypeGuard
import sn
from sn import snPrefs

logger:sn.SNLogger = sn.getLogger(__name__)

TRUSTED_MODULES = ("sn",)
'''The modules and packages whose hooks can always be imported (see
*trusted()*): sn's own. Others are added by the "hooks/trustedModules"
preference.'''

TRUSTED_PREF = "hooks/trustedModules"
"The preference listing the modules and packages, besides sn, whose hooks can be imported."

_REF = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*:[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")

type Hook = Callable[[Any, "HookContext"], Any]

@dataclass
class HookContext:
  '''How a hook's being used: passed to it with the object (see *call()*).'''
  key:str = ""
  "The attribute that named it (eg: \".menu/Show source\"); empty if none did."
  vobject:Any = None
  "The object on the canvas it's used from (a *VObject*), if any."
  view:Any = None
  "The view it's used in (an *SNGView*), if any."
  selection:list[Any] = field(default_factory=list)
  '''What a menu item acts on (see *VObject.selectionOrSelf()*): the
  selected view objects, if the object it's on is one of them; else just
  that one. Empty if it isn't from a menu.'''
  extra:dict[str, Any] = field(default_factory=dict)
  "Anything else whatever calls it wants to say."

_hooks:dict[str, Hook] = {}
"The hooks: reference -> function."

_appliesTo:dict[str, Callable[[Any, HookContext], bool]] = {}
"The hooks that apply only to some objects: reference -> the test (see *hook()*, *applies()*)."

_problems:dict[str, str] = {}
'''Why references can't be called (see *problem()*), so that a module isn't
tried again each time: forgotten when a hook's made, or the trusted modules
change.'''

_reported:set[str] = set()
"The references a problem's been logged for (see *_report()*): each is logged once."

def reference(fn:Callable) -> str:
  '''
  :param fn: A function (or a class's method).
  :type fn: Callable
  :returns: The reference that names it: ``module:qualified.name``.
  :rtype: str
  '''
  return f"{fn.__module__}:{fn.__qualname__}"

def hook[F:Callable](fn:F|None=None, *, appliesTo:Callable[[Any, HookContext], bool]|None=None) -> Any:
  '''
  A decorator: makes *fn* a hook, so that attributes can name it (by its
  *reference()*). It should be in a module that's imported by its name (not a
  program's __main__, which is named "__main__" whatever the program is), so
  that it can be found again when its module's imported later on.

  Used as ``@hook``, or ``@hook(appliesTo=...)`` for one that only makes
  sense for some objects (see *applies()*): eg: a menu item set on a type for
  its instances, that means nothing on the type itself.

  :param fn: The function.
  :type fn: F | None
  :param appliesTo: Whether it applies to an object (used as *context* says):
    called as ``appliesTo(obj, context)``. Default: it applies to everything.
  :type appliesTo: Callable[[Any, HookContext], bool] | None
  :returns: *fn* itself; or, without *fn*, a decorator that makes it a hook.
  :rtype: Any
  '''
  if fn is None:
    return lambda f: hook(f, appliesTo=appliesTo)
  ref = reference(fn)
  if fn.__module__ == "__main__":
    logger.warning(f'The hook {ref} is in a program\'s __main__ module: models can\'t name it after the program\'s '
                   'ended (by its module\'s name, which is "__main__" for any program). Put it in a module of its own.')
  _hooks[ref] = fn
  if appliesTo is not None:
    _appliesTo[ref] = appliesTo
  else:
    _appliesTo.pop(ref, None)
  _problems.clear() # (its module may have failed to import before)
  _reported.discard(ref)
  return fn

def isReference(text:Any) -> TypeGuard[str]:
  '''
  :param text: An attribute's value.
  :type text: Any
  :returns: Whether it's written as a reference (``module:function``) --
    whether or not there's such a hook.
  :rtype: bool
  '''
  return isinstance(text, str) and _REF.fullmatch(text.strip()) is not None

def trustedModules() -> list[str]:
  '''
  :returns: The modules and packages whose hooks can be imported: sn's own
    (*TRUSTED_MODULES*), and those in the "hooks/trustedModules" preference.
  :rtype: list[str]
  '''
  pref = snPrefs.get(TRUSTED_PREF, [])
  return list(TRUSTED_MODULES) + [str(m).strip() for m in (pref if isinstance(pref, list) else []) if str(m).strip()]

def trusted(module:str) -> bool:
  '''
  :param module: A module's dotted name.
  :type module: str
  :returns: Whether it can be imported to find hooks in it: it's one of
    *trustedModules()*, or in one of them (eg: "a.b.c" is in "a.b", but
    "a.bc" isn't).
  :rtype: bool
  '''
  return any(module == t or module.startswith(t + ".") for t in trustedModules())

def problem(ref:str) -> str|None:
  '''
  Find the hook *ref* names, importing its module if it needs to (and may).

  :param ref: A reference: ``module:function``.
  :type ref: str
  :returns: Why it can't be called -- eg: it isn't a reference, its module
    isn't trusted, or there's no such hook -- or None if it can.
  :rtype: str | None
  '''
  ref = ref.strip() if isinstance(ref, str) else ref
  if not isReference(ref):
    return f'"{ref}" isn\'t a hook\'s name ("module:function").'
  if ref in _hooks:
    return None
  if ref not in _problems:
    why = _find(ref)
    if why is None:
      return None
    _problems[ref] = why
  return _problems[ref]

def _find(ref:str) -> str|None:
  '''
  :param ref: A reference that isn't a known hook.
  :type ref: str
  :returns: Why it can't be called; or None if importing its module made it a hook.
  :rtype: str | None
  '''
  module = ref.partition(":")[0]
  if not trusted(module):
    return (f'"{ref}" can\'t be used: its module, {module}, isn\'t trusted (it isn\'t in sn, nor in the '
            f'"{TRUSTED_PREF}" setting).')
  try:
    importlib.import_module(module)
  except Exception as ex:
    return f'"{ref}" can\'t be used: its module, {module}, couldn\'t be imported ({ex.__class__.__name__}: {ex}).'
  if ref in _hooks:
    return None
  return f'"{ref}" can\'t be used: there\'s no such hook (a function made one by @sn.hooks.hook) in {module}.'

def resolve(ref:str) -> Hook|None:
  '''
  :param ref: A reference: ``module:function``.
  :type ref: str
  :returns: The hook it names (importing its module if it needs to and may:
    see *problem()*), or None if it can't be called (logged once).
  :rtype: Hook | None
  '''
  why = problem(ref)
  if why is not None:
    _report(str(ref), why)
    return None
  return _hooks[ref.strip()]

def call(ref:str, obj:Any, context:HookContext|None=None, default:Any=None) -> Any:
  '''
  Call the hook *ref* names, on *obj*.

  :param ref: A reference: ``module:function``.
  :type ref: str
  :param obj: The model object it's for.
  :type obj: Any
  :param context: How it's being used.
  :type context: HookContext | None
  :param default: What to return if it can't be called, or fails.
  :type default: Any
  :returns: What it returns; or *default* if it can't be called, or raises an
    exception (logged: once, if it can't be called; each time, if it fails).
  :rtype: Any
  '''
  fn = resolve(ref)
  if fn is None:
    return default
  try:
    return fn(obj, context if context is not None else HookContext())
  except Exception:
    logger.warning(f'The hook "{ref.strip()}" failed (on {getattr(obj, "name", obj)!r}).', exc_info=True)
    return default

def applies(ref:str, obj:Any, context:HookContext|None=None) -> bool:
  '''
  :param ref: A reference: ``module:function``.
  :type ref: str
  :param obj: A model object.
  :type obj: Any
  :param context: How it'd be used.
  :type context: HookContext | None
  :returns: Whether the hook applies to *obj*: its *appliesTo* test (see
    *hook()*) says so, or it hasn't one. One that can't be called applies (to
    be shown, but disabled: see *resolve()*); one whose test fails doesn't
    (logged).
  :rtype: bool
  '''
  if resolve(ref) is None:
    return True
  test = _appliesTo.get(ref.strip())
  if test is None:
    return True
  try:
    return bool(test(obj, context if context is not None else HookContext()))
  except Exception:
    logger.warning(f'The hook "{ref.strip()}"\'s appliesTo test failed (on {getattr(obj, "name", obj)!r}).', exc_info=True)
    return False

def hookAttributes(obj:Any, prefix:str) -> dict[str, str]:
  '''
  :param obj: A model object (or anything with attributes: keys() and get()).
  :type obj: Any
  :param prefix: The start of the attributes' keys: eg: ".menu/".
  :type prefix: str
  :returns: Its attributes -- its own and those it inherits (eg: from its
    types) -- whose keys start with *prefix*, and whose values are references:
    key without the prefix (eg: "Show source") -> reference, sorted by key.
  :rtype: dict[str, str]
  '''
  ret:dict[str, str] = {}
  for key in sorted(k for k in obj.keys() if isinstance(k, str) and k.startswith(prefix) and len(k) > len(prefix)):
    value = obj.get(key, None)
    if isReference(value):
      ret[key[len(prefix):]] = value.strip()
    elif value is not None:
      _report(f"{key}={value!r}", f'The attribute "{key}" ({value!r}) isn\'t a hook\'s name ("module:function"): '
                                  'it\'s ignored.')
  return ret

def _report(key:str, message:str) -> None:
  '''
  :param key: What it's about: logged only the first time.
  :type key: str
  :param message: The problem.
  :type message: str
  '''
  if key not in _reported:
    _reported.add(key)
    logger.warning(message)

def _onTrustedModules(_key:str, _value:Any) -> None:
  _problems.clear()
  _reported.clear()
snPrefs.addCallback(TRUSTED_PREF, _onTrustedModules)
