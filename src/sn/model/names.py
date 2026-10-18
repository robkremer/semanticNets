'''
The grammar of object names: which names are constants and which are
variables -- and of which kind. This is the only place that knows the syntax:
everything else asks *grammar* (see *NameGrammar.parse()*), so an application
that needs its own syntax for names can install its own grammar (see
*setGrammar()*).

The default grammar:

  =============  ===================================================
  ``fred``       a constant: names the object it is
  ``?x``         an individual variable: matches individuals
  ``^T``         a type variable: matches types
  ``!a``         an "any" variable: matches individuals and types alike
  =============  ===================================================

A variable used as a relation's type (eg: ``^r`` in ``!a -^r-> ?b``) matches
relation types, whatever its kind (an individual can't be a relation's type).

A variable whose stem starts with "_" (eg: ``?_brother``, or just ``?_``) is
*hidden*: it matches as any other does, but a query's answers don't report
it (see *isHiddenName()*): eg: ``?x -has-brother-> ?_b`` answers who has a
brother, not who it is.

Created on Oct 6, 2026

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
from enum import Enum

class NameKind(Enum):
  '''
  What a name makes an object: a constant, or a variable matching individuals,
  types, or either.
  '''
  CONSTANT = "constant"
  INDIVIDUAL = "individual"
  TYPE = "type"
  ANY = "any"

  @property
  def isVariable(self) -> bool:
    '''
    :returns: True iff this is a variable's kind.
    '''
    return self is not NameKind.CONSTANT

class NameGrammar:
  '''
  The default grammar of names (see the module doc). To change the syntax,
  subclass it, override *parse()* (and *describe()*, which says it in words),
  and install an instance with *setGrammar()*.

  The base rules (see *sn.model.reasoner.BASE_RULES*) are written in the
  default syntax (eg: ``!a -^r-> ?b``), so a replacement should extend it
  rather than drop it: leave the names it doesn't claim to ``super().parse()``.
  '''
  PREFIXES:dict[str, NameKind] = {"?": NameKind.INDIVIDUAL, "^": NameKind.TYPE, "!": NameKind.ANY}
  "The default grammar's variable prefixes."

  def parse(self, name:str) -> tuple[NameKind, str]:
    '''
    THE place a name's kind is decided.

    :param name: An object's name.
    :returns: Its kind, and its stem: the name without the syntax that makes
      it a variable, eg: (NameKind.INDIVIDUAL, "x") for "?x". A constant's
      stem is its name.
    '''
    if name and name[0] in self.PREFIXES:
      return self.PREFIXES[name[0]], name[1:]
    return NameKind.CONSTANT, name

  def isHidden(self, name:str) -> bool:
    '''
    :param name: An object's name.
    :returns: True iff it's a hidden variable's: one that answers don't report
      (see the module doc) -- by default, one whose stem starts with "_".
    '''
    kind, stem = self.parse(name)
    return kind.isVariable and stem.startswith("_")

  def describe(self) -> str:
    '''
    :returns: The grammar in words, for notes and messages.
    '''
    return ('a name starting with "?" is an individual variable (it matches individuals), '
            'with "^" a type variable (it matches types), and with "!" an "any" variable '
            '(it matches individuals and types alike); any other name is a constant. A variable whose name '
            'starts with "_" after that (eg: "?_b") is hidden: it isn\'t reported in a query\'s answers')

grammar:NameGrammar = NameGrammar()
"The grammar in use. Read it as *names.grammar* (not imported by name), so a replacement is seen."

def setGrammar(g:NameGrammar) -> None:
  '''
  Install *g* as the grammar of names.
  '''
  global grammar
  grammar = g

def nameKind(name:object) -> NameKind:
  '''
  :param name: A name -- anything else (eg: None, during construction) is a constant.
  :returns: Its kind, per the grammar in use.
  '''
  return grammar.parse(name)[0] if isinstance(name, str) else NameKind.CONSTANT

def isVariableName(name:object) -> bool:
  '''
  :returns: True iff *name* is a variable's, per the grammar in use.
  '''
  return nameKind(name).isVariable

def isHiddenName(name:object) -> bool:
  '''
  :returns: True iff *name* is a hidden variable's, per the grammar in use (see *NameGrammar.isHidden()*).
  '''
  return isinstance(name, str) and grammar.isHidden(name)

def stem(name:str) -> str:
  '''
  :returns: *name* without the syntax that makes it a variable (see *NameGrammar.parse()*).
  '''
  return grammar.parse(name)[1]
