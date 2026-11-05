'''
"assert" and "set attribute", as typed at the terminal: relating inferred
objects, a relation type's new ends and their undo, repeated and ambiguous
asserts, typed values, relational properties set off -- and the terminal's
output formats.

Created on Nov 4, 2026

@author: robkremer
'''
import io
import unittest
from contextlib import redirect_stdout
from util.attribute import Attribute, VAR
from util.observer import Observer
from util.persistence.pRef import DuplicateNameError
from sn.model.model import Model, Node, Relation
from sn.controller.modelInterface import ModelContext


class Test(unittest.TestCase):

  def setUp(self):
    self.m = Model(f"temp_assertAndSet_{self._testMethodName}.xml") # (models are cached by name)
    self.c = ModelContext(self.m)
    self.line = self.c.parser.parseLine
    self.person = Node(self.m, [self.m.NODE], name="person")
    self.fred = Node(self.m, [self.person], individual=True, name="fred")
    self.likes = Relation(self.m, [self.m.RELATION], name="likes", src=self.person, dst=self.person)

  def inferredNode(self, name:str) -> Node:
    with self.m.inferring():
      return Node(self.m, [self.person], individual=True, name=name, inferred=True)

  # Relating an inferred object (it isn't saved: the relation would lead nowhere when read)

  def test0100relateInferredRefused(self):
    ghost = self.inferredNode("ghost")
    n = len(self.m)
    with self.assertRaises(PermissionError):
      Relation(self.m, [self.likes], individual=True, src=self.fred, dst=ghost)
    with self.assertRaises(PermissionError):
      self.line("assert fred likes ghost")
    with self.assertRaises(PermissionError):
      self.line("assert ghost likes fred")
    self.assertEqual(len(self.m), n) # (nothing half made)
    self.assertNotIn(ghost, self.fred.getRelatedTo(self.likes))
    r = Relation(self.m, [self.likes], individual=True, src=self.fred, dst=self.fred)
    with self.assertRaises(PermissionError):
      r.connect(destination=ghost)
    self.assertIs(r.localDst, self.fred)
    with self.m.inferring(): # (the reasoner may)
      inferredRel = Relation(self.m, [self.likes], individual=True, src=self.fred, dst=ghost, inferred=True)
    self.assertIs(inferredRel.dst, ghost)

  # A relation type's new ends: undo, redo, undo

  def test0200relationTypeEnds(self):
    animal = Node(self.m, [self.m.NODE], name="animal")
    sees = Relation(self.m, [self.m.RELATION], name="sees") # (no ends of its own)
    self.assertIsNone(sees.localSrc)
    self.line("assert person sees animal")
    self.assertIs(sees.localSrc, self.person)
    self.assertIs(sees.localDst, animal)
    self.line("undo")
    self.assertIsNone(sees.localSrc)
    self.assertIsNone(sees.localDst)
    self.assertNotIn(sees, self.person._outgoing)
    self.line("redo")
    self.assertIs(sees.localSrc, self.person)
    self.assertIs(sees.localDst, animal)
    self.line("undo")
    self.assertIsNone(sees.localSrc)
    self.line("assert animal likes animal") # (one that had ends)
    self.assertIs(self.likes.localSrc, animal)
    self.line("undo")
    self.assertIs(self.likes.localSrc, self.person)
    self.assertIs(self.likes.localDst, self.person)
    self.assertIn(self.likes, self.person._outgoing)
    self.assertNotIn(self.likes, animal._outgoing)

  def test0250connectTellsObservers(self):
    animal = Node(self.m, [self.m.NODE], name="animal")
    heard:list = []
    class Listener(Observer):
      def update(self, subject, *topics):
        heard.extend(topics)
    listener = Listener()
    self.likes.attach(listener)
    self.likes.connect(animal, animal)
    self.assertIn(("mod src", (self.person, animal)), heard)
    self.assertIn(("mod dst", (self.person, animal)), heard)

  # Repeated and ambiguous asserts

  def test0300assertAgainAddsNothing(self):
    self.line("assert person bob")
    n = len(self.m)
    self.line("assert person bob")
    self.assertEqual(len(self.m), n)
    self.line("undo") # (the second: nothing)
    self.assertEqual(len(self.m), n)
    self.assertIn(self.person, self.m["bob"].getParents())

  def test0310assertAmbiguousNameRefused(self):
    Node(self.m, [self.person], individual=True, name="sam")
    Node(self.m, [self.person], individual=True, name="sam")
    n = len(self.m)
    with self.assertRaises(DuplicateNameError):
      self.line("assert person sam")
    self.assertEqual(len(self.m), n)

  # Typed values

  def test0400setBool(self):
    for text, expected in (("false", False), ("no", False), ("0", False), ("true", True), ("yes", True)):
      self.line(f"set attribute fred flag {text} --type bool")
      self.assertIs(self.fred["flag"], expected, text)
    with self.assertRaises(ValueError):
      self.line("set attribute fred flag maybe --type bool")

  def test0410resetKeepsType(self):
    self.line("set attribute fred age 3 --type int")
    self.assertEqual(self.fred["age"], 3)
    self.line("set attribute fred age 4")
    self.assertEqual(self.fred["age"], 4)
    self.assertIs(self.fred.getLocalAttr("age").type, int)
    self.line("undo")
    self.assertEqual(self.fred["age"], 3)
    with self.assertRaises(ValueError):
      self.line("set attribute fred age 3 --type nosuchtype")

  def test0420newAttributeUndone(self):
    self.c.set_attribute(self.fred, "nickname", Attribute("freddy", str, VAR))
    self.assertEqual(self.fred["nickname"], "freddy")
    self.line("undo")
    self.assertIsNone(self.fred.getLocalAttr("nickname"))

  # Relational properties are tags: set off, they're taken away

  def test0500symmetricOff(self):
    self.line("set attribute likes symmetric yes")
    self.assertIsNotNone(self.likes.getLocalAttr("symmetric"))
    self.line("set attribute likes symmetric no")
    self.assertIsNone(self.likes.getLocalAttr("symmetric"))
    self.line("undo")
    self.assertIs(self.likes.getLocalAttr("symmetric").value, True)
    self.line("undo")
    self.assertIsNone(self.likes.getLocalAttr("symmetric"))
    self.line("set attribute likes transitive no") # (not there: nothing to take away)
    self.assertIsNone(self.likes.getLocalAttr("transitive"))

  # The terminal's output formats

  def test0600formats(self):
    from sn.view import textUserInterface as tui
    ui = tui.UIContext(self.m)
    try:
      for fmt in tui.formatOptions["GraphObject"]:
        ui.format_object(fmt)
        self.assertIsInstance(tui.printLists(self.fred, contextModel=self.m), str, fmt)
      for fmt in tui.formatOptions["Model"]:
        ui.format_model(fmt)
        with redirect_stdout(io.StringIO()):
          self.assertIsInstance(tui.printLists(self.m, contextModel=self.m), str, fmt)
      ui.format_object("tostring")
      self.assertIn("fred", tui.printLists(self.fred, contextModel=self.m))
    finally:
      ui.format_object("str")
      ui.format_model("str")


if __name__ == "__main__":
  unittest.main()
