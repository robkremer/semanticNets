'''
Copying or moving models and their views as a unit -- eg, to put them on a web
site, or in another folder: which files go (see *FileSet*), and where (see
*FileSet.plan()*). The copying is *util.persistence.copyFiles*'s: each copy
refers to the other copies, and says where it is. (The model directory's
**Copy To...** and **Move To...**, and **File | Copy model and views to...**, ask
what's to be done: see *sn.view.graphics.copyDialog*.)

Created on Nov 18, 2026

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
from dataclasses import dataclass
from typing import Callable
from sn.model.directory import Directory, Entry, EXTENSIONS, scanFile, urlOf
from util.persistence.copyFiles import Copier, Copied, References, layout, references
from util.utils import urlPath

@dataclass
class Item:
  '''A model or view that may go (see *FileSet*).'''
  entry:Entry
  why:str
  '''Why it's listed: "picked", "a view of ...", "the model of ...", or "used
  by ..." (a model a file that goes refers to: eg, a super-model).'''
  needed:bool = False
  "Whether it's listed because a file that goes refers to it (it wasn't picked, nor is it a view of a model that was)."
  include:bool = True
  "Whether it goes."

  @property
  def path(self) -> str:
    return self.entry.path

  @property
  def name(self) -> str:
    "Its file's name (eg: \"family.snm\")."
    return os.path.basename(self.entry.path)

