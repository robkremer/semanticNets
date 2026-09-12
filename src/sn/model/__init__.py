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
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual
from util.attribute import Attribute, VAR_DEFAULTED, TYPENAME, VAR, CONST
from util.persistence.pRef import PRDb
import sys
import atexit
from util.utils import askUser
from util.observer import Subject
from util.abstractGraph import AbstractGraph
from util.dirtyable import Dirtyable

TerminatorType = str
LineType = "choices[smooth,straight]"

class TopModel(Model):
  def __init__(self, url:str, mode="w", memoryResident:bool=True, _reading:bool=False):
    '''
    Builds the base model for the SN application. This is required to always be
    in the in-memory models under the name "sn" (access as "$sn" in a URL, don't
    forget to escape it on a command line as "\\$sn"
    '''
    AbstractGraph.__init__(self, url, mode=mode, memoryResident=memoryResident, _reading=_reading)
    Subject.__init__(self)
    Dirtyable.__init__(self)
    self._allowParentsCaching:bool = False
    self.TOP:GraphObject = GraphObject(self, [])
    # these re-assignments from a ValidationList to a list are necessary in 
    # these top types as they will violate the ValidationList constraints. 
    self.TOP._outgoing.checking(False) 
    self.TOP._incoming.checking(False)
    self.RELATION:Relation = Relation(self, [], self.TOP, self.TOP)
    self.RELATION._outgoing.checking(False)
    self.RELATION._incoming.checking(False)
    self.ISA:Relation = Relation(self, [], self.TOP, self.TOP)
    self.ISA._outgoing.checking(False)
    self.ISA._incoming.checking(False)
    IsaIndividual(self, self.RELATION, self.TOP) # can't do this until after ISA exists
    isaisa:IsaIndividual = IsaIndividual(self, self.ISA, self.RELATION)

    # now that we have the isa defined, fix up the name attribute (as it involves inheritance) 
    self.TOP.setAttr("name", Attribute("top", str, VAR_DEFAULTED, "The name of the object. Can be used to access the object in the model."))
    if self.TOP._id != 1:
      raise Exception("TopModel.__init__() called twice.")
    self.RELATION.setAttr("name", Attribute("relation", None, TYPENAME)) # can't do this until AFTER ISA exists.
    self.ISA["name"] = "isa"
    self.NODE:Node = Node(self, [self.TOP])
    self.NODE.setAttr("name", Attribute("node", None, VAR)) # can't do this until AFTER ISA exists.

    # add it the basic relation types
    self.REFLEXIVE:Relation = Relation(self, [self.RELATION], individual=False, name="reflexive")
    self.REFLEXIVE["reflexive"] = Attribute(True, bool, CONST, "Object is a reflexive relation")
    self.IRREFLEXIVE:Relation = Relation(self, [self.RELATION], individual=False, name="irreflexive")
    self.IRREFLEXIVE["irreflexive"] = Attribute(True, bool, CONST, "Object is a irreflexive relation")
    self.SYMMETRIC:Relation = Relation(self, [self.RELATION], individual=False, name="symmetric") 
    self.SYMMETRIC["symmetric"] = Attribute(True, bool, CONST, "Object is a symmetric relation")
    self.TRANSITIVE:Relation = Relation(self, [self.RELATION], individual=False, name="transitive") 
    self.TRANSITIVE["transitive"] = Attribute(True, bool, CONST, "Object is a transitive relation")

    # fix up the ISA relation type so it inherits from REFLEXIVE and TRANSITIVE
    assert isinstance(isaisa, IsaIndividual)
    isaisa.connect(destination=self.TRANSITIVE)
    IsaIndividual(self, self.ISA, self.REFLEXIVE)
    IsaIndividual(self, self.RELATION, self.TOP) # relations needs to be fixed too.

    self.EQUALITY:Relation = Relation(self, [self.REFLEXIVE, self.SYMMETRIC, self.TRANSITIVE], name="equality")

    # add in a base context node
    self.COLLECTION:Collection = Collection(self, [self.NODE], [], individual=False, name="collection")

    self[0] # causes the "all model" collection to be instantiated.
    self._allowParentsCaching = True
    
    self.TOP['vis/shape']          = Attribute("Rectangle", str, VAR_DEFAULTED, \
      """The shape of the node or relation label in the GUI.
      Rectangle
      Oval
      RightParallelogram
      LeftParallelogram
      FileFolder
      TopPentagon
      RightPentagon
      LeftPentagon
      Hexagon
      RoundedRectangle
      """)
    self.TOP['vis/minSize']        = Attribute(20, int, VAR_DEFAULTED, "The minimum width of the shape of a node or relation label in the GUI.")
    self.TOP['vis/maxSize']        = Attribute(80, int, VAR_DEFAULTED, "The maximum width of the shape of the node or relation label in the GUI.")
    self.TOP['vis/aspectRatio']    = Attribute(0.6, float, VAR_DEFAULTED, "The height-to-width ratio of the shape of the node or relation label in the GUI.")
    self.TOP['vis/fillColor']      = Attribute("", "color", VAR_DEFAULTED, "The fill color of the node or relation label in the GUI.")
    self.TOP['vis/borderColor']    = Attribute("black", "color", VAR_DEFAULTED, "The border color of the node or relation label in the GUI.")
    self.TOP['vis/borderSmooth']   = Attribute(False, bool, VAR_DEFAULTED, "Whether or not the border is smooth for a node or relation label in the GUI.")
    self.TOP['vis/borderWidth']    = Attribute(1, int, VAR_DEFAULTED, "The width of the border for a node or relation label in the GUI.")
    self.TOP['vis/textColor']      = Attribute("black", "color", VAR_DEFAULTED, "The text color of the node or relation label in the GUI.")
    self.TOP['vis/textModifiesBB'] = Attribute(True, bool, VAR_DEFAULTED, "Set to True to let the text determine the size of the node or relation label in the GUI.")
    

    self.RELATION['vis/terminator1'] = Attribute("", TerminatorType, VAR_DEFAULTED, "The distal-from side connector of the relation connector in the GUI.\n  circle[(<size>)] | arrow[(<top-to-centre>,<tip-to-intersect>,<width>)]")
    self.RELATION['vis/terminator2'] = Attribute("", TerminatorType, VAR_DEFAULTED, "The proximal-from side connector of the relation connector in the GUI.\n  circle[(<size>)] | arrow[(<top-to-centre>,<tip-to-intersect>,<width>)]")
    self.RELATION['vis/terminator3'] = Attribute("", TerminatorType, VAR_DEFAULTED, "The proximal-to side connector of the relation connector in the GUI.\n  circle[(<size>)] | arrow[(<top-to-centre>,<tip-to-intersect>,<width>)]")
    self.RELATION['vis/terminator4'] = Attribute("arrow", TerminatorType, VAR_DEFAULTED, "The distal-to side connector of the relation connector in the GUI.\n  circle[(<size>)] | arrow[(<top-to-centre>,<tip-to-intersect>,<width>)]")
    self.RELATION['vis/lineColor']   = Attribute("black", "color", VAR_DEFAULTED, "The line color of the relation connector in the GUI.")
    self.RELATION['vis/lineFillColor'] = Attribute("black", "color", VAR_DEFAULTED, "The terminal's fill color of the relation connector in the GUI.")
    self.RELATION['vis/lineType']    = Attribute("smooth", LineType, VAR_DEFAULTED, "The curve type of the line of the relation connector in the GUI.\n  smooth | straight")
    self.RELATION['vis/lineWidth']   = Attribute(1, int, VAR_DEFAULTED, "The line width of the relation connector in the GUI.")
    self.RELATION['vis/shape']       = "Oval"
    
    self.ISA['vis/shape']           = "Rectangle"
    self.ISA['vis/minSize']         = 4
    self.ISA['vis/maxSize']         = 4
    self.ISA['vis/fillColor']       = "blue"
    self.ISA['vis/lineColor']       = "blue"
    self.ISA['vis/borderColor']     = "blue"
    self.ISA['vis/lineFillColor']   = ""
    self.ISA['vis/terminator4']     = "arrow(8,8,5)"
    self.ISA['vis/aspectRatio']     = 1.0

    self.SYMMETRIC['vis/terminator1'] = "arrow"
    self.REFLEXIVE['vis/terminator2'] = "circle"
    self.TRANSITIVE['vis/terminator4'] = "arrow(11,14,3)"
    
model = TopModel("sn:///sn", mode="", _reading=False) # creates a model in memory cache
model._writeLocked = True

    