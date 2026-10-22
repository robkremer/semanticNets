'''
Choosing the model a view shows: in place of one that can't be found when the
view's opened (eg: it's been moved), or another (File | Change model...: eg,
a copy of it). See *SNGView.askForMissingModel*, *Application.changeModel()*.

Created on Oct 22, 2026

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
from sn.model.directory import Entry
from util.utils import ownDialog, urlPath

class ChooseModelDialog(tk.Toplevel):
  '''
  Which model a view is to show: one of *candidates* (eg: copies of the one
  it shows, or of the one it can't find: see *Directory.copiesOf()*), or a
  file, or a URL. Modal: *show()* returns the model's URL, if OK'd.
  '''

  def __init__(self, parent:tk.Misc, title:str, message:str, candidates:list[Entry], near:str="", ok:str="OK"):
    '''
    :param title: The dialog's title.
    :param message: What it's for, above the choices.
    :param candidates: The models offered (the first is chosen).
    :param near: A URL: the file dialog starts in its folder.
    :param ok: The OK button's text.
    '''
    super().__init__(parent)
    ownDialog(self, parent) # (over its parent's window, not full screen: see ownDialog())
    self.title(title)
    self.near = near
    self.result:str|None = None
    self.candidates = candidates
    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, wraplength=560, justify=tk.LEFT, text=message).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
    row = 1
    self.list:tk.Listbox|None = None
    if candidates:
      ttk.Label(frame, text="Found (moved or copied from there, or with the same name):").grid(row=row, column=0, columnspan=3, sticky=tk.W)
      self.list = tk.Listbox(frame, height=min(len(candidates), 6), width=80, exportselection=False)
      for e in candidates:
        self.list.insert(tk.END, urlPath(e.url) if e.url.startswith("file:") else e.url)
      self.list.grid(row=row + 1, column=0, columnspan=3, sticky=tk.EW, pady=2)
      self.list.selection_set(0)
      self.list.bind("<<ListboxSelect>>", lambda _e: self.new.set(""))
      self.list.bind("<Double-Button-1>", lambda _e: self.ok())
      row += 2
    ttk.Label(frame, text="Or:" if candidates else "Model:").grid(row=row, column=0, sticky=tk.W)
    self.new = tk.StringVar()
    self.new.trace_add("write", lambda *_a: self.new.get() and self.list is not None and self.list.selection_clear(0, tk.END))
    ttk.Entry(frame, textvariable=self.new, width=60).grid(row=row, column=1, sticky=tk.EW, pady=2)
    choosers = ttk.Frame(frame)
    choosers.grid(row=row, column=2, sticky=tk.W)
    ttk.Button(choosers, text="File...", command=self.chooseFile).pack(side=tk.LEFT, padx=(4, 0))
    ttk.Button(choosers, text="URL...", command=self.chooseURL).pack(side=tk.LEFT, padx=(4, 0))
    self.message = ttk.Label(frame, foreground="red3", wraplength=560, justify=tk.LEFT)
    self.message.grid(row=row + 1, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=row + 2, column=0, columnspan=3, sticky=tk.E, pady=(8, 0))
    ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side=tk.LEFT)
    ttk.Button(buttons, text=ok, command=self.ok, default="active").pack(side=tk.LEFT, padx=(6, 0))
    frame.columnconfigure(1, weight=1)
    self.bind("<Return>", lambda _e: self.ok())
    self.bind("<Escape>", lambda _e: self.destroy())

  def chooseFile(self) -> None:
    nearFile = (urlPath(self.near) or "") if self.near.startswith("file:") else ""
    path = filedialog.askopenfilename(parent=self, title="The model",
                                      filetypes=[("Model files", "*.snm"), ("All files", "*.*")],
                                      initialdir=os.path.dirname(nearFile) or None)
    if path:
      self.new.set(path)

  def chooseURL(self) -> None:
    from sn.view.graphics.directoryWindow import askModelURL
    url = askModelURL(self, "The model", kinds=("model",))
    if url:
      self.new.set(url)

  def ok(self) -> None:
    typed = self.new.get().strip()
    chosen = self.list.curselection() if self.list is not None else ()
    if typed:
      self.result = typed if "://" in typed else Path(os.path.abspath(os.path.expanduser(typed))).as_uri()
    elif chosen:
      self.result = self.candidates[chosen[0]].url
    else:
      self.message.configure(text="Choose a model.")
      return
    self.destroy()

  def show(self) -> str|None:
    ''':returns: The URL of the model chosen, if OK'd.'''
    try:
      self.wait_visibility()
      self.grab_set()
      self.lift()
    except tk.TclError:
      pass
    self.wait_window()
    return self.result
