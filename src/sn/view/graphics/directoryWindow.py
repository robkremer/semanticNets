'''
The model directory window: the models and views in the folders of the search
path (see *sn.model.directory*), each model with its views under it, to open
(or open read-only) or move to the Trash; and a progress bar for opening them
(see *sn.view.graphics.progress*). It's the application's main window (see
*Application.showDirectory()*, and the Window menu's "Model Directory").

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
import logging
import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import TYPE_CHECKING, Callable, Iterator
import sn
from sn import snPrefs
from sn.model.directory import Directory, Entry, Folder, parsePath, formatPath, withFolder, pathOf, \
  peekFile, moveToTrash
from sn.view.graphics import progress
from sn.model.model import Model
from util.attribute import Attribute, VAR_DEFAULTED
from util.persistence.pRef import PRDb
from util.tooltip import CreateToolTip
from util.utils import ownDialog

if TYPE_CHECKING:
  from sn.view.graphics.guiApp import Application

logger = logging.getLogger(__name__)

PATH_PREF = "gui/directoryPath"
"The preference holding the search path (see *sn.model.directory.parsePath()*)."

TIME_FORMAT = "%Y-%m-%d %H:%M"

def searchPath() -> list[Folder]:
  ''':returns: The search path's folders (see *PATH_PREF*).'''
  text = snPrefs.get(PATH_PREF, "")
  return parsePath(text if isinstance(text, str) else "")

def setSearchPath(text:str) -> None:
  '''
  :param text: The new search path (see *sn.model.directory.parsePath()*).
  :type text: str
  '''
  snPrefs[PATH_PREF] = text

def noteFolderOf(url:str) -> bool:
  '''
  A model or view at *url* has been opened, made or saved: add its folder to
  the search path if it isn't in it already.

  :param url:
  :type url: str
  :returns: Whether it was added.
  :rtype: bool
  '''
  path = pathOf(url)
  if not path or isTemporary(path):
    return False
  current = snPrefs.get(PATH_PREF, "")
  new = withFolder(current if isinstance(current, str) else "", os.path.dirname(path))
  if new is None:
    return False
  setSearchPath(new)
  return True

def isTemporary(path:str) -> bool:
  '''
  :param path:
  :type path: str
  :returns: Whether *path* is in a temporary folder (eg: a test's): its folder
    isn't added to the search path.
  :rtype: bool
  '''
  import tempfile
  real = os.path.realpath(path)
  temps = {os.path.realpath(tempfile.gettempdir()), os.path.realpath("/tmp"), os.path.realpath("/var/folders")}
  return any(real == t or real.startswith(t.rstrip(os.sep) + os.sep) for t in temps)

def seedSearchPath(urls:list[str]) -> None:
  '''
  If the search path is empty (eg: the directory's never been used), start it
  with the folders of *urls* (eg: the files opened recently) that are there.

  :param urls:
  :type urls: list[str]
  '''
  current = snPrefs.get(PATH_PREF, "")
  if isinstance(current, str) and current.strip():
    return
  for url in urls:
    path = pathOf(url) if "://" in url else url
    if path and os.path.isdir(os.path.dirname(path)):
      noteFolderOf(url if "://" in url else "file://" + path)

def sizeText(size:int|None) -> str:
  '''
  :param size: A number of bytes.
  :type size: int | None
  :returns: It, readably: eg, "12 KB", "3.4 MB".
  :rtype: str
  '''
  if size is None:
    return ""
  for unit, scale in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
    if size >= scale:
      value = size / scale
      return f"{value:.1f} {unit}" if value < 10 else f"{value:.0f} {unit}"
  return f"{size} B"

def isDark(widget:tk.Misc) -> bool:
  ":returns: Whether macOS is in dark mode (never, elsewhere)."
  try:
    return bool(widget.tk.call("tk::unsupported::MacWindowStyle", "isdark", widget.winfo_toplevel()))
  except tk.TclError:
    return False

