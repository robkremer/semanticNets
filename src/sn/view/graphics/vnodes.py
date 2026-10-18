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
"""
Implements VNode and all its supporting classes:

*VNode*:
   The main class in this module. A visual node that represents an *Node* (model node).
      
  .. inheritance-diagram:: VNode
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

----
"""

from sn.model.model import GraphObject
from sn.view.graphics.vobjects import VObject
from typing import Optional, Any, override, TYPE_CHECKING
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

class VNode(VObject):
  '''
  This class is more or less a dummy class under *VObject* for all nodes (including 
  T (top) (which **relation** is specialized from)) that are not **relations** so that
  nodes are issubclass()-distinct from **relations**. As such, most of it's functionality is 
  implemented in the common superclass *VObject*.  
  
  *VNode* <: *VObject* :> *VRelation*
  '''

  ### CONSTRUCTOR AND HELPERS ##########################################################

  def __init__(self, view:"SNGView", modelObject:GraphObject|str,
               shape:Any|str="Rectangle",
               x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None,
               **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param modelObject:
    :type modelObject: GraphObject | str
    :param shape:
    :type shape: Any | str
    :param x:
    :type x: Optional[int]
    :param y:
    :type y: Optional[int]
    :param x1:
    :type x1: Optional[int]
    :param y1:
    :type y1: Optional[int]
    :param kwargs:
    :type kwargs:
    '''
    super().__init__(view, modelObject, shape, x, y, x1, y1)
 
  @override
  def makeModelObjectSubtype(self, individual:bool) -> None:
    '''
    :param individual:
    :type individual: bool
    '''
    self.view.context.new_node(self.modelObject, name="", individual=individual, type=not individual, model=self.view.model) # type: ignore[arg-type]
