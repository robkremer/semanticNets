'''
The model/view directory: the models (.snm) and views (.snv) in a list of
folders -- the *search path*, like the shell's PATH -- found without reading
them: only each file's header and the first few properties of the object in it
(its type, URL, and -- for a view -- its model) are read (see *peekFile()*).

The search path is a string of folders separated by ":" (*os.pathsep*), or by
new lines. A folder ending in "/**" includes all the folders below it, too
(see *parsePath()*). The window showing the directory is
*sn.view.graphics.directoryWindow.DirectoryWindow*.

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
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Iterator, Optional
from urllib.parse import urljoin, urlparse, unquote
from util.utils import fixURL, urlExists

EXTENSIONS = {".snm": "model", ".snv": "view"}
"The files the directory lists, and what's in them."

SUBFOLDERS = "/**"
"Ending a folder in the search path: and all the folders below it."

# ── The search path ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Folder:
  '''A folder in the search path.'''
  path:str
  "Its (absolute, user-expanded) path."
  subfolders:bool = False
  "Whether the folders below it are included too."

  def __str__(self) -> str:
    return self.path + (SUBFOLDERS if self.subfolders else "")

  def covers(self, folder:str) -> bool:
    '''
    :param folder: A folder's path.
    :type folder: str
    :returns: Whether the files in *folder* are in this part of the search path.
    :rtype: bool
    '''
    folder = _norm(folder)
    if folder == self.path:
      return True
    return self.subfolders and folder.startswith(self.path.rstrip(os.sep) + os.sep)

def _norm(path:str) -> str:
  return os.path.normpath(os.path.abspath(os.path.expanduser(path)))

def parsePath(text:str) -> list[Folder]:
  '''
  :param text: A search path: folders separated by ":" (*os.pathsep*) or new
    lines; each ending in "/**" if the folders below it are included too. "~"
    is the home folder. Blank parts are ignored, and so are repeats.
  :type text: str
  :returns: Its folders, in order.
  :rtype: list[Folder]
  '''
  ret:list[Folder] = []
  for part in re.split(rf"[{re.escape(os.pathsep)}\n]", text or ""):
    part = part.strip()
    if not part:
      continue
    subfolders = part.endswith(SUBFOLDERS) or part == "**"
    if subfolders:
      part = part[:-len(SUBFOLDERS)] if part.endswith(SUBFOLDERS) else ""
    folder = Folder(_norm(part or os.sep), subfolders)
    if folder not in ret:
      ret.append(folder)
  return ret

def formatPath(folders:list[Folder]) -> str:
  '''
  :param folders:
  :type folders: list[Folder]
  :returns: *folders* as a search path (see *parsePath()*).
  :rtype: str
  '''
  return os.pathsep.join(str(f) for f in folders)

def covered(folders:list[Folder], folder:str) -> bool:
  '''
  :param folders: A search path.
  :type folders: list[Folder]
  :param folder: A folder's path.
  :type folder: str
  :returns: Whether *folder*'s files are in the search path.
  :rtype: bool
  '''
  return any(f.covers(folder) for f in folders)

def withFolder(text:str, folder:str) -> str|None:
  '''
  :param text: A search path.
  :type text: str
  :param folder: A folder's path.
  :type folder: str
  :returns: *text* with *folder* added at the end, if it isn't covered by it
    already (see *covered()*); else None.
  :rtype: str | None
  '''
  folders = parsePath(text)
  if covered(folders, folder):
    return None
  return formatPath([*folders, Folder(_norm(folder))])

def filesIn(folders:list[Folder]) -> Iterator[str]:
  '''
  :param folders: A search path.
  :type folders: list[Folder]
  :returns: The paths of the models and views in *folders* (see
    *EXTENSIONS*), each once; not in hidden folders, nor hidden files. Folders
    that aren't there are skipped.
  :rtype: Iterator[str]
  '''
  seen:set[str] = set()
  def inFolder(path:str) -> Iterator[str]:
    try:
      names = sorted(os.listdir(path))
    except OSError:
      return
    for name in names:
      if name.startswith("."):
        continue
      full = os.path.join(path, name)
      if os.path.splitext(name)[1] in EXTENSIONS and os.path.isfile(full):
        real = os.path.realpath(full)
        if real not in seen:
          seen.add(real)
          yield full
  for f in folders:
    if f.subfolders:
      for top, dirs, _ in os.walk(f.path):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        yield from inFolder(top)
    else:
      yield from inFolder(f.path)

# ── Peeking into a file ─────────────────────────────────────────────────────

PEEKED = ("url", "model", "nextID")
"The properties of the object in a file that *peekFile()* reads (if they're there)."

def peekFile(path:str) -> dict[str, str]:
  '''
  Read just the start of a model or view file -- its header and the first
  properties of the object in it -- not the rest. (For a big model, that's a
  few kilobytes of megabytes.) Both XML formats (XML, XML2) are understood.

  :param path: The file's path.
  :type path: str
  :returns: "type": the class of the object in it (its fully qualified name);
    and those of *PEEKED*, and of the header's "previousURL", that are there.
  :rtype: dict[str, str]
  :raises ValueError: If it isn't a file of that kind (or can't be read).
  '''
  ret:dict[str, str] = {}
  stack:list[ET.Element] = []
  try:
    with open(path, "rb") as f:
      for event, elem in ET.iterparse(f, events=("start", "end")):
        if event == "start":
          stack.append(elem)
          depth = len(stack)
          # depth 1: the top strdict; 2: its "header"/"root" properties; 3: their
          # objects; 4: those objects' properties.
          if depth == 3 and elem.tag == "object" and stack[1].get("key") == "root":
            ret["type"] = elem.get("type", "")
          elif depth == 4 and elem.tag == "property" and stack[1].get("key") == "root" and elem.get("key") == "_db":
            break # (the objects in it: no further)
          continue
        stack.pop()
        depth = len(stack) + 1
        if depth == 4 and elem.tag == "property":
          section, key = stack[1].get("key"), elem.get("key")
          if (section == "root" and key in PEEKED) or (section == "header" and key == "previousURL"):
            value = elem.get("value")
            if value is None and len(elem) == 1: # (the XML format: the value's in an object in it)
              value = elem[0].get("value")
            if value is not None:
              ret[key] = value
        elif depth == 3 and stack[1].get("key") == "root":
          break # (the end of the object)
        if depth == 4:
          elem.clear() # (and what's in it: only the start of the file is kept in memory)
  except (ET.ParseError, OSError) as e:
    raise ValueError(f'Can\'t read "{path}": {e}') from e
  if "type" not in ret:
    raise ValueError(f'"{path}" isn\'t a model or view file.')
  return ret

# ── The directory's entries ─────────────────────────────────────────────────

def urlOf(path:str) -> str:
  '''
  :param path: A file's path.
  :type path: str
  :returns: Its URL, as the program makes it (see *fixURL()*): eg, so it can
    be found among the open windows' views.
  :rtype: str
  '''
  return fixURL(path, replaceExt=None, mode="w")[0]

def pathOf(url:str) -> str|None:
  '''
  :param url:
  :type url: str
  :returns: The path of the file at *url*, if it's a file URL; else None (eg:
    the system model, "sn:/sn.xml").
  :rtype: str | None
  '''
  u = urlparse(url)
  return unquote(u.path) if u.scheme == "file" else None

@dataclass
class Entry:
  '''A model or view in the directory.'''
  path:str
  "The file's path (for a model only a view refers to: where it should be)."
  kind:str
  '"model" or "view" (see *EXTENSIONS*).'
  url:str = ""
  "Its URL."
  modelURL:str|None = None
  "A view's model's URL (made absolute)."
  type:str = ""
  "The class of the object in it (its fully qualified name)."
  objects:int|None = None
  "About how many objects are in it (its nextID)."
  created:float|None = None
  "When the file was created (seconds since the epoch)."
  modified:float|None = None
  "When it was last changed."
  size:int|None = None
  "Its size in bytes."
  error:str|None = None
  "Why it couldn't be read (eg: it's missing); otherwise None."
  onPath:bool = True
  "Whether it's in the search path (else it's a model a view there refers to)."
  views:list[Entry] = field(default_factory=list)
  "A model's views (in the directory)."

  @property
  def name(self) -> str:
    "The file's name, without its extension."
    if self.path:
      return os.path.splitext(os.path.basename(self.path))[0]
    return self.url.rsplit("/", 1)[-1]

  @property
  def folder(self) -> str:
    return os.path.dirname(self.path) if self.path else ""

def scanFile(path:str, onPath:bool=True) -> Entry:
  '''
  :param path: A model's or view's file.
  :type path: str
  :param onPath: Whether it's in the search path (see *Entry.onPath*).
  :type onPath: bool
  :returns: Its entry: read with *peekFile()*. If it can't be read, the
    entry's *error* says why.
  :rtype: Entry
  '''
  ext = os.path.splitext(path)[1]
  entry = Entry(path=path, kind=EXTENSIONS.get(ext, "model"), onPath=onPath)
  try:
    entry.url = urlOf(path)
  except Exception:
    entry.url = "file://" + path
  try:
    st = os.stat(path)
  except OSError as e:
    entry.error = "missing" if isinstance(e, FileNotFoundError) else str(e)
    return entry
  entry.size, entry.modified = st.st_size, st.st_mtime
  entry.created = getattr(st, "st_birthtime", None) or st.st_ctime
  try:
    peeked = peekFile(path)
  except ValueError as e:
    entry.error = str(e)
    return entry
  entry.type = peeked["type"]
  kind = _kindOf(entry.type)
  if kind is not None:
    entry.kind = kind
  try:
    entry.objects = int(peeked["nextID"]) if "nextID" in peeked else None
  except ValueError:
    pass
  if entry.kind == "view" and peeked.get("model"):
    entry.modelURL = modelURLOf(entry.url, peeked["model"], peeked.get("url"))
  return entry

def _kindOf(typeName:str) -> str|None:
  '''
  :returns: "view" or "model": what the class named *typeName* is -- if it's
    a class that's loaded (nothing's imported to find out) -- else None.
  '''
  module, _, name = typeName.rpartition(".")
  cls = getattr(sys.modules.get(module), name, None)
  if not isinstance(cls, type):
    return None
  from sn.model.model import Model
  try:
    from sn.view.graphics.sngView import SNGView
    if issubclass(cls, SNGView):
      return "view"
  except ImportError:
    pass
  return "model" if issubclass(cls, Model) else None

def modelURLOf(viewURL:str, model:str, storedURL:str|None=None) -> str:
  '''
  :param viewURL: Where a view is.
  :type viewURL: str
  :param model: Its model's URL, as it's written in it: perhaps relative to it.
  :type model: str
  :param storedURL: The URL written in it (where it was when it was saved: if
    it's been copied, its model may have been left there -- see
    *PRDb.absoluteURL()*).
  :type storedURL: str | None
  :returns: The model's URL.
  :rtype: str
  '''
  from util.persistence.pRef import PRDb
  if not PRDb.isRelativeURL(model):
    return model
  ret = urljoin(viewURL, model)
  if storedURL and storedURL != viewURL and not urlExists(ret):
    alt = urljoin(storedURL, model)
    if urlExists(alt):
      return alt
  return ret

class Directory:
  '''
  The models and views in the search path (see *scan()*), and the models the
  views refer to that aren't in it.
  '''

  def __init__(self) -> None:
    self.entries:dict[str, Entry] = {}
    "The entries, by URL."

  def scan(self, folders:list[Folder]) -> Iterator[Entry]:
    '''
    Start afresh, and find the models and views in *folders*: one at a time,
    so a window can show them as they're found (and stay responsive).

    :param folders: The search path.
    :type folders: list[Folder]
    :returns: Each entry, as it's found: then the models views refer to that
      aren't in *folders*.
    :rtype: Iterator[Entry]
    '''
    self.entries = {}
    for path in filesIn(folders):
      entry = scanFile(path)
      self.entries[entry.url] = entry
      yield entry
    yield from self.addReferencedModels()

  def addReferencedModels(self) -> Iterator[Entry]:
    '''
    Add the models the views refer to that aren't in the directory (eg: in a
    folder that isn't in the search path), if they're files.

    :returns: Those added.
    :rtype: Iterator[Entry]
    '''
    for entry in list(self.entries.values()):
      url = entry.modelURL
      if entry.kind == "view" and url and url not in self.entries:
        path = pathOf(url)
        model = scanFile(path, onPath=False) if path else Entry(path="", kind="model", url=url, onPath=False)
        model.url = url
        self.entries[url] = model
        yield model

  def update(self, path:str) -> Entry|None:
    '''
    Read *path* again (eg: it's been saved, or deleted): its entry is replaced,
    or taken out if it's gone and no view refers to it.

    :param path:
    :type path: str
    :returns: Its new entry, if it has one.
    :rtype: Entry | None
    '''
    entry = scanFile(path)
    old = self.entries.get(entry.url)
    if entry.error == "missing" and not any(e.modelURL == entry.url for e in self.entries.values()):
      self.entries.pop(entry.url, None)
      return None
    if old is not None:
      entry.onPath = old.onPath
    self.entries[entry.url] = entry
    list(self.addReferencedModels())
    return entry

  def models(self) -> list[Entry]:
    '''
    :returns: The models, sorted by name (then folder), each with its views --
      sorted by name -- in its *views*. Views whose models aren't models in
      the directory (eg: the system model) come under an entry made for it.
    :rtype: list[Entry]
    '''
    models:dict[str, Entry] = {}
    for e in self.entries.values():
      if e.kind == "model":
        e.views = []
        models[e.url] = e
    for e in self.entries.values():
      if e.kind == "view":
        url = e.modelURL or ""
        if url not in models:
          models[url] = Entry(path=pathOf(url) or "", kind="model", url=url, onPath=False,
                              error=None if url else "the view doesn't say what its model is")
        models[url].views.append(e)
    for m in models.values():
      m.views.sort(key=lambda v: (v.name.lower(), v.path))
    return sorted(models.values(), key=lambda m: (m.name.lower(), m.path))

# ── Deleting ────────────────────────────────────────────────────────────────

def moveToTrash(path:str) -> None:
  '''
  Move a file to the Trash (on macOS, where the Finder's "Put Back" can
  restore it).

  :param path:
  :type path: str
  :raises OSError: If it can't be moved there (eg: on another platform:
    nothing's deleted then).
  '''
  if sys.platform != "darwin":
    raise OSError(f'Can\'t move "{path}" to the Trash on this platform: delete it yourself if you want it gone.')
  import ctypes, ctypes.util
  objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "/usr/lib/libobjc.dylib")
  ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
  objc.objc_getClass.restype = ctypes.c_void_p
  objc.objc_getClass.argtypes = [ctypes.c_char_p]
  objc.sel_registerName.restype = ctypes.c_void_p
  objc.sel_registerName.argtypes = [ctypes.c_char_p]
  send = objc.objc_msgSend
  def call(receiver, selector:bytes, *args, argtypes:tuple=(), restype=ctypes.c_void_p):
    send.restype = restype
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, *argtypes]
    return send(receiver, objc.sel_registerName(selector), *args)
  manager = call(objc.objc_getClass(b"NSFileManager"), b"defaultManager")
  string = call(objc.objc_getClass(b"NSString"), b"stringWithUTF8String:", os.fsencode(os.path.abspath(path)),
                argtypes=(ctypes.c_char_p,))
  url = call(objc.objc_getClass(b"NSURL"), b"fileURLWithPath:", string, argtypes=(ctypes.c_void_p,))
  error = ctypes.c_void_p()
  ok = call(manager, b"trashItemAtURL:resultingItemURL:error:", url, None, ctypes.byref(error),
            argtypes=(ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)), restype=ctypes.c_bool)
  if not ok:
    reason = "unknown error"
    if error.value:
      text = call(error.value, b"localizedDescription")
      if text:
        reason = (call(text, b"UTF8String", restype=ctypes.c_char_p) or b"").decode("utf-8", "replace") or reason
    raise OSError(f'Couldn\'t move "{path}" to the Trash: {reason}')