RECENT_URLS_PREF = ".recentURLs"
"The URLs typed most recently (see *askModelURL()*): offered again. (Hidden from Settings: it starts with \".\".)"

def askModelURL(parent:tk.Misc, title:str, kinds:tuple[str, ...]=("model", "view"), prompt:str="") -> str|None:
  '''
  Ask for the URL of a model or view -- eg: on the web -- offering the URLs
  typed recently, and checking there's one of *kinds* there before it's taken
  (see *sn.model.directory.urlProblem()*).

  :param parent:
  :type parent: tk.Misc
  :param title:
  :type title: str
  :param kinds: "model", "view", or both.
  :type kinds: tuple[str, ...]
  :param prompt:
  :type prompt: str
  :returns: The URL, or None if cancelled.
  :rtype: str | None
  '''
  from util.urlDialog import askURL
  from sn.model.directory import urlProblem
  recent = snPrefs.get(RECENT_URLS_PREF, [])
  recent = [u for u in recent if isinstance(u, str)] if isinstance(recent, list) else []
  url = askURL(parent, title, prompt=prompt or f'The URL of a {" or ".join(kinds)} (eg: "https://..."):',
               recent=recent, check=lambda u: urlProblem(u, kinds))
  if url:
    snPrefs[RECENT_URLS_PREF] = Attribute([url, *[u for u in recent if u != url]][:20], list, VAR_DEFAULTED,
                                          "The URLs typed most recently (for models and views).")
  return url

def noteSaved(url:str) -> None:
  '''
  A model or view has been saved at *url*: add its folder to the search path
  (see *noteFolderOf()*), and show it as it is now in the model directory.

  :param url:
  :type url: str
  '''
  from sn.view.graphics.guiApp import Application
  app = Application.current
  if app is not None:
    app.noteFile(url)
  else:
    noteFolderOf(url)


def repaint(widget:tk.Misc) -> None:
  '''
  Redraw what's changed on the screen now -- while the event loop is held up
  (eg: by reading a file). That runs the callbacks queued to run when it's
  idle (*after_idle()*), too: those queued by a view being read are harmless
  then (its objects' first drawings are put off till it's all read: see
  *SNGView._drawAllAfterRead()*).

  :param widget: Any widget.
  :type widget: tk.Misc
  '''
  widget.update_idletasks()


