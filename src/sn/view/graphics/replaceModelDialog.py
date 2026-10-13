'''
Replacing a model's super-model with another (Edit | Replace super-model...):
eg, a local ontology with its copy on the web. See *Model.replaceSuperModel()*.

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
import os
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from sn.model.model import Model
from util.persistence.pRef import PRDb
from util.utils import ownDialog

class ReplaceModelDialog(tk.Toplevel):
  '''
  Which of a model's super-models -- or of the models its objects refer to
  that aren't (see *Model.unlistedModels()*) -- to replace, and with what
  (a file, or a URL). Modal: *show()* returns (the old model, the new one's
  file or URL), if OK'd.
  '''

  def __init__(self, parent:tk.Misc, model:Model):
    super().__init__(parent)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.model = model
    self.title(f"Replace a super-model of {model.name}")
    self.result:tuple[Model, str]|None = None
    implicit = model.implicitSuperDBs()
    unlisted = model.unlistedModels()
    self.candidates:list[tuple[str, Model]] = \
      [(PRDb.relativeURL(db.url, base=model.url), db) for db in model.superDBs
       if isinstance(db, Model) and not any(db is i for i in implicit)] + \
      [(f"{PRDb.relativeURL(db.url, base=model.url)}  (not a super-model: {n} reference{'s' if n > 1 else ''})", db)
       for db, n in unlisted.items()]
    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, wraplength=520, justify=tk.LEFT, foreground="gray35",
              text="Every reference this model's objects make to the one replaced becomes a reference to the same "
                   "object (the same id) in the other -- eg: a copy of an ontology moved to the web. Its views are "
                   "taken to refer to it too, when they're opened.").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 8))
    ttk.Label(frame, text="Replace:").grid(row=1, column=0, sticky=tk.W)
    self.old = ttk.Combobox(frame, state="readonly", width=60, values=[label for label, _ in self.candidates])
    self.old.grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=2)
    if self.candidates:
      self.old.current(len(self.candidates) - 1 if unlisted else 0)
    ttk.Label(frame, text="With:").grid(row=2, column=0, sticky=tk.W)
    self.new = tk.StringVar()
    ttk.Entry(frame, textvariable=self.new, width=48).grid(row=2, column=1, sticky=tk.EW, pady=2)
    ttk.Button(frame, text="File...", command=self.chooseFile).grid(row=2, column=2, padx=(4, 0))
    ttk.Button(frame, text="URL...", command=self.chooseURL).grid(row=2, column=3, padx=(4, 0))
    self.message = ttk.Label(frame, foreground="red3", wraplength=520, justify=tk.LEFT)
    self.message.grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=4, sticky=tk.E, pady=(8, 0))
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Replace", command=self.ok, default="active").pack(side=tk.LEFT, padx=(6, 0))
    frame.columnconfigure(1, weight=1)
    self.bind("<Return>", lambda _e: self.ok())
    self.bind("<Escape>", lambda _e: self.destroy())
    if not self.candidates:
      self.message.configure(text="It has no super-models (but the built-in ones, which can't be replaced).")

  def chooseFile(self) -> None:
    modelFile = self.model.url[len("file://"):] if self.model.url.startswith("file://") else ""
    path = filedialog.askopenfilename(parent=self, title="The model to put in its place",
                                      filetypes=[("Model files", "*.snm"), ("All files", "*.*")],
                                      initialdir=os.path.dirname(modelFile) or None)
    if path:
      self.new.set(PRDb.relativeURL(Path(path).as_uri(), base=self.model.url))

  def chooseURL(self) -> None:
    from sn.view.graphics.directoryWindow import askModelURL
    url = askModelURL(self, "The model to put in its place", kinds=("model",))
    if url:
      self.new.set(url)

  def ok(self) -> None:
    i = self.old.current()
    if i < 0:
      self.message.configure(text="Choose the model to replace.")
      return
    if not self.new.get().strip():
      self.message.configure(text="Choose the model to put in its place.")
      return
    self.result = (self.candidates[i][1], self.new.get().strip())
    self.destroy()

  def show(self) -> tuple[Model, str]|None:
    ''':returns: The model to replace, and the file or URL of the one to put in its place, if OK'd.'''
    try:
      self.wait_visibility()
      self.grab_set()
      self.lift()
    except tk.TclError:
      pass
    self.wait_window()
    return self.result
