%################################################################################
% (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
%################################################################################
%
% Rule base for sn.model.prologReasoner.PrologReasoner (SWI-Prolog, through its
% Python interface, janus). A port of clingoReasoner.lp: see there for the
% input facts, the results, and what each rule means. Where it differs:
%
% - Every GraphObject is the atom '#N' (clingo's o(N): Prolog finds a fact by
%   an atom argument, but not by the number inside a compound term). The
%   model's attributes are given as attr_base/3.
% - It works in two steps. First, the closure: what the rules conclude, and
%   all it depends on, worked out together. Prolog's tabling (with the
%   well-founded semantics) does what clingo's grounding does here: these
%   predicates are tabled, so recursion ends, and negating one is tnot/1
%   (not_exists/1 when what it tests isn't all bound); negating an input fact
%   is \+. While the rules run, holds/3, isa_star/2 and attr/3 are r_holds/3,
%   r_isa_star/2 and r_attr/3; the user's rules (see
%   PrologReasoner._rulesProgram()) use those.
% - Then (see sn_close/0) the closure's results are stated as facts --
%   holds/3, isa_star/2 and attr/3 -- and the rest (what's inferred,
%   inherited, the violations, the user's constraints, queries) is read from
%   them by plain Prolog. (A tabled call makes a table for each call: a
%   question about a given triple would work it out again. A fact is found by
%   its arguments.) Only the closure's true answers are kept: if the user's
%   rules make a loop through a negation, what depends on it may be
%   undefined, and is left out.
% - A tabled predicate needs a clause for tnot/1 to see it as false: those
%   that may have none (the user's rules add them) get "p(...) :- fail."
% - Prolog runs a clause's body in order: a body binds its variables before
%   it tests them (\==, a negation), and starts with what it has bound (a
%   predicate called with an argument bound finds its facts by it).
% - A clause's head has no compound term with variables in it (a created
%   object's term): the body makes it, last -- or a call with the same
%   variable in two places would unify a variable with a term holding it.
% - Tuples are lists: violation(Code,Severity,Subject,[Arg,...]).
% - The objects the rules create are new(Rule,Var,[[Name,Value],...]) -- as
%   clingo's new(Rule,Var,((Name,Value),...)) -- and a cardinality's are
%   card(T,of,X) (or to).
%
% The rules (see sn.model.reasoner.ruleOf()) and constraints are added to this
% program as clingo's are (see PrologReasoner._rulesProgram()), in the same
% file: the input facts follow this rule base, then the rules.

:- set_prolog_flag(double_quotes, string).

% The input facts (some models have none of some).
:- dynamic obj/1, individual/1, kind/2, collection/1, name/2, const/2, parent/2, lsrc/2, ldst/2,
   domain/2, range/2, src/2, dst/2, link/3, prop/2, member/2, pattern/1, var_kind/2, attr_base/3,
   lattr/2, card/4, card_error/3.

% What the user's rules and constraints add to.
:- discontiguous fired/4, rule_attr/4, rule_isa/3, rule_new/1, violation0/4, requirement_holds/2.
:- dynamic requirement_holds/2.

type(O) :- obj(O), \+ individual(O).
rel_type(T) :- kind(T,relation), \+ individual(T).

% Pattern elements: see clingoReasoner.lp.
data(X) :- obj(X), \+ pattern(X).
data(N) :- new_obj(N).

base(X) :- obj(X), \+ pattern(X).
any_individual(X) :- individual(X).
any_individual(N) :- new_obj(N).

% A created object: rule_new/1 (a compound term; not for a model's object: a tabled call for each would make a table for each).
new_obj(N) :- ( var(N) -> rule_new(N) ; compound(N), rule_new(N) ).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% The closure ---------------------------------------------------------------

:- table r_isa_star/2, isa_base/2, asserted/3, asserted_under/3, link_holds/3, refined/3, r_holds/3,
   same/2, card_of/3, card_has/3, card_new/3, fired/4, rule_attr/4, rule_isa/3, rule_new/1, r_attr/3.

fired(_,_,_,_) :- fail.
rule_attr(_,_,_,_) :- fail.
rule_isa(_,_,_) :- fail.
rule_new(_) :- fail.

%%% Type hierarchy

r_isa_star(X,X) :- obj(X).
r_isa_star(X,Z) :- parent(X,Y), r_isa_star(Y,Z).
r_isa_star(N,N) :- new_obj(N).
r_isa_star(X,Z) :- rule_isa(_,X,Y), r_isa_star(Y,Z).
r_isa_star(Y,T) :- same(X,Y), r_isa_star(X,T), T \== X.
isa_base(X,X) :- obj(X).
isa_base(X,Z) :- parent(X,Y), isa_base(Y,Z).

%%% Relations

asserted(T,S,D) :- ( var(T) -> link_asserted(T,S,D) ; rel_type(T), parent(R,T), link(R,S,D) ).
link_asserted(T,S,D) :- link(R,S,D), parent(R,T), rel_type(T).
asserted_under(T,S,D) :- asserted(T2,S,D), isa_base(T2,T), rel_type(T).

link_holds(T,S,D) :- asserted(T,S,D).
link_holds(T,X,D) :- ( var(X) -> link_holds(T,S,D), parent(X,S) ; parent(X,S), link_holds(T,S,D) ),
                     data(X), tnot(refined(T,X,D)).
link_holds(T,X,D) :- ( var(X) -> link_holds(T,S,D), rule_isa(_,X,S) ; rule_isa(_,X,S), link_holds(T,S,D) ),
                     data(X), tnot(refined(T,X,D)).
refined(T,X,D) :- asserted(T,_,D), asserted(T2,X,D2), isa_base(T2,T), isa_base(D2,D), (T2,D2) \== (T,D).

r_holds(T,S,D) :- link_holds(T,S,D).
r_holds(T,S,D) :- fired(_,T,S,D).
% (Of T2's children, only its subtypes: the others are its relations, which relate nothing -- but a
% call r_holds(R,S,D) for each, with S bound, would make a table for each relation and object.)
r_holds(T2,S,D) :- ( var(T2) -> r_holds(T,S,D), parent(T,T2), rel_type(T2) ; rel_type(T2), parent(T,T2), rel_type(T), r_holds(T,S,D) ).
r_holds(T,S,Y) :- same(X,Y), r_holds(T,S,X).
r_holds(T,Y,D) :- same(X,Y), r_holds(T,X,D).

%%% Cardinality: objects that must be the same, and the objects it creates

same(D1,D2) :- card(T,out,_,1), r_holds(T,S,D1), new_obj(D1), r_holds(T,S,D2), D1 \== D2.
same(S1,S2) :- card(T,in,_,1), r_holds(T,S1,D), new_obj(S1), r_holds(T,S2,D), S1 \== S2.
same(X,Y) :- same(Y,X).
same(X,Z) :- same(X,Y), same(Y,Z), X \== Z.

card_top(C) :- const(top,C).
card_of(T,out,X) :- card(T,out,Min,_), Min > 0, domain(T,C), \+ card_top(C), r_isa_star(X,C), base(X), individual(X), kind(X,node).
card_of(T,in,X) :- card(T,in,Min,_), Min > 0, range(T,C), \+ card_top(C), r_isa_star(X,C), base(X), individual(X), kind(X,node).
card_has(T,out,X) :- asserted_under(T,X,_).
card_has(T,in,X) :- asserted_under(T,_,X).
card_new(T,out,X) :- card_of(T,out,X), card(T,out,_,1), tnot(card_has(T,out,X)).
card_new(T,in,X) :- card_of(T,in,X), card(T,in,_,1), tnot(card_has(T,in,X)).
% (The new objects' terms are made once X is bound: a head card(T,of,X) would
% make a cyclic term of a call like r_holds(T,S,S), unifying S with card(T,of,S).)
rule_new(N) :- card_new(T,out,X), N = card(T,of,X).
fired(T,T,X,N) :- card_new(T,out,X), N = card(T,of,X).
rule_isa(T,N,C) :- card_new(T,out,X), range(T,C), \+ card_top(C), N = card(T,of,X).
rule_new(N) :- card_new(T,in,X), N = card(T,to,X).
fired(T,T,N,X) :- card_new(T,in,X), N = card(T,to,X).
rule_isa(T,N,C) :- card_new(T,in,X), domain(T,C), \+ card_top(C), N = card(T,to,X).

%%% Attributes

r_attr(X,K,V) :- attr_base(X,K,V).
r_attr(X,K,V) :- rule_attr(_,X,K,V).
r_attr(Y,K,V) :- same(X,Y), r_attr(X,K,V).

%%% Nodes defined by their links (Gaines's structural connectives): see clingoReasoner.lp

:- dynamic def_part/6, def_last/5, def_marks/5, def_mixed/2.
:- table def_ok/4, def_holds/3, def_fails/3, def_hpre/3, def_hsuf/3, def_fpre/3, def_fsuf/3.

def_ok(C,meet,X,1) :- def_part(C,meet,1,A,P,_), r_holds(P,X,A).
def_ok(C,meet,A,1) :- def_part(C,meet,1,A,_,pos).
def_ok(C,meet,X,J) :- def_ok(C,meet,X,I), J is I+1, def_part(C,meet,J,A,P,_), r_holds(P,X,A).
def_ok(C,meet,A,J) :- def_ok(C,meet,A,I), J is I+1, def_part(C,meet,J,A,_,pos).
def_ok(C,join,X,1) :- def_part(C,join,1,A,P,_), r_holds(P,A,X).
def_ok(C,join,A,1) :- def_part(C,join,1,A,_,pos).
def_ok(C,join,X,J) :- def_ok(C,join,X,I), J is I+1, def_part(C,join,J,A,P,_), r_holds(P,A,X).
def_ok(C,join,A,J) :- def_ok(C,join,A,I), J is I+1, def_part(C,join,J,A,_,pos).
fired(R,Q,X,C) :- def_last(C,meet,N,Q,R), def_ok(C,meet,X,N), X \== C.
fired(R,Q,C,X) :- def_last(C,join,N,Q,R), def_ok(C,join,X,N), X \== C.

def_key(C,D,I,A,TK,FK) :- def_part(C,D,I,A,_,pos), def_marks(C,D,TK,FK,_).
def_key(C,D,I,A,FK,TK) :- def_part(C,D,I,A,_,neg), def_marks(C,D,TK,FK,_).
def_holds(C,D,I) :- def_key(C,D,I,A,Y,_), r_attr(A,Y,_).
def_fails(C,D,I) :- def_key(C,D,I,A,_,N), r_attr(A,N,_).
def_hpre(C,D,0) :- def_marks(C,D,_,_,_).
def_hpre(C,D,I) :- def_hpre(C,D,H), I is H+1, def_holds(C,D,I).
def_hsuf(C,D,M) :- def_marks(C,D,_,_,_), def_last(C,D,N,_,_), M is N+1.
def_hsuf(C,D,I) :- def_hsuf(C,D,H), I is H-1, def_holds(C,D,I).
def_fpre(C,D,0) :- def_marks(C,D,_,_,_).
def_fpre(C,D,I) :- def_fpre(C,D,H), I is H+1, def_fails(C,D,I).
def_fsuf(C,D,M) :- def_marks(C,D,_,_,_), def_last(C,D,N,_,_), M is N+1.
def_fsuf(C,D,I) :- def_fsuf(C,D,H), I is H-1, def_fails(C,D,I).
rule_attr(R,C,TK,V) :- def_last(C,meet,N,_,R), def_hpre(C,meet,N), def_marks(C,meet,TK,_,V).
rule_attr(R,C,FK,V) :- def_last(C,join,N,_,R), def_fpre(C,join,N), def_marks(C,join,_,FK,V).
rule_attr(R,A,N,V) :- def_marks(C,meet,_,FK,V), r_attr(C,FK,_), def_key(C,meet,I,A,_,N), \+ def_mixed(C,meet),
    H is I-1, def_hpre(C,meet,H), L is I+1, def_hsuf(C,meet,L), def_last(C,meet,_,_,R).
rule_attr(R,A,Y,V) :- def_marks(C,join,TK,_,V), r_attr(C,TK,_), def_key(C,join,I,A,Y,_), \+ def_mixed(C,join),
    H is I-1, def_fpre(C,join,H), L is I+1, def_fsuf(C,join,L), def_last(C,join,_,_,R).

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
%%% The closure's results, as facts (PrologReasoner runs sn_close/0 before it
%%% reads anything) -----------------------------------------------------------

:- dynamic holds/3, isa_star/2, attr/3.

sn_close :-
    forall(call_delays(r_holds(T,S,D), true), assertz(holds(T,S,D))),
    forall(call_delays(r_isa_star(X,C), true), assertz(isa_star(X,C))),
    forall(call_delays(r_attr(X,K,V), true), assertz(attr(X,K,V))).

%%% Relations

inherited(T,X,D) :- link_holds(T,X,D), \+ link_asserted(T,X,D).
sub_holds(T,S,D) :- holds(T2,S,D), T2 \== T, parent(T2,T), rel_type(T2).
inferred(T,S,D) :- holds(T,S,D), \+ link_asserted(T,S,D), \+ sub_holds(T,S,D).

%%% Signatures (domain/range) and classification

needs_src(R,T,C) :- src(R,S), isa_star(R,T), R \== T, domain(T,C), \+ isa_star(S,C).
needs_dst(R,T,C) :- dst(R,D), isa_star(R,T), R \== T, range(T,C), \+ isa_star(D,C).

:- table need/2.
need(S,C) :- needs_src(R,_,C), src(R,S), data(R), data(S).
need(D,C) :- needs_dst(R,_,C), dst(R,D), data(R), data(D).
classify(X,C) :- need(X,C), \+ need_more_specific(X,C).
need_more_specific(X,C) :- need(X,C2), C2 \== C, isa_star(C2,C).

%%% Violations

violation0(domain, error, R, [T,S,C]) :- needs_src(R,T,C), src(R,S).
violation0(range,  error, R, [T,D,C]) :- needs_dst(R,T,C), dst(R,D).

violation0(isa_cycle, error, X, [P]) :- parent(X,P), isa_star(P,X).
violation0(isa_individual_parent, error, X, [P]) :- parent(X,P), individual(P).
violation0(redundant_parent, warning, X, [P1,P2]) :-
    parent(X,P1), parent(X,P2), P1 \== P2, isa_star(P1,P2), \+ isa_star(P2,P1).

violation0(node_isa_relation, error, X, [R]) :- kind(X,node), const(relation,R), isa_star(X,R).
violation0(relation_isa_node, error, X, [N]) :- kind(X,relation), const(node,N), isa_star(X,N).

has_lsrc(R) :- lsrc(R,_).
has_ldst(R) :- ldst(R,_).
violation0(unset_endpoint, warning, R, [src]) :- kind(R,relation), individual(R), \+ has_lsrc(R).
violation0(unset_endpoint, warning, R, [dst]) :- kind(R,relation), individual(R), \+ has_ldst(R).

% Too many, too few: see clingoReasoner.lp.
card_counted(D) :- obj(D).
card_counted(N) :- new_obj(N), \+ card_merged(N).
card_merged(N) :- new_obj(N), same(N,X), obj(X).
card_merged(N) :- new_obj(N), same(N,X), new_obj(X), X @< N.
violation0(cardinality_max, error, S, [T,N,M]) :- card(T,out,_,M), M >= 0, distinct(S, holds(T,S,_)), individual(S),
    aggregate_all(count, (holds(T,S,D), obj(D)), N), N > M.
violation0(cardinality_max_in, error, D, [T,N,M]) :- card(T,in,_,M), M >= 0, distinct(D, holds(T,_,D)), individual(D),
    aggregate_all(count, (holds(T,S,D), obj(S)), N), N > M.
violation0(cardinality_min, warning, X, [T,N,Min]) :- card(T,out,Min,_), card_of(T,out,X),
    aggregate_all(count, (holds(T,X,D), card_counted(D)), N), N < Min.
violation0(cardinality_min_in, warning, X, [T,N,Min]) :- card(T,in,Min,_), card_of(T,in,X),
    aggregate_all(count, (holds(T,S,X), card_counted(S)), N), N < Min.
violation0(bad_cardinality, warning, T, [K,M]) :- card_error(T,K,M).

violation(C,S,X,A) :- violation0(C,S,X,A), data(X).
violation(variable_kind, warning, X, [individual, "a type"]) :- var_kind(X,individual), type(X).
violation(variable_kind, warning, X, [type, "an individual"]) :- var_kind(X,type), individual(X).

isa_data(X,T) :- isa_star(X,T), data(X).