class DirectoryPane(ttk.Frame):
  '''
  The directory: a toolbar, the list of models and views, a line saying more
  about the one selected, and a progress bar (shown while something's being
  scanned, opened or drawn).
  '''

  MODEL_SHADE = ("#e9eef5", "#2e3540")
  "The background of the models' rows (setting them off from their views'): in light mode, and dark."

  COLUMNS = (("status", "", 72), ("objects", "Objects", 72), ("size", "Size", 72), ("location", "Location", 300),
             ("modified", "Modified", 125), ("created", "Created", 125))
  "The list's columns, after the name: (id, heading, width)."

  def __init__(self, app:Application):
    '''
    :param app: The application: the pane fills its main window.
    :type app: Application
    '''
    super().__init__(app, padding=6)
    self.app = app
    self.directory = Directory()
    self._scanning:Iterator[Entry]|None = None
    self._rowEntries:dict[str, Entry] = {}

    bar = ttk.Frame(self)
    bar.pack(fill=tk.X, pady=(0, 6))
    def button(text:str, command:Callable[[], None], tipText:str) -> ttk.Button:
      b = ttk.Button(bar, text=text, command=command)
      b.pack(side=tk.LEFT, padx=(0, 4))
      CreateToolTip(b, tipText, wrapLength=300)
      return b
    self.openButton = button("Open", self.openSelected, "Open the selected view, or the selected model in its default view (or double-click it).")
    self.openReadOnlyButton = button("Open Read-only", lambda: self.openSelected(readOnly=True),
      "Open it with its model write-locked: it can't be changed (nor saved).")
    self.deleteButton = button("Move to Trash", self.deleteSelected,
      "Move the selected model or view to the Trash (and, for a model, offer to move its views too).")
    button("Folders...", self.editFolders, "Which folders are searched for models and views (the search path).")
    button("Rescan", self.rescan, "Look through the folders again.")

    listFrame = ttk.Frame(self)
    listFrame.pack(fill=tk.BOTH, expand=True)
    self.tree = ttk.Treeview(listFrame, columns=[c[0] for c in self.COLUMNS], selectmode="browse")
    self.tree.heading("#0", text="Model / view")
    self.tree.column("#0", width=220, stretch=True)
    for cid, heading, width in self.COLUMNS:
      self.tree.heading(cid, text=heading)
      self.tree.column(cid, width=width, stretch=cid == "location", anchor=tk.E if cid in ("objects", "size") else tk.W)
    scroll = ttk.Scrollbar(listFrame, orient=tk.VERTICAL, command=self.tree.yview)
    self.tree.configure(yscrollcommand=scroll.set)
    self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    self.tree.tag_configure("missing", foreground="gray55")
    self.tree.tag_configure("elsewhere", foreground="gray35")
    self.tree.tag_configure("open", font=("TkDefaultFont", 0, "bold"))
    self.tree.tag_configure("model", background=self.MODEL_SHADE[1 if isDark(self) else 0])
    self.tree.bind("<<TreeviewSelect>>", lambda _e: self._selectionChanged())
    self.tree.bind("<Double-1>", lambda _e: self.openSelected())
    self.tree.bind("<Return>", lambda _e: self.openSelected())

    self.infoLabel = ttk.Label(self, foreground="gray35", anchor=tk.W, justify=tk.LEFT)
    self.infoLabel.pack(fill=tk.X, pady=(6, 0))
    self.progressFrame = ttk.Frame(self)
    self.progressLabel = ttk.Label(self.progressFrame, anchor=tk.W)
    self.progressLabel.pack(fill=tk.X)
    self.progressBar = ttk.Progressbar(self.progressFrame, mode="determinate", maximum=1000)
    self.progressBar.pack(fill=tk.X)
    self._selectionChanged()

  # ── Scanning ──────────────────────────────────────────────────────────────

  def rescan(self) -> None:
    '''
    Look through the search path's folders afresh: a few at a time, so the
    window stays responsive (see *_scanSome()*).
    '''
    self._scanning = self.directory.scan(searchPath())
    self.infoLabel.configure(text="Looking through the folders...")
    self._scanSome()

  def _scanSome(self) -> None:
    scanning = self._scanning
    if scanning is None:
      return
    until = time.monotonic() + 0.05
    count = len(self.directory.entries)
    try:
      while time.monotonic() < until:
        next(scanning)
        count += 1
    except StopIteration:
      self._scanning = None
      self.refresh()
      return
    self.infoLabel.configure(text=f"Looking through the folders... ({count} found)")
    self.after(1, self._scanSome)

  def noteFile(self, path:str) -> None:
    '''
    *path* -- a model or view -- has been saved, made or deleted: show it as
    it is now.

    :param path:
    :type path: str
    '''
    self.directory.update(path)
    self.refresh()

  # ── The list ──────────────────────────────────────────────────────────────

  def refresh(self) -> None:
    '''
    Show the directory's entries afresh (eg: which are open), keeping what's
    selected and which models are expanded.
    '''
    tree = self.tree
    selected = tree.selection()
    expanded = {iid for iid in tree.get_children() if tree.item(iid, "open")}
    first = not self._rowEntries
    tree.delete(*tree.get_children())
    self._rowEntries = {}
    for model in self.directory.models():
      iid = self._row("", model)
      for view in model.views:
        self._row(iid, view)
      tree.item(iid, open=first or iid in expanded)
    keep = [iid for iid in selected if tree.exists(iid)]
    if keep:
      tree.selection_set(keep)
      tree.see(keep[0])
    self._selectionChanged()

  def _row(self, parent:str, entry:Entry) -> str:
    iid = f"{entry.kind}:{entry.url}"
    status, tags = self._status(entry)
    name = entry.name if entry.url else "(no model)"
    def when(t:float|None) -> str:
      return time.strftime(TIME_FORMAT, time.localtime(t)) if t else ""
    objects = "" if entry.objects is None else f"{entry.objects:,}" if entry.objectsExact else f"\u2264 {entry.objects:,}"
    self.tree.insert(parent, tk.END, iid=iid, text=name, tags=(*tags, entry.kind),
                     values=(status, objects, sizeText(entry.size), entry.location, when(entry.modified), when(entry.created)))
    self._rowEntries[iid] = entry
    return iid

  def _status(self, entry:Entry) -> tuple[str, tuple[str, ...]]:
    '''
    :returns: What to say about *entry* in the list, and its tags: whether it's
      open, read-only, missing, ...
    '''
    tags:list[str] = []
    if not entry.onPath:
      tags.append("elsewhere")
    if entry.error:
      tags.append("missing")
      return ("missing" if entry.error == "missing" else "unreadable"), tuple(tags)
    if entry.kind == "view":
      if entry.url in self.app.windows:
        return "open", (*tags, "open")
      return "", tuple(tags)
    model = PRDb.AllDBs.get(entry.url)
    if model is None:
      return ("system" if entry.url.startswith("sn:") else ""), tuple(tags)
    shown = any(w.view is not None and w.view.model is model for w in self.app.windows.values())
    status = "read-only" if model.writeLocked() else "open" if shown else "" # (else just in memory: see deleteSelected())
    return status, (*tags, "open") if shown else tuple(tags)

  def selectedEntry(self) -> Entry|None:
    ''':returns: The entry selected, if there is one.'''
    selection = self.tree.selection()
    return self._rowEntries.get(selection[0]) if selection else None

  def _selectionChanged(self) -> None:
    if self._scanning is not None: # (see _scanSome())
      return
    entry = self.selectedEntry()
    openable = entry is not None and not entry.error and bool(entry.path or entry.remote)
    for b in (self.openButton, self.openReadOnlyButton):
      b.state(["!disabled"] if openable else ["disabled"])
    self.deleteButton.state(["!disabled"] if openable and entry is not None and entry.path else ["disabled"]) # (not a remote one)
    if entry is None:
      folders = searchPath()
      self.infoLabel.configure(text=f"{len(self.directory.entries)} models and views in {len(folders)} folder"
                               f"{'' if len(folders) == 1 else 's'} (see Folders...)." if folders else
                               "No folders are searched yet: see Folders... (the folders of the models and views you open are added).")
      return
    lines = [entry.url or "(the view doesn't say what its model is)"]
    details = []
    if entry.error:
      details.append(entry.error if entry.error != "missing" else "the file's missing")
    if entry.objects is not None and entry.objectsExact:
      details.append(f"{entry.objects:,} objects")
    elif entry.objects is not None:
      details.append(f"at most {entry.objects:,} objects (as many as have been made in it: fewer if some were deleted -- "
                     "saving it again makes it say exactly)")
    if entry.remote:
      details.append("remote: opened read-only")
    if not entry.onPath and entry.kind == "model":
      details.append("not in the searched folders: a view there refers to it")
    if details:
      lines.append(", ".join(details))
    self.infoLabel.configure(text="\n".join(lines))

  # ── Opening ───────────────────────────────────────────────────────────────

  def openSelected(self, readOnly:bool=False) -> None:
    '''
    Open the selected view, or the selected model in its default view.

    :param readOnly: Whether its model's to be write-locked (see *PRDb.writeLocked()*).
    :type readOnly: bool
    '''
    entry = self.selectedEntry()
    if entry is None or entry.error or not (entry.path or entry.remote):
      return
    self.app.openEntry(entry, readOnly=readOnly)

  # ── Deleting ──────────────────────────────────────────────────────────────

  def deleteSelected(self) -> None:
    '''
    Move the selected model or view to the Trash, once the user agrees -- and,
    for a model with views, its views too if they say so. Nothing that's open
    is moved.
    '''
    entry = self.selectedEntry()
    if entry is None or entry.error or not entry.path:
      return
    top = self.winfo_toplevel()
    files = [entry]
    if entry.kind == "model":
      views = [v for v in entry.views if not v.error and v.path]
      if views:
        names = "\n  ".join(os.path.basename(v.path) for v in views)
        answer = messagebox.askyesnocancel(sn.NAME, f'Move "{os.path.basename(entry.path)}" to the Trash?\n\n'
                                           f'Its views:\n  {names}\n\nMove its views to the Trash too?',
                                           icon=messagebox.WARNING, parent=top)
        if answer is None:
          return
        if answer:
          files += views
      elif not messagebox.askokcancel(sn.NAME, f'Move "{os.path.basename(entry.path)}" to the Trash?', parent=top):
        return
    elif not messagebox.askokcancel(sn.NAME, f'Move "{os.path.basename(entry.path)}" to the Trash?', parent=top):
      return
    openNow = [f for f in files if self._isOpen(f)]
    if openNow:
      messagebox.showerror(sn.NAME, "Close these first (they're open):\n\n  " +
                           "\n  ".join(os.path.basename(f.path) for f in openNow) + "\n\nNothing was moved.", parent=top)
      return
    used = [f for f in files if f.kind == "model" and self._usedBy(f)]
    if used:
      messagebox.showerror(sn.NAME, "\n\n".join(f'"{os.path.basename(f.path)}" is used by other models that are open: '
                           + ", ".join(self._usedBy(f)) for f in used) + "\n\nNothing was moved.", parent=top)
      return
    for f in files: # (models that were open, still in memory: forgotten -- they're going)
      model = PRDb.AllDBs.get(f.url) if f.kind == "model" else None
      if isinstance(model, Model):
        try:
          model.unload()
        except RuntimeError as e:
          messagebox.showerror(sn.NAME, f'"{os.path.basename(f.path)}" can\'t be moved: {e}\n\nNothing was moved.', parent=top)
          return
    failed = []
    for f in files:
      try:
        moveToTrash(f.path)
      except OSError as e:
        failed.append(str(e))
    for f in sorted(files, key=lambda f: f.kind != "view"): # (views first: a model's kept, as missing, while a view refers to it)
      self.directory.update(f.path)
    self.refresh()
    if failed:
      messagebox.showerror(sn.NAME, "\n\n".join(failed), parent=top)

  def _isOpen(self, entry:Entry) -> bool:
    '''
    :returns: Whether *entry* is shown in a window: a view, or a model one of
      the windows' views is of. (A model that was, but isn't now, stays in
      memory: it isn't open.)
    '''
    if entry.kind == "view":
      return entry.url in self.app.windows
    return any(w.view is not None and w.view.model.url == entry.url for w in self.app.windows.values())

  def _usedBy(self, entry:Entry) -> list[str]:
    ''':returns: The names of the models in memory that *entry*, a model, is a super-model of (see *Model.dependents()*).'''
    model = PRDb.AllDBs.get(entry.url)
    if model is None or not hasattr(model, "dependents"):
      return []
    return sorted({os.path.basename(url) for kind, url in model.dependents() if kind == "model"})

  # ── The search path ───────────────────────────────────────────────────────

  def editFolders(self) -> None:
    '''
    Edit the search path in a dialog (see *FoldersDialog*); rescan if it's changed.
    '''
    dialog = FoldersDialog(self.winfo_toplevel(), searchPath())
    folders = dialog.show()
    if folders is not None and folders != searchPath():
      setSearchPath(formatPath(folders))
      self.rescan()

  # ── Progress ──────────────────────────────────────────────────────────────

  def _showProgress(self, label:str|None, done:int, total:int|None) -> None:
    '''
    Show how a job's going (see *sn.view.graphics.progress*), or hide the
    progress bar (*label* None). It's drawn there and then (the job's
    holding up the event loop).
    '''
    if label is None:
      self.progressBar.stop()
      self.progressFrame.pack_forget() # (not repainted now: the event loop does it -- what's next may be its idle callbacks)
      return
    if not self.progressFrame.winfo_ismapped():
      self.progressFrame.pack(fill=tk.X, pady=(6, 0))
    self.progressLabel.configure(text=label)
    if total:
      self.progressBar.configure(mode="determinate", value=min(1000, int(1000 * done / total)))
    else:
      self.progressBar.configure(mode="indeterminate")
      self.progressBar.step(25)
    repaint(self)


