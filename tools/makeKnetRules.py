'''
Make the KNet rules model that comes with the Rep Plus Net Reader plugin --
plugins/rnetReader/knet.snm -- from scratch: the relation types of the kernel
of Brian Gaines's protologic (Gaines, 2015, *Universal Logic as a Science of
Patterns*, sections 2.2 to 2.8), and its inference patterns, as ordinary rules
and constraints, which every reasoner applies to the models built on it (the
reader's models are: see *rnetReader.reader.ONTOLOGY*).

  python3.14 tools/makeKnetRules.py

It builds the model in a temporary folder, as a temporary user (HOME), so it
never touches your files or preferences; and then copies it into
plugins/rnetReader/, stored as being in *PLACEHOLDER* (it's read from
wherever the plugin is: see *rnetReader.reader.ONTOLOGY*).

X includes Y (X -> Y) means that whatever is X is Y (X's extension is in
Y's): eg, dog includes animal. The kernel:

- includes: transitive (a preorder: every node includes itself, too, but that
  isn't concluded -- it adds nothing to what follows, and would loop every
  node).
- equivalent: an SN subtype of includes, symmetric: each includes the other
  (concluded, below, for any two that do). It needn't be transitive: two
  equivalences in a row are two pairs of includes, which concludes the third.
- excludes: symmetric: nothing is both (their extensions don't overlap).
- coexcludes: symmetric: everything is one or the other (their extensions
  cover everything).
- negates: an SN subtype of excludes and coexcludes (structural negation),
  symmetric: each is the other's complement.
- inconsistent: an SN subtype of includes and excludes, as Gaines's
  inconsistent link combines them: X can only be empty.

The rules (each of the paper's patterns that the symmetric ones don't already
give; transitivity and symmetry are the base rules' -- see
tools/makeBaseRules.py):

- exclusion: N includes T, T excludes H => N excludes H (whatever includes the
  tail is excluded from the head).
- coexclusion: N excludes H, T coexcludes H => N includes T (whatever excludes
  the head includes the tail).
- coexclusion inherited: T includes U, T coexcludes H => U coexcludes H (it's
  inherited "down" the reverse of includes).
- negation: A excludes B and coexcludes B => A negates B. (Two negations of
  one node make them equivalent: that follows -- see coexclusion.)
- equivalence: A includes B and B includes A (A and B distinct) => A
  equivalent B.
- inconsistency: A includes B and excludes B => A inconsistent B.
- self-inconsistency: A excludes A => A inconsistent A (any node with an
  inconsistent link has one to itself: whatever it includes, it excludes).
- symmetric (types too): A excludes B => B excludes A, and likewise for
  coexcludes and equivalent (and so negates), whether A and B are individuals
  or types: the base rules' symmetric only concludes it toward an individual.
- isa: ^A isa ^B (SN types), ^B isa knode (but isn't it) => ^A includes ^B:
  every isa link is an inclusion (not the other way round), so the kernel's
  inferences run over ordinary type hierarchies too -- those under *KNODE*,
  an SN subtype of node (see *isaRule()*).

Truth marks (the paper's section 4.2): a node marked true (T) or false (F)
-- its *MARK_TRUE* or *MARK_FALSE* attribute, whose value says how it got it
(see rnetReader.hooks): "asserted", or one of these rules' (Rep Plus's mark
kinds, which say how):

- true by inclusion: A is true, A includes B => B is true ("included").
- false by exclusion: A is true, A excludes B => B is false ("excluded").
- false by inclusion: A is false, B includes A => B is false ("irrelevant",
  Rep Plus calls it).
- true by coexclusion: A is false, A coexcludes B => B is true ("coexcluded").
- false by inconsistency: A excludes A => A is false ("necessary": an
  inconsistent node can only be empty) -- and its dual, true by coexclusion
  with itself: A coexcludes A => A is true ("necessary": everything is A).

(Equivalence and negation follow: they're includes, and excludes and
coexcludes.) A node can be both (Belnap's "both": inconsistent), as asserted
or as concluded. What a node has asserted stands: a rule's conclusion of the
same mark only says so.

*KNODE*'s nodes show their marks as bars beside them (vis/sideBars: see
rnetReader.hooks.markBars()), and have menu items to assert and clear them.

The structural connectives (the paper's section 5), as relation types
(*CONNECTIVES*: see *connectives()*) tagged so that the reasoners draw
Gaines's iterative clause (see sn.model.reasoner.DEFINING):

- conjunct includes (heavy arrowheads), an SN subtype of includes, and
  conjunct excludes (with a bar), of excludes: C is the conjunction of the
  nodes it has them to -- whatever includes each of those (and excludes
  each it conjunct excludes) includes C.
- disjunct includes (double arrowheads), of includes, and disjunct
  coexcludes (with two bars), of coexcludes: D is the disjunction of the
  nodes that have them to it -- D includes whatever each of those includes
  (and each that disjunct coexcludes it coexcludes).

And their marks ("definition"): a conjunction is true when its conjuncts all
are (and those it excludes false), and a disjunction false when its
disjuncts all are (and those that coexclude it true); a false conjunction
whose conjuncts but one are true makes that one false, and a true
disjunction whose disjuncts but one are false makes that one true -- unless
one of them is marked both (as KNet doesn't: disjunctive syllogism from a
contradiction). (That a false conjunct makes its conjunction false, and a
true disjunct its disjunction true, is what includes says already.)

And one constraint, a warning: an inconsistent node (one that excludes
itself: see self-inconsistency) -- Rep Plus marks it "E". Inconsistency stays
where it is (Gaines's paraconsistency): it propagates only through the
patterns above, and nothing else follows from it.

The variables are "any" (!a): the patterns hold of nodes whether they're
individuals (as in the reader's models) or types.

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import os, sys, shutil, tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TARGET = os.path.join(ROOT, "plugins", "rnetReader", "knet.snm")
PLACEHOLDER = "file:///SEMANTIC_NETS_PLUGINS/rnetReader"
"Where the model is stored as being (the folder): it's wherever the plugin is installed."

INCLUDES, EQUIVALENT, EXCLUDES, COEXCLUDES, NEGATES, INCONSISTENT = \
  "includes", "equivalent", "excludes", "coexcludes", "negates", "inconsistent"
"The kernel relation types' names (see *rnetReader.reader.KERNEL*, which must agree)."

KNODE = "knode"
'''The SN type of the types whose isa links are inclusions (see *isaRule()*):
eg, dog isa animal isa knode gives dog includes animal.'''

MARK_TRUE, MARK_FALSE = "markTrue", "markFalse"
"The attributes that mark a node true or false (see *rnetReader.hooks*, which must agree)."

DEFINITION = "definition"
"How a node got a mark through a connective (Rep Plus's mark kind: see *rnetReader.hooks.MARK_COLORS*)."

CONJUNCT_INCLUDES, CONJUNCT_EXCLUDES, DISJUNCT_INCLUDES, DISJUNCT_COEXCLUDES = \
  "conjunct includes", "conjunct excludes", "disjunct includes", "disjunct coexcludes"
CONNECTIVES = (CONJUNCT_INCLUDES, CONJUNCT_EXCLUDES, DISJUNCT_INCLUDES, DISJUNCT_COEXCLUDES)
"The connectives' relation types' names (see *connectives()*, and *rnetReader.reader.CONNECTIVES*, which must agree)."

HEAVY_ARROW = "arrow(11,13,6)"
"A heavy arrowhead (a conjunction's: see *rnetReader.reader.HEAVY_ARROW*)."

HOOKS = "snplugins.rnetReader.hooks"
"The module of the hooks *KNODE* names (see *rnetReader.hooks*): the plugin's, once it's loaded."

INCONSISTENT_NODE = "inconsistent node"
"The constraint (and its violations' code) that reports an inconsistent node."

def setUp() -> str:
  '''
  Make the temporary folder, and make it this process's home -- before sn is
  imported, as that reads the preferences from there (and logs there).

  :returns: The folder.
  '''
  folder = os.path.realpath(tempfile.mkdtemp(prefix="snKnetRules-")) # (resolved: on macOS, /var is /private/var)
  os.environ["HOME"] = folder
  os.environ["SN_NO_SAVE_PROMPT"] = "1"
  os.chdir(folder)
  sys.path[:0] = [os.path.join(ROOT, "src"), os.path.abspath(os.path.join(ROOT, "..", "pythonUtils", "src"))]
  return folder

def makeKnetRules(path:str) -> None:
  '''
  :param path: Where to save the model.
  '''
  from sn.model.model import Model, Node, Relation
  m = Model(path)
  def relType(name, parents, note, terminator="", mid="", color="#000000", **tags):
    r = Relation(m, parents or [m.RELATION], None, None, name=name)
    for k, v in tags.items():
      r[k] = v
    # Drawn as Gaines does (and Rep Plus): no label, its kind by its marks.
    # And after reasoning, a view leaves out what's implied by what it shows:
    # cycles' loops, the mirrors of symmetric ones, includes beside an
    # equivalent...
    r["vis/label"] = ""
    if not parents:
      r["vis/hideImplied"] = True
    r["vis/terminator4"] = terminator
    r["vis/midMarks"] = mid
    r["vis/lineType"] = "straight"
    r["vis/lineColor"] = color
    r["vis/lineFillColor"] = color
    if parents: # (its note's kind is theirs)
      r["note"] = note
    else:
      r.setAttr("note", typeNote(note))
    return r
  inc = relType(INCLUDES, None, "X includes Y (X -> Y): whatever is X is Y (eg: dog includes animal). Transitive.",
                terminator="arrow", transitive=True)
  equ = relType(EQUIVALENT, [inc], "X and Y include each other. Concluded for any two that do.",
                terminator="", symmetric=True)
  equ["vis/terminator1"] = "arrow"
  equ["vis/terminator4"] = "arrow"
  exc = relType(EXCLUDES, None, "Nothing is both X and Y: whatever includes one is excluded from including the other. Symmetric.",
                mid="|", color="#008a00", symmetric=True)
  coe = relType(COEXCLUDES, None, "Everything is X or Y: whatever excludes one includes the other. Symmetric.",
                mid="||", color="#0000c0", symmetric=True)
  neg = relType(NEGATES, [exc, coe], "X is everything Y isn't (structural negation): X excludes and coexcludes Y. Symmetric.",
                mid="|||", symmetric=True)
  inco = relType(INCONSISTENT, [inc, exc], "X both includes and excludes Y (Gaines's inconsistent link): X can only be empty.",
                 terminator="| arrow", color="#d00000")
  connectives(m, relType, inc, exc, coe)
  def rel(typ, src, dst):
    return Relation(m, [typ], src, dst, individual=True)
  def var(name, constraints=None):
    ret = Node(m, [m.NODE], individual=True, name=name)
    if constraints:
      ret["constraints"] = constraints
    return ret
  def rule(name, antecedent, consequent, note):
    r = Node(m, [m.RULE], individual=True, name=name)
    r["note"] = note
    for part, xs in ((r.partFor(m.ANTECEDENT), antecedent), (r.partFor(m.CONSEQUENT), consequent)):
      for x in xs:
        rel(m.CONTAINS, part, x)
    return r
  def constraint(name, pattern, report, note, message):
    c = Node(m, [m.CONSTRAINT], individual=True, name=name)
    c["note"] = note
    c["report"] = report
    c["severity"] = "warning"
    c["message"] = message
    for x in pattern:
      rel(m.CONTAINS, c, x)
    return c

  # ---- inferences ---------------------------------------------------------------
  n, t, h = var("!n"), var("!t"), var("!h")
  rule("exclusion", [rel(inc, n, t), rel(exc, t, h)], [rel(exc, n, h)],
       "n includes t, t excludes h => n excludes h: whatever includes the tail of an exclusion is excluded from its head.")
  n, t, h = var("!n"), var("!t"), var("!h")
  rule("coexclusion", [rel(exc, n, h), rel(coe, t, h)], [rel(inc, n, t)],
       "n excludes h, t coexcludes h => n includes t: whatever excludes the head of a coexclusion includes its tail.")
  t, u, h = var("!t"), var("!u"), var("!h")
  rule("coexclusion inherited", [rel(inc, t, u), rel(coe, t, h)], [rel(coe, u, h)],
       "t includes u, t coexcludes h => u coexcludes h: what includes more covers more.")
  a, b = var("!a"), var("!b")
  rule("negation", [rel(exc, a, b), rel(coe, a, b)], [rel(neg, a, b)],
       "a excludes b and coexcludes b => a negates b (structural negation).")
  a, b = var("!a"), var("!b")
  rule("equivalence", [rel(inc, a, b), rel(inc, b, a), rel(m.DISTINCT, a, b)], [rel(equ, a, b)],
       "a includes b and b includes a => a equivalent b (a cycle of inclusions).")
  a, b = var("!a"), var("!b")
  rule("inconsistency", [rel(inc, a, b), rel(exc, a, b)], [rel(inco, a, b)],
       "a includes b and excludes b => a inconsistent b (Gaines's inconsistent link).")
  a = var("!a")
  rule("self-inconsistency", [rel(exc, a, a)], [rel(inco, a, a)],
       "a excludes a => a inconsistent a: a node with an inconsistent link has one to itself.")
  # The base rules' symmetry is only toward an individual (in SN, dog -r-> plant
  # says every dog is r-related to some plant: see tools/makeBaseRules.py), but
  # between KNet concepts it holds whatever they are (animal excludes plant:
  # plant excludes animal). One rule each, of the kernel type (not a ^r: an
  # attribute to pick them by would be inherited by the reader's link types,
  # concluding links of those). Negation follows from the other two.
  for typ in (exc, coe, equ):
    a, b = var("!a"), var("!b")
    rule(f"{typ.name} symmetric (types too)", [rel(typ, a, b)], [rel(typ, b, a)],
         f"a {typ.name} b => b {typ.name} a, whether a and b are individuals or types (eg: under knode): the base "
         "rules' symmetric only concludes it toward an individual.")
  isaRule(m, inc, rule)

  # ---- marks ----------------------------------------------------------------------
  # (Each concludes the mark on its own copy of the variable: a consequent's
  # variable's constraints are what the rule concludes of it.)
  # (In this order: where rules conclude different values of a mark, a node gets the first's -- see
  # sn.model.reasoner.materialize() -- so an inconsistent node is false necessarily, and the others' as
  # KNet has them: eg, true by inclusion rather than by coexclusion.)
  for name, typ, concluded, note in (
      ("false by inconsistency", exc, MARK_FALSE,
       "a excludes a => a is false, necessarily: an inconsistent node can only be empty."),
      ("true by coexclusion with itself", coe, MARK_TRUE,
       "a coexcludes a => a is true, necessarily: everything is a (the dual of false by inconsistency).")):
    a = var("!a")
    rule(name, [rel(typ, a, a)], [var("!a", f"{concluded}: necessary")], note)
  for name, mark, typ, forward, concluded, how, note in (
      ("true by inclusion", MARK_TRUE, inc, True, MARK_TRUE, "included",
       "a is true, a includes b => b is true: what something true includes is true."),
      ("false by exclusion", MARK_TRUE, exc, True, MARK_FALSE, "excluded",
       "a is true, a excludes b => b is false."),
      ("false by inclusion", MARK_FALSE, inc, False, MARK_FALSE, "irrelevant",
       "a is false, b includes a => b is false: whatever includes something false is false (Rep Plus calls the "
       "mark \"irrelevant\")."),
      ("true by coexclusion", MARK_FALSE, coe, True, MARK_TRUE, "coexcluded",
       "a is false, a coexcludes b => b is true.")):
    a, b = var("!a", mark), var("!b")
    rule(name, [rel(typ, a, b) if forward else rel(typ, b, a), rel(m.DISTINCT, a, b)], # (not from itself: a node
         [var("!b", f"{concluded}: {how}")], note)                                     # includes itself, too)

  # ---- violations ---------------------------------------------------------------
  a = var("!a")
  constraint(INCONSISTENT_NODE, [rel(exc, a, a)], "!a",
             "A node that excludes itself (it includes and excludes something) is inconsistent: nothing can be it. "
             "(It's a warning: the inconsistency stays local -- Gaines's paraconsistency.)",
             "{0} is inconsistent: it includes something it excludes (Rep Plus's E)")
  m.save()

def connectives(m, relType, inc, exc, coe) -> None:
  '''
  Add *CONNECTIVES*: the links that define Gaines's structural conjunctions
  and disjunctions (the paper's section 5), tagged so that the reasoners
  draw his iterative clause (see *sn.model.reasoner.DEFINING*), in the
  order includes, with the truth marks: a conjunction (heavy arrowheads)
  is what includes each of its conjuncts (and excludes each it excludes), a
  disjunction (double arrowheads) what each of its disjuncts includes (and
  what each that coexcludes it doesn't).
  '''
  for name, parent, key, requires, terminator, color, note in (
      (CONJUNCT_INCLUDES, inc, "meet", INCLUDES, HEAVY_ARROW, "#000000",
       "C conjunct includes A: C is the conjunction (the meet) of what it conjunct includes, and excludes by conjunct "
       "excludes -- an includes, and whatever includes all of them (and excludes those) includes C. C is true when "
       "they all are (and those false); false C, all of them but one true: that one's false (unless one is marked both)."),
      (CONJUNCT_EXCLUDES, exc, "meet", EXCLUDES, f"| {HEAVY_ARROW}", "#008a00",
       "C conjunct excludes B: B's negation is one of C's conjuncts (see conjunct includes) -- an excludes."),
      (DISJUNCT_INCLUDES, inc, "join", INCLUDES, ">>", "#000000",
       "A disjunct includes D: D is the disjunction (the join) of what disjunct includes it, and coexcludes it by "
       "disjunct coexcludes -- an includes, and D includes whatever all of them include (and those coexclude). D is "
       "false when they all are (and those true); true D, all of them but one false: that one's true (unless one is marked both)."),
      (DISJUNCT_COEXCLUDES, coe, "join", COEXCLUDES, "|| >>", "#0000c0",
       "B disjunct coexcludes D: B's negation is one of D's disjuncts (see disjunct includes) -- a coexcludes.")):
    r = relType(name, [parent], note, terminator=terminator, color=color)
    r[key] = requires
    r["order"] = INCLUDES
    r["trueMark"], r["falseMark"], r["markValue"] = MARK_TRUE, MARK_FALSE, DEFINITION

def typeNote(text:str):
  '''
  :returns: A type's note: text, that its subtypes and instances can change (as
    the reader's link types do: see *rnetReader.reader.note()*).
  '''
  from util.attribute import Attribute, VAR_DEFAULTED
  return Attribute(text, "text", VAR_DEFAULTED)

def isaRule(m, inc, rule) -> None:
  '''
  Add *KNODE* -- with its marks' bars and menu items (see *rnetReader.hooks*)
  -- and the rule that an isa link between SN types under it is an
  inclusion: ^a isa ^b, ^b isa knode (and isn't it) => ^a includes ^b. Type variables (^a),
  so it's about type hierarchies -- not an individual and its types (the
  reader's models' individuals are of drawing types, eg: "Concept", which
  aren't concepts of the net). And only those under *KNODE*, not every type:
  else every type would include node and top, SN's own, and the relation
  types would include relation (and the reader's link types their kernel
  types).
  '''
  from sn.model.model import Node, Relation, IsaIndividual
  knode = Node(m, [m.NODE], name=KNODE)
  knode.setAttr("note", typeNote("A node of a KNet net: its instances are (eg: the reader's nodes), and so are the SN types under "
                   "it, whose isa links are inclusions: eg, dog isa animal isa knode gives dog includes animal (so a type "
                   "that excludes animal excludes dog). They show their truth marks as bars (markTrue: beside them; "
                   "markFalse: over them), and their menus mark them."))
  knode["vis/sideBars"] = f"$({HOOKS}:markBars)"
  for item, fn in (("Mark/True", "markTrue"), ("Mark/False", "markFalse"), ("Mark/Clear", "clearMarks")):
    knode[f".menu/{item}"] = f"{HOOKS}:{fn}"
  a, b = Node(m, [m.NODE], name="^a"), Node(m, [m.NODE], name="^b")
  rule("isa", [IsaIndividual(m, a, b), IsaIndividual(m, b, knode), Relation(m, [m.DISTINCT], a, b, individual=True),
               Relation(m, [m.DISTINCT], b, knode, individual=True)],
       [Relation(m, [inc], a, b, individual=True)],
       "^a isa ^b => ^a includes ^b, for types under knode (not knode itself): every isa link is an inclusion (but "
       "not every inclusion is an isa link).")

def install(folder:str) -> None:
  '''
  Copy the model into plugins/rnetReader/, stored as being in *PLACEHOLDER*
  -- and with the header's record of the program that wrote it neutralized --
  so nothing of this temporary folder is left in it.

  :param folder: Where it was made.
  '''
  from pathlib import Path
  with open(os.path.join(folder, "knet.snm"), encoding="utf-8") as fd:
    text = fd.read()
  text = text.replace(Path(folder).as_uri(), PLACEHOLDER).replace(os.path.abspath(sys.argv[0]), "Semantic Nets")
  assert folder not in text, f"knet.snm still mentions {folder}"
  with open(TARGET, "w", encoding="utf-8") as fd:
    fd.write(text)
  print("wrote", TARGET)

def main() -> None:
  folder = setUp()
  import atexit, sn
  atexit.unregister(sn.savePrefsIfChanged) # (nothing of the temporary user to keep)
  atexit.unregister(sn.saveAtExit)
  makeKnetRules(os.path.join(folder, "knet.snm"))
  install(folder)
  shutil.rmtree(folder, ignore_errors=True)

if __name__ == "__main__":
  main()
