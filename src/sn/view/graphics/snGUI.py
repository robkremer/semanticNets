#################################################################################
# (c) Copyright 2024-2025, Rob Kremer, MIT open source license.                 #
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
import sn
'''
The *__main__* module to run the SN GUI.

Created on Aug 12, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>

'''

from typing import Optional, Iterable, Union, Callable
from types import NoneType
from sn import snPrefs
from sn.model.model import Model
from sn.view.graphics.loggingPanedWindow import AppWindow
from sn.view.graphics.view import SNView

import logging
logger:sn.SNLogger = sn.getLogger(__name__)

root:Optional[AppWindow] = None
'The root window will be of type *AppWindow'

def runGUI(model:Union[Model, tuple[Model, Callable[[SNView], None]]]|None=None, views:Union[list[str], str, None]|None=None):
  '''
  :param model: [Model (optional)] A Model object to open. Can also be a 
      Model/script tuple where the second element is a function taking a SNView
      to be executed after the SNView is created. Useful if you want to display
      certain elements on the SNView at initialization.
  :param views: [list[str] (optional)] A list of views to open.
  :raises Exception: if either *model* or *view* is given and opening these
    fails. Note 
  
  Initializes and runs the GUI, opening the *model* and any *views* URLs given; if
  neither is given, an attempt is mode to open any views remembered from the
  last time the program is run (however, any failures here will **not** raise
  and exception, but fail quietly with only a logger warning).
  
  .. Note:
    This function does not return, at least not until the *tkinter* *mainloop()*
    method ends.
  '''
  global root
  
  #check parameters
  modelScript = None
  if isinstance(model, tuple):
    assert len(model) == 2
    modelScript = model[1]
    assert callable(modelScript)
    model = model[0]
  assert isinstance(model, (Model, NoneType)), f'Unexpected model type: "{model.__class__.__name__}"'
  if isinstance(views, str):
    views = [views]
  assert isinstance(views, (Iterable, NoneType))
  if views is not None:
    for v in views:
      assert isinstance(v, str)

  root = AppWindow()#tk.Tk()
  # style = ttk.Style(root)
  # style.theme_use('classic')
  root.focus_force()
  
  if model is not None or (views is not None and len(views)>0): # we have stuff to open
    if model is not None: # we were passed a model to open
      try:
        tgview = SNView(model=model, root=root)
        if modelScript is not None:
            modelScript(tgview)
      except Exception as ex:
        root.destroy()
        raise ex
    if views is not None and len(views)>0: # we were passed some views to open
      for url in views:
        try:
          SNView(url=url, root=root)
        except Exception as ex:
          root.destroy()
          raise ex
  # we weren't passed anything to open, so attempt to open remembered stuff from the prefs
  elif "views" in snPrefs and isinstance(snPrefs["views"], Iterable) and len(snPrefs["views"])>0: 
    for url in snPrefs["views"]:
      try:
        SNView(url=url, root=root)
      except Exception as ex:
        logger.warning(f'Failed to open recent URL "{url}": {ex}')
  else:
    root.deiconify()
  root.mainloop()

if __name__ == '__main__':
  runGUI()