class FileSet:
  '''
  The files to copy or move together: the models and views picked (eg: in the
  model directory), the views of the models among them, and the models they
  refer to (their super-models, a view's model: see *gather()*) -- each
  listed with why (see *Item*), and whether it goes.
  '''

  def __init__(self, directory:Directory, picked:list[Entry], move:bool=False,
               progress:Callable[[str, int, int], None]|None=None):
    '''
    :param directory: The model directory: where the picked models' views are
      found (see *Entry.views*), and the models they refer to.
    :param picked: The models and views picked: those that are files on this
      computer (not on the web, nor missing) are listed.
    :param move: Whether they're to be moved, not copied: then models listed
      only because they're referred to don't go, unless they're ticked (see
      *Item.include*) -- they're left where they are, and the moved files
      refer to them there.
    :param progress: Called as each file's looked through (see *gather()*):
      with its path, how many have been, and how many are known of so far.
    '''
    self.directory = directory
    self.move = move
    self.items:list[Item] = []
    self._byPath:dict[str, Item] = {}
    self._references:dict[str, References] = {}
    self._entries:dict[str, Entry] = {os.path.realpath(e.path): e for e in directory.entries.values() if e.path}
    self.base:str|None = None
    "The folder of the first file picked: files in it (or below it) keep their places relative to it (see *plan()*)."
    self.gather(picked, progress)

  # ── What goes ────────────────────────────────────────────────────────────

  def gather(self, picked:list[Entry], progress:Callable[[str, int, int], None]|None=None) -> None:
    '''
    List *picked*: each model with its views, and each view with its model;
    then -- looking through each listed file (see *references()*) -- the
    models and views they refer to, and those they refer to, and so on (eg:
    their super-models).
    '''
    for e in picked:
      name = os.path.basename(e.path or e.url)
      self._add(e, "picked")
      if e.kind == "model":
        for v in e.views:
          self._add(v, f'a view of "{name}"')
      else:
        model = self.entryFor(e.modelURL) if e.modelURL else None
        if model is not None:
          self._add(model, f'the model of "{name}"', needed=True)
    if self.base is None and self.items:
      self.base = os.path.dirname(self.items[0].path)
    done = 0
    while done < len(self.items):
      item = self.items[done]
      if progress is not None:
        progress(item.path, done, len(self.items))
      for url in self.references(item.path).local:
        entry = self.entryFor(url)
        if entry is not None:
          self._add(entry, f'used by "{item.name}"', needed=True)
      done += 1

  def _add(self, entry:Entry, why:str, needed:bool=False) -> None:
    if not entry.path or entry.error or entry.remote:
      return
    key = os.path.realpath(entry.path)
    if key in self._byPath:
      return
    item = Item(entry, why, needed=needed, include=not (needed and self.move))
    self.items.append(item)
    self._byPath[key] = item
    if self.base is None and why == "picked":
      self.base = os.path.dirname(entry.path)

  def entryFor(self, url:str) -> Entry|None:
    '''
    :returns: The model or view at *url*, if it's a file on this computer that
      is one (by its extension: see *EXTENSIONS*): the directory's entry for
      it, or else one made for it (see *scanFile()*).
    '''
    path = urlPath(url)
    if not path or os.path.splitext(path)[1] not in EXTENSIONS:
      return None
    entry = self._entries.get(os.path.realpath(path))
    if entry is None:
      entry = self.directory.entries.get(url) or scanFile(path, onPath=False)
      self._entries[os.path.realpath(path)] = entry
    return entry

  def references(self, path:str) -> References:
    ''':returns: What the file at *path* refers to (see *util.persistence.copyFiles.references()*): looked through once.'''
    if path not in self._references:
      try:
        self._references[path] = references(path, EXTENSIONS)
      except OSError:
        self._references[path] = References(adjustable=False)
    return self._references[path]

  def included(self) -> list[Item]:
    ''':returns: Those that go (see *Item.include*).'''
    return [i for i in self.items if i.include]

  # ── What they refer to that doesn't go ───────────────────────────────────

  def outside(self) -> dict[str, set[str]]:
    '''
    :returns: The files on this computer that those going refer to, but don't
      go -- each with the names of those that refer to it. The copies refer to
      them where they are: they're found on this computer, but not elsewhere
      (eg: on a web site).
    '''
    going = {os.path.realpath(i.path) for i in self.included()}
    ret:dict[str, set[str]] = {}
    for i in self.included():
      for url in self.references(i.path).local:
        path = urlPath(url) or url
        if os.path.realpath(path) not in going:
          ret.setdefault(path, set()).add(i.name)
    return ret

  def missing(self) -> dict[str, set[str]]:
    ''':returns: The files on this computer that those going refer to, but aren't there: each with the names of those that refer to it.'''
    ret:dict[str, set[str]] = {}
    for i in self.included():
      for url in self.references(i.path).missing:
        ret.setdefault(urlPath(url) or url, set()).add(i.name)
    return ret

  def web(self) -> set[str]:
    ''':returns: The URLs of the files elsewhere (eg: "https:...") those going refer to: they're referred to there, as they are.'''
    return {url for i in self.included() for url in self.references(i.path).web}

  def unadjustable(self) -> list[Item]:
    ''':returns: Those going that are in a format whose references can't be adjusted (see *References.adjustable*): copied as they are.'''
    return [i for i in self.included() if not self.references(i.path).adjustable]

  # ── Where they go ────────────────────────────────────────────────────────

  def plan(self, folder:str) -> dict[str, str]:
    '''
    :param folder: Where they go.
    :returns: Each of those going (its path), and where it goes: those in the
      folder of the first file picked (see *base*), or below it, keep their
      places relative to it; the others go in *folder* itself (see *layout()*).
    '''
    return layout([i.path for i in self.included()], folder, self.base)

  def copier(self, folder:str, servedFrom:str|None=None) -> Copier:
    '''
    :param folder: Where they go (see *plan()*).
    :param servedFrom: If they're to be put on a web site: the URL *folder*
      will be there (see *Copier*).
    :raises ValueError: If it can't be done: eg, a file would be copied onto
      itself.
    '''
    return Copier(self.plan(folder), EXTENSIONS, servedFrom=servedFrom or None, folder=folder)

def copyFiles(fileSet:FileSet, folder:str, servedFrom:str|None=None,
              progress:Callable[[str, int, int], None]|None=None) -> list[Copied]:
  '''
  Copy those of *fileSet* that go (see *Item.include*) to *folder* (see
  *FileSet.plan()*). (Moving them is copying them, then putting the originals
  in the Trash: see *sn.view.graphics.copyDialog*.)

  :param servedFrom: If they're to be put on a web site: the URL *folder* will
    be there.
  :returns: What was done with each.
  :raises ValueError: If it can't be done (see *FileSet.copier()*).
  :raises OSError: If a file can't be read, or its copy written.
  '''
  return fileSet.copier(folder, servedFrom).run(progress)

def copyURLs(copied:list[Copied]) -> dict[str, str]:
  ''':returns: The URL of each file copied (as the program makes it: see *urlOf()*), and its copy's.'''
  return {urlOf(c.source): urlOf(c.copy) for c in copied}
