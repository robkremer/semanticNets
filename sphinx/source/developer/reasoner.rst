
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

The rule base
-------------

``clingoReasoner.lp`` defines, over the facts:

- ``isa_star``: the reflexive-transitive isa closure (including types that
  rules conclude);
- ``holds(T,S,D)``: S is related to D under relation type T -- directly, by
  a subtype of T, by a relational property (symmetric, transitive, ...), by
  inheritance down the isa hierarchy, or by a rule;
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

- a rule's variables range over the model's data only, never over created
  objects (``base``/``individual`` rather than ``data``/``any_individual``),
  so a rule can't keep creating objects from its own creations;
- an object is created only if the data doesn't already have one doing the
  job (``_satisfied``) -- tested against *asserted* relations and types
  only, so the test doesn't depend on its own outcome.

Queries
-------

:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.answer` compiles a
query's pattern to an ``ans(...)`` rule, solves it with the model's facts
and the results of reasoning (a query's variables *do* range over created
objects), and returns one dict per match: variable to object.
:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.query` takes clingo
rules defining ``ans`` directly (the terminal's ``ask reasoner``).
