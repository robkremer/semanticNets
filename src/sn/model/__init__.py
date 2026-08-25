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
from util.attribute import Attribute, VAR_DEFAULTED, TYPENAME, VAR
from util.persistence.pRef import PRDb
from mypyc.primitives import str_ops
import sys
import atexit
from util.utils import askUser
from util.observer import Subject

class TopModel(Model):
  def __init__(self, url:str, mode:str="", _reading:bool=False):
    '''
    Builds the base model for the SN application. This is required to always be
    in the in-memory models under the name "sn" (access as "$sn" in a URL, don't
    forget to escape it on a command line as "\$sn"
    '''
    Subject.__init__(self)
    PRDb.__init__(self, url, mode="")
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
    self.TOP.setAttr("name", Attribute("top", str, VAR_DEFAULTED))
    if self.TOP._id != 1:
      raise Exception("TopModel.__init__() called twice.")
    self.RELATION.setAttr("name", Attribute("relation", None, TYPENAME)) # can't do this until AFTER ISA exists.
    self.ISA["name"] = "isa"
    self.NODE:Node = Node(self, [self.TOP])
    self.NODE.setAttr("name", Attribute("node", None, VAR)) # can't do this until AFTER ISA exists.

    # add it the basic relation types
    self.REFLEXIVE:Relation = Relation(self, [self.RELATION], individual=False, name="reflexive")
    self.REFLEXIVE["reflexive"] = True
    self.IRREFLEXIVE:Relation = Relation(self, [self.RELATION], individual=False, name="irreflexive")
    self.IRREFLEXIVE["irreflexive"] = True
    self.SYMMETRIC:Relation = Relation(self, [self.RELATION], individual=False, name="symmetric") 
    self.SYMMETRIC["symmetric"] = True
    self.TRANSITIVE:Relation = Relation(self, [self.RELATION], individual=False, name="transitive") 
    self.TRANSITIVE["transitive"] = True

    # fix up the ISA relation type so it inherits from REFLEXIVE and TRANSITIVE
    assert isinstance(isaisa, IsaIndividual)
    isaisa.connect(destination=self.REFLEXIVE)
    IsaIndividual(self, self.ISA, self.TRANSITIVE)

    self.EQUALITY:Relation = Relation(self, [self.REFLEXIVE, self.SYMMETRIC, self.TRANSITIVE], name="equality")

    # add in a base context node
    self.COLLECTION:Collection = Collection(self, [self.NODE], [], individual=False, name="collection")

    self[0] # causes the "all model" collection to be instantiated.
    self._allowParentsCaching = True
    
model = TopModel("sn:///sn", mode="", _reading=False) # creates a model in memory cache
model._writeLocked = True

def saveAtExit():
  url:str
  db:PRDb
  for url, db in Model.AllDBs.items():
    assert isinstance(db, Model)
    model:Model = db
    if not model.writeLocked() and model.isDirty():
      ans:str|None = askUser(f'Save modified model?\n  {url}\n(Y/N):', "Save modified Model?")
      if ans is not None and ans.upper() in ["Y", "YES", "T", "TRUE"]:
        model.save()
  #print(f'At exit: {askUser("Answer a question:", "A title")}')
  
atexit.register(saveAtExit)
    