class FoldersDialog(tk.Toplevel):
  '''
  The search path: one folder per line, each ending in ``/**`` if the folders
  below it are included too. Modal: *show()* returns the folders, if OK'd.
  '''

  def __init__(self, parent:tk.Misc, folders:list[Folder]):
    super().__init__(parent)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.parent = parent
    self.title("Folders searched for models and views")
    self.result:list[Folder]|None = None
    frame = ttk.Frame(self, padding=8)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, foreground="gray35", wraplength=460, justify=tk.LEFT,
              text='One per line: a folder (a path, or a "file:" URL) -- ending in "/**" to search the folders below '
                   'it too -- or the URL of a model or view elsewhere (eg: "https://..."). The folders of the models '
                   'and views you open, make or save are added.').pack(anchor=tk.W, pady=(0, 6))
    self.text = tk.Text(frame, width=64, height=10, wrap=tk.NONE, undo=True)
    self.text.pack(fill=tk.BOTH, expand=True)
    self.text.insert("1.0", "\n".join(str(f) for f in folders))
    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(8, 0))
    self.subfolders = tk.BooleanVar(value=True)
    ttk.Button(buttons, text="Add Folder...", command=self.addFolder).pack(side=tk.LEFT)
    ttk.Checkbutton(buttons, text="with its subfolders", variable=self.subfolders).pack(side=tk.LEFT, padx=6)
    ttk.Button(buttons, text="OK", command=self.ok, default="active").pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.RIGHT)
    self.bind("<Escape>", lambda _e: self.destroy())

  def addFolder(self) -> None:
    folder = filedialog.askdirectory(parent=self, title="Add a folder to search for models and views", mustexist=True)
    if folder:
      text = self.text.get("1.0", tk.END).rstrip("\n")
      line = str(Folder(folder, self.subfolders.get()))
      self.text.delete("1.0", tk.END)
      self.text.insert("1.0", (text + "\n" if text else "") + line)

  def ok(self) -> None:
    self.result = parsePath(self.text.get("1.0", tk.END))
    self.destroy()

  def show(self) -> list[Folder]|None:
    ''':returns: The folders, if OK'd; else None.'''
    try:
      self.wait_visibility()
      self.grab_set()
      self.lift()
      self.text.focus_set()
    except tk.TclError:
      pass
    self.wait_window()
    return self.result


class ReadProgress:
  '''
  Reports the reading of models and views -- *PRDb.readProgress* -- as
  progress (see *sn.view.graphics.progress*): one job per file, its total how
  many objects its header says it has.
  '''

  def __init__(self) -> None:
    self._totals:dict[str, int|None] = {}
    self._current:list[str] = []

  def __call__(self, db:PRDb, count:int) -> None:
    url = db.url
    if url in self._current[:-1]: # (an outer file, read in bits around an inner one: the inner one's shown)
      return
    if not self._current or self._current[-1] != url:
      if url not in self._totals:
        total = None
        path = pathOf(url)
        if path:
          try:
            peeked = peekFile(path)
            total = int(peeked.get("objects") or peeked.get("nextID") or 0) or None # (its head says how many; an old file, about how many)
          except (ValueError, OSError):
            pass
        self._totals[url] = total
      self._current.append(url)
      what = "view" if url.endswith(".snv") else "model"
      progress.begin(f'Reading {what} "{os.path.basename(pathOf(url) or url)}"...', self._totals[url])
    progress.step(count)

  def finish(self) -> None:
    "End the jobs begun for the files read."
    if self._current:
      progress.end(len(self._current))
    self._current = []
