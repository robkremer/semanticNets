'''
Copying or moving models and views as a unit: the model directory's **Copy
To...** and **Move To...**, and **File | Copy model and views to...** (see
*copyOrMove()*). What's picked goes with its views and the models it uses (see
*sn.model.fileCopies.FileSet*); a dialog (*CopyDialog*) shows them, each to be
ticked or not, and asks where they're to go -- and, if that folder is to be
put on a web site, where it'll be there. The copies refer to one another, and
say where they are (see *util.persistence.copyFiles*). Moving is copying,
then putting the originals in the Trash.

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
import logging
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import TYPE_CHECKING, Callable
import sn
from sn import snPrefs
from sn.model.directory import Directory, Entry, urlOf
from sn.model.fileCopies import FileSet, Item, copyFiles
from sn.view.graphics import progress
from util.attribute import Attribute, VAR_DEFAULTED
from util.persistence.copyFiles import Copied
from util.persistence.pRef import PRDb
from util.platformSupport import TRASH_NAME, moveToTrash
from util.utils import ownDialog

if TYPE_CHECKING:
  from sn.view.graphics.guiApp import Application

logger = logging.getLogger(__name__)

FOLDER_PREF = ".copyFolder"
"The folder models and views were last copied or moved to. (Hidden from Settings: it starts with \".\".)"

SERVED_PREF = ".servedFolders"
'''The folders copied to that are put on web sites, and where: each "folder ->
URL" (see *CopyDialog*): offered again when the folder's chosen.'''

def servedFrom(folder:str) -> str:
  ''':returns: Where *folder* was last said to be on the web (see *SERVED_PREF*), or "".'''
  entries = snPrefs.get(SERVED_PREF, [])
  for entry in entries if isinstance(entries, list) else []:
    f, arrow, url = str(entry).partition(" -> ")
    if arrow and os.path.normpath(f) == os.path.normpath(folder):
      return url.strip()
  return ""

def noteServedFrom(folder:str, url:str) -> None:
  "Remember that *folder* is on the web at *url* (or isn't, if it's \"\"): see *SERVED_PREF*."
  entries = snPrefs.get(SERVED_PREF, [])
  entries = [e for e in entries if isinstance(e, str) and os.path.normpath(e.partition(" -> ")[0]) != os.path.normpath(folder)] \
            if isinstance(entries, list) else []
  if url:
    entries.insert(0, f"{folder} -> {url}")
  snPrefs[SERVED_PREF] = Attribute(entries[:20], list, VAR_DEFAULTED,
                                   "The folders models were copied to that are put on web sites, and where.")


