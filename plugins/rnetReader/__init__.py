'''
rnetReader: a plugin (see *sn.plugins*) that makes a model and view of a Rep
Plus net (a ".rnet" file: Brian Gaines's CNet and KNet), from the Tools
menu's "Rep Plus Net Reader...".

  - *rnet*: reads the file;
  - *reader*: makes the model;
  - *hooks*: a KNet node's truth marks -- their bars, and its menu's items to mark it (and to show its net's probes);
  - *probes*: a net's probes, and the links they say hold;
  - *view*: the front end, and the view.

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
from typing import Any

_dialog:Any = None
"The dialog, while it's open: the menu item brings it to the front rather than opening another."

def register(ctx:Any) -> None:
  '''
  Add "Rep Plus Net Reader..." to the Tools menu (see
  *sn.plugins.PluginContext*): its dialog (see *view.ReaderDialog*) asks
  for the net file -- in the folder last read from -- and the model and view
  to make of it: by default in the folder they were last made in (else
  beside the net), and makes them (see *view.convert()*).

  :param ctx: The plugin's context.
  :type ctx: sn.plugins.PluginContext
  '''
  def openDialog() -> None:
    global _dialog
    if _dialog is not None and _dialog.winfo_exists():
      _dialog.lift()
      _dialog.focus_force()
      return
    from .view import ReaderDialog # (here: tkinter, the views, ... only once it's used)
    def went(_rnet:str, model:str, _view:str) -> None:
      ctx.setPref("outputFolder", os.path.dirname(os.path.abspath(os.path.expanduser(model))))
    def closed() -> None:
      global _dialog
      _dialog = None
    _dialog = ReaderDialog(ctx.app, folder=ctx.pref("lastFolder", None) or os.path.expanduser("~"),
                           outputFolder=ctx.pref("outputFolder", None) or None,
                           onChosen=lambda path: ctx.setPref("lastFolder", os.path.dirname(path)),
                           onGo=went, onClose=closed)
  ctx.addMenuItem("Rep Plus Net Reader...", openDialog)
