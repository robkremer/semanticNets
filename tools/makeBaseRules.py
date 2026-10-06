'''
Make the base rules that come with Semantic Nets -- src/sn/model/baseRules.snm
-- from scratch: the meaning of the relational properties (symmetric,
transitive, reflexive, irreflexive, asymmetric), as ordinary rules and
constraints, which every reasoner applies to every model (see
sn.model.reasoner.BASE_RULES).

  python3.14 tools/makeBaseRules.py

It builds the model in a temporary folder, as a temporary user (HOME), so it
never touches your files or preferences; and then copies it into
src/sn/model/, stored as being in sn.model.reasoner.BASE_RULES_PLACEHOLDER
(see sn.model.reasoner.baseRuleModels(), which reads it from where it is).

The properties are tags on specific relation types, and aren't inherited
(brother isa sibling, but only sibling is symmetric); brother pairs still
count as sibling pairs, so they get sibling's symmetric closure. ^r, used as
a relation's type, ranges over relation types.

The other variables' kinds (see sn.model.names) follow from what a relation
with a type at an end means: "every" at its source, "some" at its destination
-- person -has-mother-> person: every person has some mother (a person); Alice
-has-mother-> person (inherited): Alice has one, whoever she is. So:

- symmetric: A -r-> b (every A, b) gives b -r-> A (b, some A) -- but a -r-> T
  (a, some T) says nothing that can be put that way. Its source is any (!a),
  its destination an individual (?b).
- transitive: holds whatever the ends are (eg: a -r-> T and T -r-> c: a's T
  is, like every T, related to c), so all any (!a).
- reflexive, irreflexive, asymmetric: about objects themselves, so
  individuals (?a): person -r-> person isn't a person related to itself.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, shutil, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET = os.path.join(ROOT, "src", "sn", "model", "baseRules.snm")

def setUp() -> str:
  '''
  Make the temporary folder, and make it this process's home -- before sn is
  imported, as that reads the preferences from there (and logs there).

  :returns: The folder.
  :rtype: str
  '''
  folder = os.path.realpath(tempfile.mkdtemp(prefix="snBaseRules-")) # (resolved: on macOS, /var is /private/var)
  os.environ["HOME"] = folder
  os.environ["SN_NO_SAVE_PROMPT"] = "1"
  os.chdir(folder)
  sys.path[:0] = [os.path.join(ROOT, "src"), os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))]
  return folder

def makeBaseRules(path:str) -> None:
  '''
  :param path: Where to save the model.
  :type path: str
  '''
  from sn.model.model import Model, Node, Relation
  import sn.model.reasoner
  sn.model.reasoner.BASE_RULES[:] = [] # (it mustn't build on the old ones)
  m = Model(path)
  def rel(typ, src, dst):
    return Relation(m, [typ], src, dst, individual=True)
  def var(name):
    return Node(m, [m.NODE], individual=True, name=name)
  def relVar(constraints=None):
    r = Relation(m, [m.RELATION], name="^r")
    if constraints:
      r["constraints"] = constraints
    return r
  def rule(name, antecedent, consequent, note):
    r = Node(m, [m.RULE], individual=True, name=name)
    r["note"] = note
    for x in antecedent:
      rel(m.ANTECEDENT, r, x)
    for x in consequent:
      rel(m.CONSEQUENT, r, x)
  def constraint(name, pattern, report, note, message=None):
    c = Node(m, [m.CONSTRAINT], individual=True, name=name)
    c["note"] = note
    c["report"] = report
    if message:
      c["message"] = message
    for x in pattern:
      rel(m.CONTAINS, c, x)

  # ---- inferences ---------------------------------------------------------------
  a, b, r = var("!a"), var("?b"), relVar("symmetric")
  rule("symmetric", [rel(r, a, b)], [rel(r, b, a)],
       "a -r-> b gives b -r-> a, for a symmetric r and an individual b (a -r-> T says a relates to some T: not which one).")
  # Symmetric + transitive + irreflexive (eg: full-sibling) means "an
  # equivalence minus identity": plain transitivity would force x -r-> x for
  # anything related at all (x->y, y->x, so x->x), making the three tags
  # contradictory. So such a type's transitivity skips the diagonal. (A
  # transitive, irreflexive type that ISN'T symmetric keeps the plain rule:
  # there a self-pair can only come from a cycle -- a real error the
  # irreflexive constraint should catch.) Without "or" in a rule, that takes
  # three: plain transitivity unless it's symmetric, plain transitivity unless
  # it's irreflexive, and transitivity off the diagonal regardless.
  for name, tags, distinct in (("transitive", "transitive, symmetric: false", False),
                               ("transitive (not irreflexive)", "transitive, irreflexive: false", False),
                               ("transitive (off the diagonal)", "transitive", True)):
    a, b, c, r = var("!a"), var("!b"), var("!c"), relVar(tags)
    ante = [rel(r, a, b), rel(r, b, c)] + ([rel(m.DISTINCT, a, c)] if distinct else [])
    rule(name, ante, [rel(r, a, c)],
         "a -r-> b and b -r-> c give a -r-> c, for a transitive r" +
         {"transitive": " that isn't symmetric.",
          "transitive (not irreflexive)": " that isn't irreflexive.",
          "transitive (off the diagonal)": ", when a and c are different (see the other two)."}[name])
  a, r = var("?a"), relVar("reflexive")
  rule("reflexive (source)", [rel(r, a, None)], [rel(r, a, a)],
       "a -r-> anything gives a -r-> a, for a reflexive r.")
  a, r = var("?a"), relVar("reflexive")
  rule("reflexive (destination)", [rel(r, None, a)], [rel(r, a, a)],
       "anything -r-> a gives a -r-> a, for a reflexive r.")

  # ---- violations ---------------------------------------------------------------
  a, r = var("?a"), relVar("irreflexive")
  constraint("irreflexive", [rel(r, a, a)], "^r, ?a",
             "An irreflexive r relates nothing to itself.")
  a, b, r = var("?a"), var("?b"), relVar("asymmetric")
  constraint("asymmetric", [rel(r, a, b), rel(r, b, a)], "^r, ?a, ?b",
             "An asymmetric r relates nothing both ways (and so nothing to itself).")
  for p, q in (("reflexive", "irreflexive"), ("symmetric", "asymmetric"), ("reflexive", "asymmetric")):
    r = relVar(f"{p}, {q}")
    constraint(f"property_conflict ({p}, {q})", [r], f"^r, {p}, {q}",
               f"Nothing can be both {p} and {q}.")
    c = next(o for o in m.values() if o.name == f"property_conflict ({p}, {q})")
    c["code"] = "property_conflict"
  m.save()

def install(folder:str) -> None:
  '''
  Copy the model into src/sn/model/, stored as being in the placeholder folder
  -- and with the header's record of the program that wrote it neutralized --
  so nothing of this temporary folder is left in it.

  :param folder: Where it was made.
  :type folder: str
  '''
  from pathlib import Path
  from sn.model.reasoner import BASE_RULES_PLACEHOLDER
  with open(os.path.join(folder, "baseRules.snm"), encoding="utf-8") as fd:
    text = fd.read()
  text = text.replace(Path(folder).as_uri(), BASE_RULES_PLACEHOLDER).replace(os.path.abspath(sys.argv[0]), "Semantic Nets")
  assert folder not in text, f"baseRules.snm still mentions {folder}"
  with open(TARGET, "w", encoding="utf-8") as fd:
    fd.write(text)
  print("wrote", TARGET)

def main() -> None:
  folder = setUp()
  import atexit, sn
  atexit.unregister(sn.savePrefsIfChanged) # (nothing of the temporary user to keep)
  atexit.unregister(sn.saveAtExit)
  makeBaseRules(os.path.join(folder, "baseRules.snm"))
  install(folder)
  shutil.rmtree(folder, ignore_errors=True)

if __name__ == "__main__":
  main()