class CopyDialog(tk.Toplevel):
  '''
  Where models and views are to be copied or moved to: a folder -- and, if
  it's to be put on a web site, the URL it'll be at -- and which of them go
  (see *FileSet*): each listed with why, and where it'll be in the folder;
  click its box (or press Space) to leave it out, or put it back. Below them:
  what the copies will refer to that doesn't go, and anything else to know.
  Modal: *show()* returns the folder and URL, if OK'd.
  '''

  BOX = 13
  "The size of the tick boxes (pixels)."

  def __init__(self, parent:tk.Misc, files:FileSet, move:bool|None=None,
               blocked:Callable[[Item], str|None]|None=None):
    '''
    :param files: What's picked, and the rest that may go with it.
    :param move: Whether they're to be moved, not copied: by default, as *files* says (see *FileSet.move*).
    :param blocked: Why a file can't go (eg: it's open, when moving), if it can't.
    '''
    super().__init__(parent)
    ownDialog(self, parent)
    self.files = files
    self.move = move = files.move if move is None else move
    self.blocked = blocked or (lambda _i: None)
    self.result:tuple[str, str|None]|None = None
    verb = "Move" if move else "Copy"
    picked = [i for i in files.items if i.why == "picked"]
    what = f'"{picked[0].name}"' if len(picked) == 1 else f"{len(picked)} files"
    withWhat = ("with its views and the models it uses" if picked[0].entry.kind == "model" else "with its model and the models it uses") \
               if len(picked) == 1 else "with the models' views and the models they use"
    self.title(f"{verb} {what} to a folder")
    frame = ttk.Frame(self, padding=8)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, foreground="gray35", wraplength=640, justify=tk.LEFT,
              text=f'{verb} {what} to a folder, {withWhat} (eg: super-models). The '
                   f'{"moved files" if move else "copies"} refer to one another, not to the originals, and say where they are.'
                   + (f' The originals go to the {TRASH_NAME}; what they use stays where it is, unless you tick it.' if move else '')
                   + ' Click a file\'s box to leave it out, or put it back.').pack(anchor=tk.W, pady=(0, 6))
    grid = ttk.Frame(frame)
    grid.pack(fill=tk.X)
    grid.columnconfigure(1, weight=1)
    self.folder = tk.StringVar(value=str(snPrefs.get(FOLDER_PREF, "") or ""))
    self.served = tk.StringVar(value=servedFrom(self.folder.get()) if self.folder.get() else "")
    ttk.Label(grid, text="Folder:").grid(row=0, column=0, sticky=tk.W)
    self.folderEntry = ttk.Entry(grid, textvariable=self.folder, width=60)
    self.folderEntry.grid(row=0, column=1, sticky=tk.EW, padx=4)
    ttk.Button(grid, text="Choose...", command=self.chooseFolder).grid(row=0, column=2)
    ttk.Label(grid, text="On the web at:").grid(row=1, column=0, sticky=tk.W, pady=(4, 0))
    ttk.Entry(grid, textvariable=self.served, width=60).grid(row=1, column=1, sticky=tk.EW, padx=4, pady=(4, 0))
    ttk.Label(grid, foreground="gray35", text="(if the folder's put on a web site)").grid(row=1, column=2, sticky=tk.W, pady=(4, 0))

    listFrame = ttk.Frame(frame)
    listFrame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
    self.tree = ttk.Treeview(listFrame, columns=("why", "to"), selectmode="browse", height=min(12, max(4, len(files.items) + 1)))
    self.tree.heading("#0", text="File")
    self.tree.heading("why", text="Why")
    self.tree.heading("to", text="Goes to")
    self.tree.column("#0", width=220, stretch=True)
    self.tree.column("why", width=220, stretch=True)
    self.tree.column("to", width=220, stretch=True)
    self.ticked, self.unticked = self._box(True), self._box(False)
    scroll = ttk.Scrollbar(listFrame, orient=tk.VERTICAL, command=self.tree.yview)
    self.tree.configure(yscrollcommand=scroll.set)
    self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    self.tree.tag_configure("stays", foreground="gray55")
    for n, item in enumerate(files.items):
      self.tree.insert("", tk.END, iid=str(n), text=item.name)
    self.tree.bind("<Button-1>", self._clicked)
    self.tree.bind("<space>", lambda _e: self.toggle(self.tree.focus()))

    self.notes = ttk.Label(frame, wraplength=640, justify=tk.LEFT)
    self.notes.pack(fill=tk.X, pady=(8, 0))
    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(8, 0))
    self.okButton = ttk.Button(buttons, text=verb, command=self.ok, default="active")
    self.okButton.pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
    self.bind("<Escape>", lambda _e: self.destroy())
    self.bind("<Return>", lambda _e: self.ok())
    self.folder.trace_add("write", lambda *_a: self.refresh())
    self.served.trace_add("write", lambda *_a: self.refresh())
    self.refresh()

  # ── The list ──────────────────────────────────────────────────────────────

  def _box(self, ticked:bool) -> tk.PhotoImage:
    ''':returns: A tick box, ticked or not (drawn: a font may not have a tick).'''
    n = self.BOX
    img = tk.PhotoImage(master=self, width=n, height=n)
    img.put("#ffffff", to=(1, 1, n - 1, n - 1))
    for edge in ((0, 0, n, 1), (0, n - 1, n, n), (0, 0, 1, n), (n - 1, 0, n, n)):
      img.put("#808080", to=edge)
    if ticked:
      for x, y in ((3, 6), (4, 7), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4), (10, 3)): # (a tick, two pixels thick)
        img.put("#1f5fbf", to=(x, y, x + 1, y + 2))
    return img

  def _clicked(self, event:tk.Event) -> str|None:
    if self.tree.identify_column(event.x) == "#0" and self.tree.identify_region(event.x, event.y) in ("tree", "cell"):
      self.toggle(self.tree.identify_row(event.y))
      return "break"
    return None

  def toggle(self, iid:str) -> None:
    "Leave the file in row *iid* out, or put it back."
    if not iid:
      return
    item = self.files.items[int(iid)]
    item.include = not item.include
    self.refresh()

  def folderPath(self) -> str:
    ''':returns: The folder typed or chosen: its full path (or "" if none's been).'''
    text = self.folder.get().strip()
    if text.startswith("file:"):
      from util.utils import urlPath
      text = urlPath(text) or ""
    return os.path.abspath(os.path.expanduser(text)) if text else ""

  def chooseFolder(self) -> None:
    current = self.folderPath()
    folder = filedialog.askdirectory(parent=self, title=f"{'Move' if self.move else 'Copy'} to which folder?",
                                     initialdir=current if current and os.path.isdir(current) else None, mustexist=False)
    if folder:
      self.folder.set(folder)
      self.served.set(servedFrom(folder))

  def refresh(self) -> None:
    '''
    Show where each file will go, and what's to be known: what the copies
    will refer to that doesn't go, ... -- and whether it can be done.
    '''
    folder = self.folderPath()
    plan = self.files.plan(folder) if folder else {}
    for n, item in enumerate(self.files.items):
      to = os.path.relpath(plan[item.path], folder) if item.path in plan else ""
      self.tree.item(str(n), image=self.ticked if item.include else self.unticked, values=(item.why, to),
                     tags=() if item.include else ("stays",))
    notes, problem = self.notesFor(folder, plan)
    self.notes.configure(text="\n".join(notes), foreground="firebrick" if problem else "")
    self.okButton.state(["disabled"] if problem else ["!disabled"])

  def notesFor(self, folder:str, plan:dict[str, str]) -> tuple[list[str], bool]:
    '''
    :returns: What's to be known before they're copied (or moved) to *folder*,
      as *plan* says; and whether it can't be done (eg: there's no folder, or
      a file would be copied onto itself).
    '''
    files = self.files
    going = files.included()
    if not going:
      return ["Nothing's ticked to go."], True
    blocked = [(i.name, why) for i in going for why in [self.blocked(i)] if why]
    if blocked:
      return ["These can't be moved: " + "; ".join(f"{n} ({why})" for n, why in blocked)], True
    if not folder:
      return ["Choose the folder they go to."], True
    served = self.served.get().strip()
    if served and not served.lower().startswith(("http://", "https://")):
      return ['The web address should start "https://" (or "http://"); or leave it empty.'], True
    try:
      files.copier(folder, served or None)
    except ValueError as e:
      return [str(e)], True
    notes:list[str] = []
    outside = files.outside()
    if outside:
      where = "a web site" if served else "another computer"
      notes.append(f"Used, but not going -- the {'moved files' if self.move else 'copies'} refer to them where they are, "
                   f"so they're found on this computer but not on {where}:")
      notes += [f"    {os.path.basename(p)} (in {os.path.dirname(p)}), used by {', '.join(sorted(by))}" for p, by in outside.items()]
    missing = files.missing()
    if missing:
      notes.append("Referred to, but not there: " + "; ".join(f"{os.path.basename(p)} (by {', '.join(sorted(by))})"
                                                            for p, by in missing.items()))
    web = files.web()
    if web:
      notes.append(f"On the web, and referred to there: {', '.join(sorted(web))}.")
    same = [i.name for i in files.unadjustable()]
    if same:
      notes.append(f"Copied as they are (not in an XML format, so what they refer to can't be changed): {', '.join(same)}.")
    there = [os.path.relpath(plan[i.path], folder) for i in going if os.path.exists(plan[i.path])]
    if there:
      notes.append(f"Already in the folder, and replaced: {', '.join(there)}.")
    if not notes:
      notes.append(f"Everything they refer to goes with them{' (or is on the web)' if web else ''}.")
    return notes, False

  # ── OK ────────────────────────────────────────────────────────────────────

  def ok(self) -> None:
    if "disabled" in self.okButton.state():
      return
    folder = self.folderPath()
    if not os.path.isdir(folder):
      if not messagebox.askokcancel(self.title(), f'There\'s no folder "{folder}". Make it?', parent=self):
        return
      try:
        os.makedirs(folder)
      except OSError as e:
        messagebox.showerror(self.title(), f'"{folder}" couldn\'t be made:\n\n{e}', parent=self)
        return
    plan = self.files.plan(folder)
    there = [os.path.relpath(dst, folder) for dst in plan.values() if os.path.exists(dst)]
    if there and not messagebox.askokcancel(self.title(), f"These are in the folder already:\n\n  " + "\n  ".join(there)
                                            + "\n\nReplace them?", icon=messagebox.WARNING, parent=self):
      return
    served = self.served.get().strip()
    snPrefs[FOLDER_PREF] = Attribute(folder, str, VAR_DEFAULTED, "The folder models and views were last copied or moved to.")
    noteServedFrom(folder, served)
    self.result = (folder, served or None)
    self.destroy()

  def show(self) -> tuple[str, str|None]|None:
    ''':returns: The folder, and where it'll be on the web (or None), if OK'd.'''
    try:
      self.wait_visibility()
      self.grab_set()
      self.lift()
      self.folderEntry.focus_set()
    except tk.TclError:
      pass
    self.wait_window()
    return self.result


