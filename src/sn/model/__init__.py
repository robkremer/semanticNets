'''
Defines and instantiates *TopModel* that must ALWAYS be memory resident for the
program to work.  Top model contains the following base objects:

  - top
    
    - node
      
      - collection
      - context
      
        - rule
        - definition
        - query
        - constraint
        
          - requirement
          
    - relation
    
      - isa
      - distinct
      - contains
      
        - antecedent
        - consequent
        - definiendum
        - definiens
        - condition
        - required
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
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual, SN_URL
from util.attribute import Attribute, VAR_DEFAULTED, VAR, LOCAL
from util.observer import Subject
from util.abstractGraph import AbstractGraph
from util.dirtyable import Dirtyable
from sn.model import names

TerminatorType = str
LineType = "choices[smooth,straight]"


NAME_NOTE = f'''The name of the object. Can be used to access the object in the model.

In a pattern (a rule, query, definition or constraint) a variable stands for whatever matches: {names.grammar.describe()}. A variable's constraints -- what what it matches must be like -- are in its "constraints" attribute (see that attribute's note). They can also be typed here, after the name and ":where:", eg:
  ?p :where: alive, age: 30
and are then moved into that attribute.'''
"The note on the name attribute: shown as its tooltip in the attribute editor."

class TopModel(Model):
  def __init__(self, url:str, mode="w", memoryResident:bool=True, _reading:bool=False):
    '''
    Builds the base model for the SN application. This is required to always be
    in the in-memory models under the name "sn" (access as "$sn" in a URL, don't
    forget to escape it on a command line as "\\$sn"

    :param url:
    :type url: str
    :param mode:
    :type mode:
    :param memoryResident:
    :type memoryResident: bool
    :param _reading:
    :type _reading: bool
    '''
    # explicitly DON'T call Model's constructor
    AbstractGraph.__init__(self, url, mode=mode, memoryResident=memoryResident, _reading=_reading)
    Subject.__init__(self)
    Dirtyable.__init__(self)
    
    self.TOP:GraphObject = GraphObject(self, []) #1
    # these re-assignments from a ValidationList to a list are necessary in 
    # these top types as they will violate the ValidationList constraints. 
    self.TOP._outgoing.checking(False) 
    self.TOP._incoming.checking(False)
    self.RELATION:Relation = Relation(self, [], self.TOP, self.TOP) #2
    self.RELATION._outgoing.checking(False)
    self.RELATION._incoming.checking(False)
    self.ISA:Relation = Relation(self, [], self.TOP, self.TOP) #3
    self.ISA._outgoing.checking(False)
    self.ISA._incoming.checking(False)
    self.ISA["reflexive"]  = Attribute(True, bool, LOCAL, "Object is a reflexive relation")
    self.ISA["transitive"] = Attribute(True, bool, LOCAL, "Object is a transitive relation")
    IsaIndividual(self, self.RELATION, self.TOP) #4 can't do this until after ISA exists
    IsaIndividual(self, self.ISA, self.RELATION) #5

    # now that we have the isa defined, fix up the name attribute (as it involves inheritance) 
    self.TOP.setAttr("name", Attribute("top", str, VAR_DEFAULTED, NAME_NOTE))
    if self.TOP._id != 1:
      raise Exception("TopModel.__init__() called twice.")
    self.RELATION.setAttr("name", Attribute("relation", None, VAR_DEFAULTED, NAME_NOTE)) # can't do this until AFTER ISA exists.
    self.ISA["name"] = "isa"
    self.NODE:Node = Node(self, [self.TOP]) #6,7
    self.NODE.setAttr("name", Attribute("node", None, VAR, NAME_NOTE)) # can't do this until AFTER ISA exists.

    # add in a base context node
    self.COLLECTION:Collection = Collection(self, [self.NODE], [], individual=False, name="collection") #21,22

    self[0] # causes the "all model" collection to be instantiated.

    # Contexts (rules, and later definitions and queries): what a context
    # "contains" is quoted -- a pattern, not a statement about the world (see
    # GraphObject.isPatternElement()). Added after everything above so existing
    # ids don't change.
    self.CONTEXT:Node = Node(self, [self.NODE], individual=False, name="context")
    self.CONTAINS:Relation = Relation(self, [self.RELATION], self.CONTEXT, self.TOP, individual=False, name="contains")
    self.RULE:Node = Node(self, [self.CONTEXT], individual=False, name="rule")
    self.ANTECEDENT:Relation = Relation(self, [self.CONTAINS], self.RULE, self.TOP, individual=False, name="antecedent")
    self.CONSEQUENT:Relation = Relation(self, [self.CONTAINS], self.RULE, self.TOP, individual=False, name="consequent")
    self.QUERY:Node = Node(self, [self.CONTEXT], individual=False, name="query") # contains its pattern with plain "contains"
    # x <-distinct-> y: x and y are different objects. In a pattern, a
    # constraint on its variables (?x != ?y) rather than a relation that must hold.
    self.DISTINCT:Relation = Relation(self, [self.RELATION], self.TOP, self.TOP, individual=False, name="distinct")
    self.DISTINCT["symmetric"] = True
    self.DISTINCT["irreflexive"] = True
    # A definition: its definiendum (the term defined) holds iff its definiens
    # (the meaning) does -- a rule both ways (see sn.model.reasoner.definitionSpecs()).
    # Added last, so existing ids don't change.
    self.DEFINITION:Node = Node(self, [self.CONTEXT], individual=False, name="definition")
    self.DEFINIENDUM:Relation = Relation(self, [self.CONTAINS], self.DEFINITION, self.TOP, individual=False, name="definiendum")
    self.DEFINIENS:Relation = Relation(self, [self.CONTAINS], self.DEFINITION, self.TOP, individual=False, name="definiens")
    # A constraint: what it contains (with plain "contains", as a query) must
    # not match -- each match is a violation (see sn.model.reasoner.constraintOf()).
    # Added last, so existing ids don't change.
    self.CONSTRAINT:Node = Node(self, [self.CONTEXT], individual=False, name="constraint")
    # A requirement: a constraint whose "required" part must hold wherever its
    # "condition" does -- each match of the condition it doesn't is a violation
    # (see sn.model.reasoner.constraintOf()). Added last, so existing ids don't change.
    self.REQUIREMENT:Node = Node(self, [self.CONSTRAINT], individual=False, name="requirement")
    # (not subtypes of antecedent and consequent: their domain is rule)
    self.CONDITION:Relation = Relation(self, [self.CONTAINS], self.REQUIREMENT, self.TOP, individual=False, name="condition")
    self.REQUIRED:Relation = Relation(self, [self.CONTAINS], self.REQUIREMENT, self.TOP, individual=False, name="required")

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
    self.RELATION['vis/shape']       = "Rectangle"
    self.RELATION['vis/borderColor'] = ""
    self.RELATION['vis/minSize']     = 10 
    self.RELATION['vis/maxSize']     = 40
    self.RELATION['vis/aspectRatio'] = 0.4
    
    self.ISA['vis/shape']           = "Rectangle"
    self.ISA['vis/minSize']         = 4
    self.ISA['vis/maxSize']         = 4
    self.ISA['vis/fillColor']       = "blue"
    self.ISA['vis/lineColor']       = "blue"
    self.ISA['vis/borderColor']     = "blue"
    self.ISA['vis/lineFillColor']   = ""
    self.ISA['vis/terminator4']     = "arrow(8,8,5)"
    self.ISA['vis/aspectRatio']     = 1.0

    self.NODE['vis/fillColor']      = "snow"
    
    self.CONTEXT['vis/titlebarColor'] = Attribute("grey", "color", VAR_DEFAULTED, "The background color of the title bar of contexts")
    self.CONTEXT[GraphObject.DISABLED] = Attribute(False, bool, VAR_DEFAULTED,
      "Switch it off: the reasoner ignores a disabled rule, definition, constraint or requirement (and it's "
      "drawn with a red slash through it). Eg: to try a model without it, while experimenting.")
    self.QUERY['vis/titlebarColor'] = "LightBlue3"
    self.QUERY['vis/fillColor']     = "LightCyan2"
    self.RULE['vis/titlebarColor']  = "khaki3"
    self.RULE['vis/fillColor']      = "lemon chiffon"
    self.DEFINITION['vis/titlebarColor'] = "goldenrod"
    self.DEFINITION['vis/fillColor']= "bisque"
    self.CONSTRAINT['vis/titlebarColor'] = "IndianRed3"
    # What a constraint's violations are like (see sn.model.reasoner.CONSTRAINT_ATTRIBUTES).
    self.CONSTRAINT['code']     = Attribute("", str, VAR_DEFAULTED, "The code of the violations it reports (default: the constraint's name).")
    self.CONSTRAINT['severity'] = Attribute("error", "choices[error,warning]", VAR_DEFAULTED, "How bad a violation is: error or warning.")
    self.CONSTRAINT['report']   = Attribute("", str, VAR_DEFAULTED,
      "What a violation is about, as a comma-separated list: its subject, then its arguments -- each one of the "
      "constraint's variables (eg: ^r), or a word taken as is (eg: reflexive). By default, all its variables, in "
      "name order (or the constraint itself if it has none).")
    self.CONSTRAINT['message']  = Attribute("", str, VAR_DEFAULTED,
      "The message, with {0} for the subject and {1}, {2}, ... for the arguments. By default, the code's built-in "
      "message, if it has one.")
    self.CONSTRAINT['vis/fillColor'] = "MistyRose"
    self.REQUIREMENT['vis/titlebarColor'] = "PaleVioletRed3"
    self.REQUIREMENT['vis/fillColor'] = "LavenderBlush"
        
model = TopModel(SN_URL, mode="", _reading=False) # creates a model in memory cache
model._writeLocked = True

    