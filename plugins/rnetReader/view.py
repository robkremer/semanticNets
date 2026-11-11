'''
The rnet Reader's front end: turn a Rep Plus net (".rnet") into a Semantic
Nets model and view, and open the view in the editor. (The Tools menu's
"Rep Plus Net Reader...": see the plugin's *register()*.)

It's a dialog (see *ReaderDialog*): the net file, and the model and view to
make of it -- by default, for "<name>.rnet", "<name>.snm" and "<name>.snv",
in the folder they were last made in (or else beside the net). "Go" makes them
(see *convert()*) -- asking first if they're there already, and replacing
them -- and opens the view: the net as CNet drew it (see *showNet()*).

Created on Nov 11, 2026

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
from typing import Any, Callable
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from util.utils import fixURL, ownDialog
from sn.view.graphics.guiApp import Application
from sn.view.graphics.sngView import SNGView
from sn.view.graphics.vnodes import VNode
from .rnet import parse
from .reader import Built, buildModel

TITLE = "Rep Plus Net Reader"

SCALE = 1.5
"How much bigger the view is than CNet's picture: room for the editor's bigger text."

MARGIN = 20
"Where CNet's top left corner is in the view."

def defaultPaths(rnetPath:str, folder:str|None=None) -> tuple[str, str]:
  '''
  :param rnetPath: A net file.
  :param folder: Where to make its files, if not beside it.
  :returns: The model and view files made from it, by default: "<name>.snm" and "<name>.snv".
  '''
  base = os.path.splitext(os.path.basename(rnetPath))[0]
  where = folder if folder else os.path.dirname(os.path.abspath(rnetPath))
  return os.path.join(where, base + ".snm"), os.path.join(where, base + ".snv")

def showNet(view:SNGView, built:Built, scale:float=SCALE, fit:bool=False) -> None:
  '''
  Fill *view* with the net *built* was made from, as CNet drew it: each node
  where it was, the size it was (scaled by *scale*) -- or, if its text is
  bigger here, as big as that, about the same centre -- and the relations
  between them. (Not the types, nor the groups: collections aren't shown.)

  Nothing is placed meanwhile (see *SNGView.localLayout*): everything's put
  where it was.

  :param view: A view of *built.model*.
  :param built: What *reader.buildModel()* made.
  :param scale: How much bigger than CNet's picture.
  '''
  localLayout, view.localLayout = view.localLayout, None # type: ignore[assignment] # (nothing's placed: it's put where it was)
  try:
    for n in built.net.nodes:
      node = built.nodes.get(n.index)
      if node is None:
        continue
      x0, y0 = MARGIN + n.x * scale, MARGIN + n.y * scale
      x1, y1 = x0 + max(n.w, 1) * scale, y0 + max(n.h, 1) * scale
      vo = view.makeViewObjectForGraphObject(node, atPoint=(x0, y0))
      assert isinstance(vo, VNode)
      if fit:
        vo.boundingBox([int(x0), int(y0), int(x1), int(y1)])
        vo.moveToCenterOn((x0 + x1) / 2, (y0 + y1) / 2, adjustPos=False)
      else:
        vo.userSized = True # (as CNet sized it: not refitted to its text)
        vo.boundingBox([int(x0), int(y0), int(x1), int(y1)])
        vo.moveTo(int(x0), int(y0), adjustPos=False)
    relations = [view.makeViewObjectForGraphObject(r) for r, _ in built.relations]
    view.canvas.update() # (what's put off till idle)
    for vr in relations: # (each label on its line, between its ends: not moved off anything it's on)
      vr.reposition(adjustPos=False)
    view.canvas.update()
  finally:
    view.localLayout = localLayout

def convert(app:Application, rnetPath:str, modelPath:str, viewPath:str, parent:tk.Misc|None=None) -> tuple[Built, SNGView]|None:
  '''
  Make the model and view of the net *rnetPath*, save them, and open the
  view. If the model or view are there already, it asks first, and replaces
  them.

  :param app: The editor.
  :param rnetPath: The net file.
  :param modelPath: The model's file (".snm").
  :param viewPath: The view's file (".snv").
  :param parent: The window any messages are about (eg: the dialog), if any.
  :returns: What was made, and the view, if it was.
  '''
  where:dict[str, Any] = {"parent": parent} if parent is not None else {}
  def error(message:str) -> None:
    messagebox.showerror(TITLE, message, **where)
  rnetPath = os.path.abspath(os.path.expanduser(rnetPath.strip()))
  modelPath = os.path.abspath(os.path.expanduser(modelPath.strip()))
  viewPath = os.path.abspath(os.path.expanduser(viewPath.strip()))
  if not os.path.isfile(rnetPath):
    return error(f"There's no such file as {rnetPath}.")
  if not modelPath.endswith(".snm") or not viewPath.endswith(".snv"):
    return error("The model's file must end in .snm, and the view's in .snv.")
  try:
    net = parse(rnetPath)
  except (ValueError, OSError) as ex:
    return error(f"Couldn't read {os.path.basename(rnetPath)}:\n\n{ex}")
  existing = [p for p in (modelPath, viewPath) if os.path.exists(p)]
  if existing and not messagebox.askokcancel(TITLE, "These files are already there:\n\n  " + "\n  ".join(existing)
                                             + "\n\nReplace them?", icon=messagebox.WARNING, **where):
    return None
  for folder in {os.path.dirname(p) for p in (modelPath, viewPath)}:
    try:
      os.makedirs(folder, exist_ok=True)
    except OSError as ex:
      return error(f"Couldn't make the folder {folder}:\n\n{ex}")
  if not app.replacingModel(modelPath): # (its window, if it's open, and the model in memory: they'd be added to)
    return None
  for p in existing:
    os.remove(p)
  built = buildModel(net, modelPath)
  built.model.save()
  view = SNGView(fixURL(viewPath, None, replaceExt=None, mode="w")[0], model=built.model, mode="w")
  window = app.openWindow(view)
  if window is None:
    return None
  view.context.visibility("system objects", "hide")
  showNet(view, built)
  view.save()
  problems = f"\nIn the file: {'; '.join(net.problems)}." if net.problems else ""
  print(f"Made {os.path.basename(modelPath)} and {os.path.basename(viewPath)} from {os.path.basename(rnetPath)} "
        f"(version {net.version}): {built.report()}{problems}")
  return built, view

class ReaderDialog(tk.Toplevel):
  '''
  The front end: the net file to read, and the model and view files to make
  of it (each with "Choose..."), which follow the net file (see
  *defaultPaths()*) -- the view following the model -- until they're changed
  by hand; and "Go" (see *convert()*), which, when it's done, closes it.
  '''
  def __init__(self, app:Application, rnetPath:str|None=None, folder:str|None=None, outputFolder:str|None=None,
               onChosen:Callable[[str], None]|None=None, onGo:Callable[[str, str, str], None]|None=None,
               onClose:Callable[[], None]|None=None):
    '''
    :param app: The editor.
    :param rnetPath: The net file to start with, if any.
    :param folder: The folder to choose a net file in, at first.
    :param outputFolder: The folder to make the model and view in, by default (else beside the net).
    :param onChosen: Told the net file chosen with "Choose..." (eg: to start there next time).
    :param onGo: Told the net, model and view files, once "Go"'s made them.
    :param onClose: Called when it's closed: by "Go" (when the view's opened) or "Cancel".
    '''
    super().__init__(app)
    ownDialog(self, app, keep=False)
    self.app, self.folder, self.outputFolder = app, folder, outputFolder
    self.onChosen, self.onGo, self.onClose = onChosen, onGo, onClose
    self.title(TITLE)
    self.vars = {k: tk.StringVar(value="") for k in ("rnet", "model", "view")}
    self.following = {"model": True, "view": True}
    "Which files follow the one they're made from: until they're changed by hand."
    self._setting = False
    pad:dict[str, Any] = dict(padx=6, pady=3)
    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(1, weight=1)
    rows = (("rnet", "Net file:", self.chooseNet), ("model", "Model:", self.chooseModel), ("view", "View:", self.chooseView))
    for row, (key, label, choose) in enumerate(rows):
      ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, **pad)
      ttk.Entry(frame, textvariable=self.vars[key], width=64).grid(row=row, column=1, sticky=tk.EW, **pad)
      ttk.Button(frame, text="Choose...", command=choose).grid(row=row, column=2, **pad)
      self.vars[key].trace_add("write", lambda *_a, key=key: self.changed(key))
    ttk.Label(frame, text="A Rep Plus net (CNet, KNet): its node and link types, nodes, links, marks and groups.",
              foreground="gray40", wraplength=520).grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=6)
    bottom = ttk.Frame(frame)
    bottom.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
    self.goButton = ttk.Button(bottom, text="Go", command=self.go, default="active")
    self.goButton.pack(side=tk.RIGHT, padx=6)
    ttk.Button(bottom, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=6)
    self.bind("<Return>", lambda _e: self.go())
    self.bind("<Escape>", lambda _e: self.cancel())
    self.protocol("WM_DELETE_WINDOW", self.cancel)
    if rnetPath:
      self.vars["rnet"].set(rnetPath)
    self.refresh()
    self.lift()
    self.focus_force()

  def set(self, key:str, value:str) -> None:
    '''Set a file, as if by the program (so it still follows the one it's made from).'''
    if self.vars[key].get() == value:
      return
    self._setting = True
    try:
      self.vars[key].set(value)
    finally:
      self._setting = False

  def changed(self, key:str) -> None:
    '''
    A file's changed: by hand (unless *set()* did it), it's no longer
    following -- or, if it's been emptied, it is again; and those that follow
    it are set from it.
    '''
    value = self.vars[key].get().strip()
    if key in self.following and not self._setting:
      self.following[key] = not value
    if key in ("rnet", "model") or not value:
      self.setDefaults()
    self.refresh()

  def setDefaults(self) -> None:
    '''Set the files that are following: the model from the net file, and the view from the model.'''
    rnet = self.vars["rnet"].get().strip()
    if not rnet:
      return
    model, _view = defaultPaths(os.path.expanduser(rnet), self.outputFolder)
    if self.following["model"]:
      self.set("model", model)
    model = self.vars["model"].get().strip()
    if model and self.following["view"]:
      self.set("view", os.path.splitext(os.path.abspath(os.path.expanduser(model)))[0] + ".snv")

  def refresh(self) -> None:
    '''Go: only with all the files given.'''
    self.goButton.state(["!disabled"] if all(v.get().strip() for v in self.vars.values()) else ["disabled"])

  def startIn(self, key:str) -> dict[str, Any]:
    value = self.vars[key].get().strip()
    folder = os.path.dirname(os.path.abspath(os.path.expanduser(value))) if value else self.folder
    return {"initialdir": folder} if folder and os.path.isdir(folder) else {}

  def chooseNet(self) -> None:
    path = filedialog.askopenfilename(parent=self, title="Choose a Rep Plus net to make a Semantic Nets model of",
                                      filetypes=[("Rep Plus nets", "*.rnet"), ("All files", "*.*")], **self.startIn("rnet"))
    if path:
      self.vars["rnet"].set(path)
      if self.onChosen is not None:
        self.onChosen(path)

  def chooseSave(self, key:str, what:str, ext:str) -> None:
    current = self.vars[key].get().strip()
    path = filedialog.asksaveasfilename(parent=self, title=f"The {what}'s file", defaultextension=ext,
                                        initialfile=os.path.basename(current) if current else "",
                                        filetypes=[(f"{what.capitalize()} files", f"*{ext}")], **self.startIn(key))
    if path:
      self.vars[key].set(path)

  def chooseModel(self) -> None:
    self.chooseSave("model", "model", ".snm")

  def chooseView(self) -> None:
    self.chooseSave("view", "view", ".snv")

  def go(self) -> None:
    '''Make the model and view (see *convert()*); close, if that's done.'''
    v = {k: var.get().strip() for k, var in self.vars.items()}
    if not all(v.values()):
      return
    self.goButton.state(["disabled"])
    self.configure(cursor="watch")
    self.update_idletasks()
    try:
      done = convert(self.app, v["rnet"], v["model"], v["view"], parent=self)
    finally:
      if self.winfo_exists():
        self.configure(cursor="")
        self.refresh()
    if done is not None:
      if self.onGo is not None:
        self.onGo(v["rnet"], v["model"], v["view"])
      self.close()

  def cancel(self) -> None:
    self.close()

  def close(self) -> None:
    self.destroy()
    if self.onClose is not None:
      self.onClose()