def _openThing(app:Application, entry:Entry) -> object|None:
  ''':returns: The model or view of *entry*, if it's in memory (eg: open in a window).'''
  if entry.kind == "view":
    window = app.windows.get(entry.url)
    return getattr(window, "view", None)
  return PRDb.AllDBs.get(entry.url)

def copyOrMove(app:Application, directory:Directory, picked:list[Entry], move:bool=False, parent:tk.Misc|None=None,
               blocked:Callable[[Item], str|None]|None=None) -> list[Copied]|None:
  '''
  Copy (or move) *picked* -- with their views, and the models they use -- to
  a folder, once the user says where (see *CopyDialog*). Models and views
  with unsaved changes are offered for saving first. Moving is copying, then
  putting the originals in the Trash, and taking each model moved to be where
  it is now wherever it's referred to where it was (see the
  "model/urlAliases" setting): eg, by a model that uses it that stayed.

  :param directory: The model directory (see *FileSet*).
  :param picked: The models and views picked.
  :param parent: What the dialogs are over.
  :param blocked: Why a file can't go, if it can't (see *CopyDialog*).
  :returns: What was copied (and so moved), or None if nothing was.
  '''
  parent = parent or app
  verb = "Move" if move else "Copy"
  def looking(path:str, done:int, total:int) -> None:
    progress.begin(f'Looking through "{os.path.basename(path)}"...', total)
    progress.step(done)
    progress.end()
  files = FileSet(directory, picked, move=move, progress=looking)
  if not files.items:
    messagebox.showinfo(verb, "Only models and views that are files on this computer (and are there) can be "
                        f"{'moved' if move else 'copied'}.", parent=parent)
    return None
  answer = CopyDialog(parent, files, move=move, blocked=blocked).show()
  if answer is None:
    return None
  folder, served = answer
  going = files.included()
  unsaved = [(i, thing) for i in going for thing in [_openThing(app, i.entry)]
             if thing is not None and getattr(thing, "isDirty", lambda: False)() and not getattr(thing, "writeLocked", lambda: False)()]
  if unsaved:
    save = messagebox.askyesnocancel(verb, "These have changes that haven't been saved:\n\n  " + "\n  ".join(i.name for i, _ in unsaved)
                                     + f"\n\nSave them first? (If not, they're {'moved' if move else 'copied'} as they were last saved"
                                     + (", and the changes are lost" if move else "") + ".)", parent=parent)
    if save is None:
      return None
    if save:
      for _i, thing in unsaved:
        thing.save(overwrite=True) # type: ignore[attr-defined]
  if move: # (models only in memory -- their windows closed -- forgotten: they're going)
    from sn.model.model import Model
    for i in going:
      model = PRDb.AllDBs.get(i.entry.url) if i.entry.kind == "model" else None
      if isinstance(model, Model):
        try:
          model.unload()
        except RuntimeError as e:
          messagebox.showerror(verb, f'"{i.name}" can\'t be moved: {e}\n\nNothing was moved.', parent=parent)
          return None
  def copying(path:str, done:int, total:int) -> None:
    progress.step(done, total)
  try:
    with progress.task(f'{"Moving" if move else "Copying"} {len(going)} file{"" if len(going) == 1 else "s"}...', len(going)):
      copied = copyFiles(files, folder, served, progress=copying)
  except (OSError, ValueError) as e:
    messagebox.showerror(verb, f"They couldn't all be copied:\n\n{e}" + ("\n\nNothing was moved." if move else ""), parent=parent)
    return None
  failed:list[str] = []
  if move:
    aliases = []
    for c in copied:
      try:
        moveToTrash(c.source)
      except OSError as e:
        failed.append(str(e))
        continue
      if os.path.splitext(c.source)[1] == ".snm":
        aliases.append(f"{urlOf(c.source)} -> {urlOf(c.copy)}")
    if aliases:
      typ, _default, note = sn.PREFS["model/urlAliases"]
      current = snPrefs.get("model/urlAliases", [])
      current = [a for a in current if isinstance(a, str)] if isinstance(current, list) else []
      snPrefs["model/urlAliases"] = Attribute(current + aliases, typ, VAR_DEFAULTED, note) # (applied: see sn._onURLAliases())
  app.noteFile(*[urlOf(c.copy) for c in copied]) # (their folder in the search path; shown in the directory)
  if move and app.directoryPane is not None:
    for c in copied:
      app.directoryPane.directory.update(c.source)
    app.directoryPane.refresh()
  where = f' (on the web at "{served}")' if served else ""
  logger.info(f'{"Moved" if move else "Copied"} {len(copied)} file{"" if len(copied) == 1 else "s"} to "{folder}"{where}: '
              + ", ".join(os.path.relpath(c.copy, folder) for c in copied) + "."
              + (" References to the moved models where they were are taken to be to them where they are now (see the "
                 "model/urlAliases setting)." if move and any(c.source.endswith(".snm") for c in copied) else ""))
  if failed:
    messagebox.showerror(verb, f"They were copied, but these couldn't be put in the {TRASH_NAME}:\n\n" + "\n\n".join(failed), parent=parent)
  return copied
