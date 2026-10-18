'''
A graphical view's files, window menus and locking (*FilesMixin*): one of the
parts of *sn.view.graphics.sngView.SNGView* (see *viewBase*).

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
import os
import tkinter as tk
import sn
from sn.model.model import Model
from typing import Any
from util.utils import fixURL, urlExists
from sn.view.graphics.utils import addToMenuBar, addCheckToMenuBar, removeFromMenuBar
from util.persistence.pRef import PRDb
from sn.view.graphics.guiApp import Application
from sn.view.graphics.directoryWindow import noteSaved
from sn.view.graphics.viewBase import KEY_FIND, KEY_SELECT_ALL, KEY_PASTE, KEY_COPY_IMAGE, KEY_COPY, KEY_ZOOM_NORMAL, KEY_CUT, KEY_ZOOM_IN, KEY_ZOOM_FIT, KEY_ZOOM_OUT
from pathlib import Path
from sn.view.graphics.viewBase import ViewBase

logger:sn.SNLogger = sn.getLogger(__name__)

class FilesMixin(ViewBase):
  '''
  A view (*sn.view.graphics.sngView.SNGView*) and its files: saving it and its
  model (as, or a copy), the model's super-models (replacing one, opening one's
  view) and preferences, closing the model; the items it puts in the
  application's menus while its window has the focus; and locking it so it
  can't change its model.
  '''

  def doSaveView(self) -> None:
    '''
    Save this view. This is the target the "File | Save view" menu item
    (added/removed by *onWindowFocusIn()*/*onWindowFocusOut()* below) is
    wired to while this view's window is focused -- kept as its own method
    (rather than wiring the menu straight to *save()*) since Rob's planning
    sibling "Save model", "Save view as...", "Save model as..." commands
    here too, and this is the natural place for any save-view-specific
    behavior (confirmation, status message, ...) if/when it needs more than
    a plain save.
    '''
    self.save(overwrite=True)

  def doSaveModel(self) -> None:
    '''
    Save this view's model: the target of the "File | Save model" menu item
    (added/removed like "Save view": see *onWindowFocusIn()*). Not a model
    that's write-locked (eg: the system model).
    '''
    model = self.model
    if model is None:
      return
    if model.writeLocked():
      logger.warning(f'"{model.url}" is write-locked: not saved.')
      return
    model.save()
    logger.info(f'Saved "{model.url}".')
    noteSaved(model.url)

  def _saveCopy(self, what:str, db:Any, extension:str, filetypes:list[tuple[str, str]]) -> None:
    '''
    Ask for a file, and save a copy of *db* (this view, or its model) there.
    This window stays on the original -- not as a Mac "Save As" does -- so say
    so, in the log, and flash the terminal pane to draw attention to it.

    :param what: "view" or "model", for the messages.
    :param db: The view or model.
    :type db: SNGView | Model
    :param extension: Its files' extension, eg: ".snv".
    :param filetypes: For the file dialog.
    '''
    from tkinter import filedialog, messagebox
    current = fixURL(db.url)[0]
    path = current[len("file://"):] if current.startswith("file://") else ""
    filename = filedialog.asksaveasfilename(parent=self.window, title=f"Save a copy of the {what} as",
                                            defaultextension=extension, filetypes=filetypes,
                                            initialdir=os.path.dirname(path) or None,
                                            initialfile=f"{os.path.splitext(os.path.basename(path))[0]} copy{extension}" if path else "")
    if not filename:
      return
    copyURL = fixURL(filename, extension, replaceExt=None, mode="w")[0]
    if copyURL == current: # (its own file: just save it)
      db.save(overwrite=True)
      logger.info(f'Saved "{current}".')
      noteSaved(current)
      return
    try:
      db.save(saveas=filename, overwrite=True) # (the dialog has asked about replacing an existing file)
    except Exception as ex:
      messagebox.showerror("Save a copy", f"The {what} couldn't be saved as\n{filename}:\n\n{ex}", parent=self.window)
      return
    logger.warning(f'Saved a copy of the {what} as "{filename}". This window is still on the original, '
                   f'"{current}", and further changes go there.')
    noteSaved(copyURL)
    self.terminal.flash()

  def doSaveViewAs(self) -> None:
    '''
    Save a copy of this view in another file: the target of "File | Save view
    as..." (see *_saveCopy()*). This window stays on this view.
    '''
    self._saveCopy("view", self, ".snv", [("View files", "*.snv"), ("All files", "*.*")])

  def doSaveModelAs(self) -> None:
    '''
    Save a copy of this view's model in another file: the target of "File |
    Save model as..." (see *_saveCopy()*). This window stays on the model.
    '''
    if self.model is not None:
      self._saveCopy("model", self.model, ".snm", [("Model files", "*.snm"), ("All files", "*.*")])

  @staticmethod
  def _afterFileMenu() -> int:
    '''
    :returns: The menu bar position just after "File" (where "Edit" goes).
    '''
    try:
      bar = tk._default_root.nametowidget(tk._default_root["menu"]) # type: ignore[attr-defined,union-attr] # @UndefinedVariable
      return int(bar.index("File")) + 1
    except Exception:
      return 1

  def doReplaceSuperModel(self) -> None:
    '''
    "Edit | Replace super-model...": put another model in place of one of this
    view's model's super-models -- or of a model its objects refer to that
    isn't one (see *Model.unlistedModels()*) -- eg: an ontology's copy on the
    web in place of the local one (see *Model.replaceSuperModel()*); and show
    the same objects of the new one in its open views.
    '''
    from tkinter import messagebox
    from sn.view.graphics.replaceModelDialog import ReplaceModelDialog
    model = self.model
    if not self.isModelEditor():
      messagebox.showinfo("Replace super-model", self.lockedReason(), parent=self.window)
      return
    answer = ReplaceModelDialog(self.window, model).show()
    if answer is None:
      return
    old, where = answer
    try:
      new = Model.getDB(PRDb.absoluteURL(where, base=model.url))
      count = model.replaceSuperModel(old, new)
    except Exception as ex:
      messagebox.showerror("Replace super-model", f'Nothing was changed:\n\n{ex}', parent=self.window)
      return
    shown = 0
    for window in list(Application.current.windows.values()) if Application.current else [self.window]:
      view = getattr(window, "view", None)
      if view is not None and view.model is model:
        shown += view.modelObjectsReplaced(old, new)
    logger.warning(f'{model.name}: "{new.url}" is in place of "{old.url}": {count} reference{"" if count == 1 else "s"} '
                   f'changed, and {shown} object{"" if shown == 1 else "s"} in open views. Save the model (and the views) '
                   f'to keep it; its other views take it into account when they\'re opened.')
    self.terminal.flash()

  def doModelPreferences(self) -> None:
    '''
    "Edit | Model preferences...": edit this view's model's preferences (see
    *sn.model.modelPrefs*) -- just their values (their notes are their names'
    tooltips). Its super-models are shown as its *superDBs* are (see
    *Model.superModelPaths()*), "Add file..." choosing a model file, "Add URL..."
    taking its URL (eg: on the web: see *askModelURL()*), and set from
    the edited list (see *Model.setSuperModels()*): if that can't be done,
    nothing is changed, and the reasons are shown.
    '''
    from tkinter import filedialog, messagebox
    from util.attributeEditor import editAttrsBox
    from util.persistence.pRef import PRDb
    from sn.model.modelPrefs import SUPER_MODELS
    model = self.model
    if model is None or not hasattr(model, "prefs"):
      return
    if not self.isModelEditor():
      messagebox.showinfo("Model preferences", self.lockedReason(), parent=self.window)
      return
    modelFile = model.url[len("file://"):] if model.url.startswith("file://") else ""
    def chooseModel(parent:tk.Misc) -> str|None:
      path = filedialog.askopenfilename(parent=parent, title="Choose a model this one builds on",
                                        filetypes=[("Model files", "*.snm"), ("All files", "*.*")],
                                        initialdir=os.path.dirname(modelFile) or None)
      return PRDb.relativeURL(Path(path).as_uri(), base=model.url) if path else None
    def chooseModelURL(parent:tk.Misc) -> str|None:
      from sn.view.graphics.directoryWindow import askModelURL
      url = askModelURL(parent, "A model this one builds on", kinds=("model",),
                        prompt="The URL of a model this one builds on (eg: an ontology on the web):")
      return PRDb.relativeURL(url, base=model.url) if url else None
    updates = editAttrsBox(self.window, model.prefs, title=f"Preferences of {model.name}",
                           displayValues={SUPER_MODELS: model.superModelPaths()},
                           hideColumns=("type", "qualifiers", "note"),
                           listItemMakers={SUPER_MODELS: {"Add file...": chooseModel, "Add URL...": chooseModelURL}})
    if not updates:
      return
    for key, attr in updates.items():
      if key == SUPER_MODELS:
        if attr is None:
          continue
        try:
          model.setSuperModels(list(attr.value or [])) # type: ignore[arg-type]
          logger.info(f'{model.name}: super-models now {["sn"] + model.superModelPaths()}.')
        except ValueError as ex:
          messagebox.showerror("Model preferences", f"The super-models weren't changed:\n\n{ex}", parent=self.window)
      else:
        try:
          if attr is None:
            del model.prefs[key]
          else:
            model.prefs.setAttr(key, attr)
          model.setDirty()
        except Exception as ex:
          logger.exception(f'{model.name}: preference "{key}" couldn\'t be set.')
          messagebox.showerror("Model preferences", f'"{key}" couldn\'t be set:\n\n{ex}', parent=self.window)

  def doCloseModel(self) -> None:
    '''
    Close this view's model: the target of the "File | Close model" menu item
    (added/removed like "Save view": see *onWindowFocusIn()*). See
    *Application.closeModel()*.
    '''
    if self.model is not None:
      self.root.closeModel(self.model)

  def onWindowFocusIn(self) -> None:
    '''
    This view's *AppWindow* just gained focus -- add (or, if already
    present from some other cause, replace) the "File | Save view" menu
    item so it's wired to this view's *doSaveView()*.

    Called by *AppWindow._onWindowFocusIn()*. Since only one *AppWindow* is
    ever focused at a time, and each focused window's *SNGView* calls this
    on the way in, this is enough to guarantee "Save view" always targets
    whichever view the user is actually looking at -- no shared
    "currently active view" bookkeeping needed anywhere else.
    '''
    addToMenuBar("File|Save view", self.doSaveView)
    addToMenuBar("File|Save view as...", self.doSaveViewAs)
    addToMenuBar("File|Save model", self.doSaveModel)
    addToMenuBar("File|Save model as...", self.doSaveModelAs)
    addToMenuBar("File|Close model", self.doCloseModel, separatorBefore=True) # (after the saves)
    addToMenuBar("File|Open super model", menu=self._superModelsMenu())
    addToMenuBar("Edit|Cut", lambda: self._editAction("cut"), accelerator=KEY_CUT[1], cascadePositions={"Edit": self._afterFileMenu()})
    addToMenuBar("Edit|Copy", lambda: self._editAction("copy"), accelerator=KEY_COPY[1])
    addToMenuBar("Edit|Paste", lambda: self._editAction("paste"), accelerator=KEY_PASTE[1])
    addToMenuBar("Edit|Copy as picture", lambda: self._editAction("copy image"), accelerator=KEY_COPY_IMAGE[1])
    addToMenuBar("Edit|Select All", lambda: self._editAction("select all"), accelerator=KEY_SELECT_ALL[1])
    addToMenuBar("Edit|Find...", self.openSearchDialog, accelerator=KEY_FIND[1], separatorBefore=True)
    addToMenuBar("Edit|Model preferences...", self.doModelPreferences, separatorBefore=True)
    addToMenuBar("Edit|Replace super-model...", self.doReplaceSuperModel)
    self._editLockedVar().set(not self.isModelEditor()) # (the model may have been write-locked since)
    addCheckToMenuBar("Edit|Lock view", self._editLockedVar(), self._onLockViewItem, separatorBefore=True)
    addCheckToMenuBar("View|Layout panel", self._layoutPanelShown(), self._onLayoutPanelItem,
                      cascadePositions={"View": self._afterFileMenu() + 1}) # (after "Edit", made just above)
    addCheckToMenuBar("View|Reasoning toolbar", self._reasoningToolbarShown(),
                      lambda: self.showReasoningToolbar(self._reasoningToolbarShown().get()))
    addToMenuBar("View|Zoom In", self.zoomIn, accelerator=KEY_ZOOM_IN[1], separatorBefore=True)
    addToMenuBar("View|Zoom Out", self.zoomOut, accelerator=KEY_ZOOM_OUT[1])
    addToMenuBar("View|Normal Size", lambda: self.zoomAbout(1.0), accelerator=KEY_ZOOM_NORMAL[1])
    addToMenuBar("View|Zoom to Fit", self.zoomToFit, accelerator=KEY_ZOOM_FIT[1])
    bar = self.__dict__.get("_reasoningToolbar")
    if bar is not None:
      bar.refreshLock()

  def onWindowFocusOut(self) -> None:
    '''
    This view's *AppWindow* just lost focus -- or is being closed outright
    -- so withdraw the "File | Save view" menu item.

    Called by *AppWindow._onWindowFocusOut()* (via *_checkStillActive()*)
    when focus genuinely leaves this window, and by
    *Application._closeWindow()* when this window is closed (which isn't
    guaranteed to first fire a Tk focus-out event). Safe to call even if
    this view never added the item (e.g. its window was never focused) --
    *removeFromMenuBar()* is a no-op in that case.
    '''
    removeFromMenuBar("File|Save view")
    removeFromMenuBar("File|Save view as...")
    removeFromMenuBar("File|Save model")
    removeFromMenuBar("File|Save model as...")
    removeFromMenuBar("Edit|Cut")
    removeFromMenuBar("Edit|Copy")
    removeFromMenuBar("Edit|Paste")
    removeFromMenuBar("Edit|Copy as picture")
    removeFromMenuBar("Edit|Select All")
    removeFromMenuBar("Edit|Find...")
    removeFromMenuBar("Edit|Model preferences...")
    removeFromMenuBar("Edit|Replace super-model...")
    removeFromMenuBar("Edit|Lock view")
    removeFromMenuBar("File|Close model")
    removeFromMenuBar("File|Open super model")
    removeFromMenuBar("View|Layout panel")
    removeFromMenuBar("View|Reasoning toolbar")
    for item in ("Zoom In", "Zoom Out", "Normal Size", "Zoom to Fit"):
      removeFromMenuBar("View|" + item)

  SN_VIEW = "sn.snv"
  '''
  The file name of the system model's (sn's) view, in the sn.model package's
  folder: sn has no file of its own, so it's taken to be there -- with the base
  rules (see *superModelView()*).
  '''

  def _superModelsMenu(self) -> tk.Menu:
    '''
    :returns: The "File | Open super model" cascade: an item for each of this
      view's model's super-models (see *superModelView()*), nearest first.
    '''
    from sn.view.graphics.utils import _getMenuBar, getSubMenu
    from sn.model.reasoner import baseRulesSource
    old = self.__dict__.get("_superMenu")
    parent = getSubMenu(_getMenuBar(), "File") # type: ignore[arg-type]
    menu = self._superMenu = tk.Menu(parent, tearoff=0)
    supers = self.model.allSuperDBs()
    for db in supers:
      if not isinstance(db, Model):
        continue
      if db is self.model.TOP.model:
        label = "sn (the system model)"
      elif baseRulesSource(db) is not None:
        label = f"{os.path.splitext(db.name)[0]} (base rules)"
      else:
        label = PRDb.relativeURL(db.url, base=self.model.url)
      menu.add_command(label=label, command=lambda db=db: self.openSuperModel(db)) # type: ignore[misc]
    if not supers:
      menu.add_command(label="(none)", state=tk.DISABLED)
    if old is not None:
      self.canvas.after_idle(old.destroy) # (once it's no longer in the menu bar)
    return menu

  def superModelView(self, model:Model) -> tuple[str, str]:
    '''
    Where a super-model's view goes: next to its file, with the same name and
    ".snv" -- for the base rules, next to the file they come from (see
    *sn.model.reasoner.baseRulesSource()*), not the copy they're read from; for
    the system model (sn), which has no file, in the sn.model package's folder
    (see *SN_VIEW*).

    :param model: A super-model.
    :returns: (the URL of the model's file -- or "" for sn, which has none --
      and the URL of its view).
    '''
    import importlib.resources
    from pathlib import Path
    from sn.model.reasoner import baseRulesSource
    if model is self.model.TOP.model:
      return "", Path(str(importlib.resources.files("sn.model").joinpath(self.SN_VIEW))).as_uri()
    src = baseRulesSource(model) or model.url
    return src, fixURL(src, ".snv", replaceExt=True, mode="w")[0]

  def openSuperModel(self, model:Model) -> None:
    '''
    Open a window on one of this view's model's super-models (see
    *superModelView()*): its view, if it has one, or else a new one -- for the
    base rules, of the file they come from (read-only).

    :param model: The super-model.
    '''
    app = self.window._root() # type: ignore[attr-defined]
    src, viewURL = self.superModelView(model)
    if src and src != model.url and not urlExists(viewURL): # (the base rules: a view of the file they come from)
      model = Model(src)
    app.openViewOn(model, viewURL) #type: ignore[attr-defined]

  def isModelEditor(self) -> bool:
    '''
    :returns: Whether the model can be changed in this view: it isn't locked
      (see *setEditLocked()*), and the model isn't write-locked. Either way,
      the view itself can be (eg: moving things, or erasing them from view).
    '''
    return not self.__dict__.get("_editLocked", False) and not self.model.writeLocked()

  def lockedReason(self) -> str:
    '''
    :returns: Why the model can't be changed in this view (see
      *isModelEditor()*), for a message.
    '''
    if self.model.writeLocked():
      return f'"{self.model.name}" is write-locked: it can\'t be changed here.'
    return "This view is locked: it can't change the model. Click the pencil (bottom right) to unlock it."

  def editLocked(self) -> bool:
    '''
    :returns: Whether the user's locked this view, so it can't change the
      model (see *setEditLocked()*).
    '''
    return self.__dict__.get("_editLocked", False)

  def _editLockedVar(self) -> tk.BooleanVar:
    '''
    :returns: Whether the model can't be changed in this view (see
      *isModelEditor()*) -- what "Edit | Lock view" shows (and sets: see
      *_onLockViewItem()*).
    '''
    var = self.__dict__.get("_editLockedVarObj")
    if var is None:
      var = self._editLockedVarObj = tk.BooleanVar(self.canvas, value=not self.isModelEditor())
    return var

  def _onLockViewItem(self) -> None:
    '''
    "Edit | Lock view" was chosen: lock or unlock the view, as the pencil in
    the reasoning toolbar does (see *setEditLocked()*) -- not a write-locked
    model's.
    '''
    if not self.setEditLocked(self._editLockedVar().get()):
      self.window.bell()

  def setEditLocked(self, locked:bool=True) -> bool:
    '''
    Lock this view, so it can't change the model (see *isModelEditor()*) --
    only how it's shown -- or unlock it. Not other views of the model. It's
    saved with the view. A write-locked model's view can't be unlocked.

    :returns: Whether it's done (unlocking a write-locked model's view isn't).
    '''
    if not locked and self.model.writeLocked():
      logger.warning(self.lockedReason())
      self._editLockedVar().set(True)
      return False
    if locked != self.editLocked():
      self._editLocked = locked
      self.setDirty() # (saved with the view)
    self._editLockedVar().set(not self.isModelEditor())
    bar = self.__dict__.get("_reasoningToolbar")
    if bar is not None:
      bar.refreshLock()
    return True
