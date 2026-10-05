
The Reasoner
============

The reasoner works out what follows from a model. It's in two layers:

:py:mod:`sn.model.reasoner`
  The engine-independent part: the :py:class:`~sn.model.reasoner.Reasoner`
  interface, the export of a model as facts, the reading of rules,
  definitions and queries into patterns, and what an engine returns
  (:py:class:`~sn.model.reasoner.Inferences`,
  :py:class:`~sn.model.reasoner.Violation`).

:py:mod:`sn.model.clingoReasoner`
  The engine: :py:class:`~sn.model.clingoReasoner.ClingoReasoner`, built on
  `clingo <https://potassco.org/clingo/>`_, an answer set programming (ASP)
  system, with its rule base in ``clingoReasoner.lp``.

Engines register themselves by name (``class ClingoReasoner(Reasoner,
engine="clingo")``) and are made with
:py:meth:`Reasoner.create(model, engine) <sn.model.reasoner.Reasoner.create>`.
Another engine (eg: a description logic reasoner) would implement the same
interface; ``test/test_model/test_reasoner.py`` pins down the semantics every
engine must share.

Why ASP
-------

A semantic network's meaning -- inheritance, relational properties,
signatures, rules -- is naturally a set of logic rules over its structure,
and clingo evaluates such rules directly, to a fixed point, with negation
(for "unless a more specific relation says otherwise"). The rules are short,
declarative, and kept in one file (``clingoReasoner.lp``), separate from the
Python.

To keep relation types first-class -- in the isa hierarchy, and themselves
related -- while staying first-order, every GraphObject is *reified* as a
term ``o(N)``: "fred likes mary" is ``link(o(31), o(21), o(23))`` together
with ``parent(o(31), o(12))`` (the relation is a *likes*), not
``likes(fred, mary)``.

The pipeline
------------

.. graphviz::

   digraph pipeline {
     rankdir=LR;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];
     model [label="Model"];
     facts [label="Reasoner.facts()\nobj, parent, link, prop,\nattr, pattern, ..."];
     rules [label="_rulesProgram()\nthe user's rules and\ndefinitions, as clingo rules"];
     lp [label="clingoReasoner.lp\nthe rule base"];
     clingo [label="clingo\n(ground & solve)"];
     inf [label="Inferences\nholds, inferred, inherited,\nclassify, violation, fired, ..."];
     model -> facts -> clingo; model -> rules -> clingo; lp -> clingo; clingo -> inf;
   }

1. :py:meth:`~sn.model.reasoner.Reasoner.facts` exports the model as
   engine-neutral facts (their vocabulary is listed in the module's
   documentation). Pattern elements -- the contents of rules and queries --
   are exported too, but marked ``pattern``, so the rule base doesn't take
   them as facts about the world.
2. The user's rules and definitions are compiled to clingo rules (below).
3. clingo grounds and solves the facts, the compiled rules and the rule
   base together. The program is *stratified* (no recursion through
   negation), so there's exactly one answer set, and it's found without
   search.
