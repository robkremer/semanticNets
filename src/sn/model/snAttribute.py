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
from util.attribute import AttributedObject, Attribute, LOCAL
from util.lineMarks import checkMarks
from util.persistence.serialize import SerializableType
from typing import Optional, override
'''
Created on Sep 25, 2026

@author: robkremer
'''

RELATIONAL_ATTRS:list = [
  "symmetric",
  "asymmetric",
  "reflexive",
  "irreflexive",
  "transitive"]

MARKS_ATTRS:tuple[str, ...] = ("vis/terminator1", "vis/terminator2", "vis/terminator3", "vis/terminator4", "vis/midMarks")
"""The attributes that hold a relation's marks: mark specs (see *util.lineMarks*), checked when they're set
(see *SNAttributedObject._validateOverride()*)."""

class SNAttributedObject(AttributedObject):
  '''
  Special purpose *AttrubutedObject* for Semantic Nets.  This version treats
  the relational attributes as special in that they are always True booleans
  and marked as LOCAL (meaning they may not be inherited by either types or
  individuals).
  
  These are:
    
    - symmetric
    - asymmetric
    - reflexive
    - irreflexive
    - transitive

  It also checks the marks attributes (*MARKS_ATTRS*) as they're set: a mark
  spec that can't be read is refused with a message saying why (the attribute
  editor shows it while the user can still fix it) -- it would otherwise be
  accepted as a string and draw nothing.
  '''

  @override
  @classmethod
  def _validateOverride(cls, key:str, isIndividual:bool, attr:Attribute, superAttr:Optional[Attribute]):
    super()._validateOverride(key, isIndividual, attr, superAttr)
    if key in MARKS_ATTRS and isinstance(attr.value, str):
      err = checkMarks(attr.value)
      if err is not None:
        raise ValueError(f'key "{key}": {err}')

  @override
  def __setitem__(self, key:str, value:SerializableType)->None:
    if key in RELATIONAL_ATTRS:
      value = Attribute(True, bool, LOCAL)
    super().__setitem__(key, value)


  @override
  def setAttr(self, key:str, attr:Attribute)->Attribute:
    if key in RELATIONAL_ATTRS:
      attr = Attribute(True, bool, LOCAL)
    return super().setAttr(key, attr)

        