4. The atoms shown (``#show``) are mapped back to GraphObjects, as an
   :py:class:`~sn.model.reasoner.Inferences`.

:py:func:`sn.model.reasoner.reason` runs this, keeps the result on the model
(``model.reasoning``), and notifies the model's observers with a
``("reasoned", (inferences,))`` topic: every view draws the results. They're
a snapshot -- not saved, and not updated as the model is edited -- until the
next ``reason()`` or :py:func:`~sn.model.reasoner.clearReasoning`.

What was inferred is also put in the model, as **inferred objects**
(:py:attr:`GraphObject.inferred <sn.model.model.GraphObject.inferred>`):
:py:func:`~sn.model.reasoner.materialize` makes a relation for each inferred
or inherited relation, and an isa link for each one the rules concluded
(objects the rules conclude exist aren't made yet). So the model's own
queries -- :py:meth:`~sn.model.model.GraphObject.getRelatedTo`, isa,
inherited attributes -- see them like anything else. They're kept apart from
what's asserted:

- they're **not saved** (the model's object table leaves them out), and
  adding or removing them doesn't make the model dirty, or go on the undo
  list -- even a write-locked model can be reasoned over (see
  :py:meth:`Model.inferring() <sn.model.model.Model.inferring>`);
- the reasoner **doesn't read them**: while it gathers its facts they're
  taken out of the model and put back afterwards
  (:py:func:`~sn.model.reasoner.withoutInferences`) -- otherwise an inferred
  isa link, say, would give its object the type's attributes, and justify
  itself;
- the next ``reason()`` **keeps** those still inferred (the same objects),
  adds the new ones, and removes the rest; ``clearReasoning()`` removes them
  all;
- they're **the reasoner's**: changing one's attributes raises
  ``PermissionError`` (``GraphObject._refuseIfInferred()``), and the model
  commands refuse to remove, reconnect or relate them, or make instances of
  them -- until the ``mark asserted`` command
  (:py:meth:`ModelContext.mark_asserted() <sn.controller.modelInterface.ModelContext.mark_asserted>`,
  undoable; not in a write-locked model) makes one asserted, with what has to
  come with it (:py:meth:`GraphObject.assertedWith() <sn.model.model.GraphObject.assertedWith>`:
  its inferred isa links, and a relation's inferred ends).

Views show the inferred relations between objects they show
(``SNGView._showInferred()``, on the ``"reasoned"`` topic) as ordinary view
objects that are drawn faded (``VObject.isInferred()``; the vis cache fades
their colours toward the background) with dashed lines -- dotted for
inherited ones (the relation's ``inferredKind``). They take part in layouts
like anything else, but aren't saved with the view, and neither they nor the
model's inferred objects count when a view or model checks whether it's dirty.

The rule base
-------------

``clingoReasoner.lp`` defines, over the facts:

- ``isa_star``: the reflexive-transitive isa closure (including types that
  rules conclude);
- ``holds(T,S,D)``: S is related to D under relation type T -- directly, by
  a subtype of T, by inheritance down the isa hierarchy, or by a rule
  (including the base rules: see below);
- ``inferred`` and ``inherited``: the holds that weren't asserted (and
  aren't implied by a more specific relation type);
- ``classify(X,C)``: a type that would make a relation's end fit its
  signature;
- ``violation(Code, Severity, Subject, Args)``: the problems, whose codes
  are turned into messages by ``reasoner._MESSAGES``.

Rules and definitions
---------------------

:py:func:`~sn.model.reasoner.patternOf` reads a context (or some of its
panes) into a :py:class:`~sn.model.reasoner.Pattern`: its variables,
constants, relations, isa links and constraints.
:py:func:`~sn.model.reasoner.ruleOf` reads a rule into a
:py:class:`~sn.model.reasoner.RuleSpec`: the antecedent's pattern, and the
consequent's conclusions -- relations (``heads``), attribute values
(``assertions``), types (``isas``), and the variables that only the
consequent has (``new``: objects to create). A definition is two RuleSpecs,
one each way (:py:func:`~sn.model.reasoner.definitionSpecs`). Problems found
on the way (eg: a consequent relation with no end) are recorded in the
spec, and reported instead of compiling the rule.

``ClingoReasoner._rulesProgram`` then compiles each spec to one clingo rule
per conclusion, the antecedent as the body (``_patternBody``):

.. code-block:: none

   fired(Rule, T, S, D)        :- <antecedent>.    % a relation
   rule_attr(Rule, X, Key, V)  :- <antecedent>.    % an attribute value
   rule_isa(Rule, X, Type)     :- <antecedent>.    % a type

and the rule base feeds these back in, as ``holds``, ``attr`` and isa. So
rules chain: one rule's conclusions can satisfy another's antecedent.

New objects
~~~~~~~~~~~

A consequent-only variable stands for an object that exists for each match.
It's represented by a term that's a function of the match --
``new(Rule, Name, ((Var, Value), ...))`` -- so there's exactly one per match,
and reported as a :py:class:`~sn.model.reasoner.NewObject`. Two things keep
this finite and stratified:

- the variables of a rule that creates objects range over the model's data
  only, never over created objects (``base``/``individual`` rather than
  ``data``/``any_individual``), so it can't keep creating objects from its
  own creations (a rule that creates nothing can't run away, so its
  variables range over all the data, created objects included);
- an object is created only if the data doesn't already have one doing the
  job (``_satisfied``) -- tested against *asserted* relations and types
  only, so the test doesn't depend on its own outcome.

Constraints
-----------

:py:func:`~sn.model.reasoner.constraintOf` reads a constraint into a
:py:class:`~sn.model.reasoner.ConstraintSpec`: its pattern, and from its
attributes the violation's code, severity, what it reports (subject first)
and message. Each compiles to one clingo rule:

.. code-block:: none

   violation0(Code, Severity, Subject, (Args,)) :- <pattern>.

:py:meth:`~sn.model.reasoner.Reasoner._finish` -- which every engine passes
its results through -- reports a violation once per set of objects it's
about (so a constraint matching a-b and b-a reports it once), and gives a
constraint's violations its message.

The base rules
--------------

The meaning of the relational properties (symmetric, transitive, reflexive,
irreflexive, asymmetric) isn't in ``clingoReasoner.lp``: it's ordinary rules
and constraints, in a model of **base rules** (``sn/model/baseRules.snm``,
made by ``tools/makeBaseRules.py``) that every reasoner applies to every
model (:py:meth:`~sn.model.reasoner.Reasoner.ruleObjects`), so a new engine
gets them by translating rules, with nothing more to write. They use "any"
variables (``!a``: individuals and types alike) and a relation-type variable
(``?r``) tagged with the property, eg: ``!a -?r-> !b`` with ``?r
{symmetric}`` concludes ``!b -?r-> !a``.

:py:data:`~sn.model.reasoner.BASE_RULES` lists the base rules' models, and
an application can change it (eg: to base rules of its own), before it makes
or reads a model. :py:func:`~sn.model.reasoner.baseRuleModels` reads them
(write-locked) once. Like the system model, they're super-models of every
model (:py:meth:`~sn.model.model.Model.implicitSuperDBs`): they can't be
removed, and aren't saved with it (the file read may be a temporary copy of
package data), but are added again when it's read.
:py:meth:`~sn.model.reasoner.Reasoner.objects` leaves them out: their
objects aren't facts, and their conclusions are reported as plain
inferences, unless the ``reasoner/showSysRules`` preference (or the
reasoner's *showSysRules*) is on.

Queries
-------

:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.answer` compiles a
query's pattern to an ``ans(...)`` rule, solves it with the model's facts
and the results of reasoning (a query's variables *do* range over created
objects), and returns one dict per match: variable to object.
:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.query` takes clingo
rules defining ``ans`` directly (the terminal's ``ask reasoner``).
