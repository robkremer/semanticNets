%################################################################################
% (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
%################################################################################
%
% Rule base for sn.model.clingoReasoner.ClingoReasoner (clingo / answer set programming).
%
% Every GraphObject -- node, relation, relation type, isa link -- is reified as
% a term o(N), so relation types participating in the isa hierarchy (and
% relations between relations) are ordinary first-order facts.
%
% ---- Input facts, see sn.model.reasoner.Reasoner.facts() -----------------------------
%   obj(O).                   every GraphObject
%   individual(O).            GraphObject.isIndividual()
%   kind(O,K).                K in top, node, relation, isa
%   collection(O).            O is a Collection (also kind node)
%   name(O,S).                GraphObject.name
%   const(K,O).               well-known objects: top, relation, isa, node, ...
%   parent(X,P).              GraphObject.getParents() (includes the implicit
%                             defaults to node/relation)
%   lsrc(R,C). ldst(R,C).     locally set relation endpoints (Relation.localSrc/.localDst)
%   domain(T,C). range(T,C).  the signature of relation type T (Relation.domain/.range)
%   src(R,S). dst(R,D).       effective endpoints (Relation.src/.dst, inherited)
%   link(R,S,D).              individual, non-isa relation R with both endpoints
%   prop(T,P).                relation type T is tagged with P (reflexive,
%                             irreflexive, symmetric, asymmetric, transitive)
%   member(C,M).              M is a member of box C (a collection that doesn't quote what it contains)
%   pattern(X).               X is a pattern element (see GraphObject.isPatternElement())
%   var_kind(X,K).            X is a variable over K: individual, type or any (see
%                             GraphObject.variableKind() and sn.model.names)
%   attr(O,K,V).              effective (local or inherited, per the model's
%                             Restriction rules) non-"vis/" scalar attributes
%   lattr(O,K).               O has K locally
%   card(T,Dir,Min,Max).      relation type T's cardinality: each source (Dir out)
%                             or destination (in) has Min..Max others by T (Max -1:
%                             any number). See sn.model.reasoner.CARDINALITY.
%   card_error(T,K,M).        T's cardinality attribute K can't be read: message M
%
% ---- Output ------------------------------------------------------------------
%   isa_data(X,T).            X isa T (reflexive-transitive), X not a pattern element
%   holds(T,S,D).             S is related to D under relation type T
%   inferred(T,S,D).          holds, but neither asserted nor implied by a
%                             more specific relation type
%   inherited(T,X,D).         X -T-> D inherited down the isa hierarchy
%   classify(X,C).            X should be classified under C (most specific)
%   violation(Code,Sev,Subject,Args).
%   fired(Rule,T,S,D).        a user rule concluded S -T-> D
%   rule_attr(Rule,X,K,V).    a user rule concluded that X has attribute K = V
%   rule_isa(Rule,X,T).       a user rule concluded that X isa T
%   rule_new(N).              a user rule concluded that object N exists: N is
%                             new(Rule,Var,Match), one per match of the rule
%                             (or new(T,Name,(("of"|"to",X),)): an object T's
%                             cardinality says X must have -- see below)
%   same(X,Y).                X and Y must be the same object (by a cardinality
%                             of at most one), one of them a new object
%
% ---- User rules --------------------------------------------------------------
%   The rules (see sn.model.reasoner.ruleOf()) -- the model's, and the base
%   rules' (see sn.model.reasoner.BASE_RULES) -- are added to this program as
%   rules concluding fired/4 and rule_attr/4, whose bodies use the predicates
%   here (holds/3, isa_star/2, attr/3, prop/2, ...); the constraints (see
%   sn.model.reasoner.constraintOf()) as rules concluding violation0/4. See
%   ClingoReasoner._rulesProgram().

type(O) :- obj(O), not individual(O).
rel_type(T) :- kind(T,relation), type(T).

% Pattern elements -- the variables (?x) and relations inside a context (a rule,
% definition or query), and relations involving them -- describe patterns, not
% the world: they're exported marked pattern(X), their relations aren't links,
% and nothing is inferred, classified or reported about them. See
% GraphObject.isPatternElement().
data(X) :- obj(X), not pattern(X).

% The objects the user's rules create (see rule_new/1) are data too -- but not
% "base" data: the variables of rules that create objects range over base
% data only, so that such a rule can't go on creating objects forever. (Other
% rules' variables, and queries', range over all data.)
base(X) :- obj(X), not pattern(X).
data(N) :- rule_new(N).
any_individual(X) :- individual(X).
any_individual(N) :- rule_new(N).

%%% Type hierarchy ------------------------------------------------------------

isa_star(X,X) :- obj(X).
isa_star(X,Z) :- parent(X,Y), isa_star(Y,Z).
% ... including what the user's rules conclude (see rule_isa/3). isa_base is
% the asserted hierarchy alone: what the refinement of inherited relations
% (below) uses under negation, so that the program stays stratified.
isa_star(N,N) :- rule_new(N).
isa_star(X,Z) :- rule_isa(_,X,Y), isa_star(Y,Z).
isa_base(X,X) :- obj(X).
isa_base(X,Z) :- parent(X,Y), isa_base(Y,Z).

%%% Relations -----------------------------------------------------------------

% A relation individual instantiates its parent relation types.
asserted(T,S,D) :- link(R,S,D), parent(R,T), rel_type(T).
% ... and, with the relation hierarchy, every type above them too (asserted
% data alone -- for the test of whether a rule's new objects are already
% there: see ClingoReasoner._satisfied() -- so that the program stays stratified).
asserted_under(T,S,D) :- asserted(T2,S,D), isa_base(T2,T), rel_type(T).

% Relations inherit down the isa hierarchy from their source, one isa step at a
% time: dog -has-> tail gives rex -has-> tail. A local relation to a more
% specific destination (rex -has-> tail#12, or rex -hasPart-> stubbyTail where
% hasPart isa has and stubbyTail isa tail) refines -- and so blocks -- the
% inherited one, for the object and everything below it.
link_holds(T,S,D) :- asserted(T,S,D).
link_holds(T,X,D) :- link_holds(T,S,D), parent(X,S), data(X), not refined(T,X,D).
link_holds(T,X,D) :- link_holds(T,S,D), rule_isa(_,X,S), data(X), not refined(T,X,D).
refined(T,X,D) :- asserted(T,_,D), asserted(T2,X,D2), isa_base(T2,T), isa_base(D2,D),
                  (T2,D2) != (T,D).
inherited(T,X,D) :- link_holds(T,X,D), not asserted(T,X,D).

% Every relation type subsumes its sub-relation types (relation hierarchy),
% including their inferred pairs.
holds(T,S,D) :- link_holds(T,S,D).
% What the rules conclude (the user's, and the base rules) holds too -- and so feeds everything else:
% the relation hierarchy, the algebraic properties, other rules, ...
holds(T,S,D) :- fired(_,T,S,D).
holds(T2,S,D) :- holds(T,S,D), parent(T,T2), rel_type(T2).

% The relational properties (symmetric, transitive, reflexive -- tags on
% relation types, read as prop/2) aren't here: what they mean is in the base
% rules, a model of ordinary rules every reasoner applies (see
% sn.model.reasoner.BASE_RULES and tools/makeBaseRules.py), whose conclusions
% are holds/3 as any rule's are.

% Report only genuinely new pairs, not those that follow by mere subsumption.
sub_holds(T,S,D) :- holds(T2,S,D), parent(T2,T), rel_type(T2).
inferred(T,S,D) :- holds(T,S,D), not asserted(T,S,D), not sub_holds(T,S,D).

%%% Signatures (domain/range) and classification ------------------------------

% A relation type's domain and range are its signature: every relation or
% sub-type below it must have a src that isa the domain, and a dst that isa
% the range.
needs_src(R,T,C) :- src(R,S), isa_star(R,T), R != T, domain(T,C), not isa_star(S,C).
needs_dst(R,T,C) :- dst(R,D), isa_star(R,T), R != T, range(T,C), not isa_star(D,C).

need(S,C) :- needs_src(R,_,C), src(R,S), data(R), data(S).
need(D,C) :- needs_dst(R,_,C), dst(R,D), data(R), data(D).
% Suggest only the most specific type (satisfying it satisfies the others).
classify(X,C) :- need(X,C), not need_more_specific(X,C).
need_more_specific(X,C) :- need(X,C), need(X,C2), C2 != C, isa_star(C2,C).

%%% Violations ----------------------------------------------------------------

violation0(domain, error, R, (T,S,C)) :- needs_src(R,T,C), src(R,S).
violation0(range,  error, R, (T,D,C)) :- needs_dst(R,T,C), dst(R,D).

violation0(isa_cycle, error, X, (P,)) :- parent(X,P), isa_star(P,X).
violation0(isa_individual_parent, error, X, (P,)) :- parent(X,P), individual(P).
violation0(redundant_parent, warning, X, (P1,P2)) :-
    parent(X,P1), parent(X,P2), P1 != P2, isa_star(P1,P2), not isa_star(P2,P1).

violation0(node_isa_relation, error, X, (R,)) :-
    kind(X,node), const(relation,R), isa_star(X,R).
violation0(relation_isa_node, error, X, (N,)) :-
    kind(X,relation), const(node,N), isa_star(X,N).

% (The relational properties' violations -- irreflexive, asymmetric and
% property_conflict -- are constraints in the base rules: see above.)

% An individual relation without a local endpoint silently takes its type's
% endpoint (ultimately top, from relation) -- almost certainly unintended.
has_lsrc(R) :- lsrc(R,_).
has_ldst(R) :- ldst(R,_).
violation0(unset_endpoint, warning, R, (src,)) :-
    kind(R,relation), individual(R), not has_lsrc(R).
violation0(unset_endpoint, warning, R, (dst,)) :-
    kind(R,relation), individual(R), not has_ldst(R).

%%% Cardinality ---------------------------------------------------------------
% A relation type's cardinality (see card/4): how many objects each source is
% related to by it -- or by its subtypes: a father is a parent -- (out), or
% each destination from (in).

new_obj(N) :- rule_new(N).

% At most one: objects that must be the same. Two of the model's objects are
% different (they have different names: see violation cardinality_max), but an
% object the rules invented -- "a mother" -- might be anyone: if it must be
% the same as another, it is. Whatever's true of one is then true of the other.
same(D1,D2) :- card(T,out,_,1), holds(T,S,D1), holds(T,S,D2), D1 != D2, new_obj(D1).
same(S1,S2) :- card(T,in,_,1), holds(T,S1,D), holds(T,S2,D), S1 != S2, new_obj(S1).
same(X,Y) :- same(Y,X).
same(X,Z) :- same(X,Y), same(Y,Z), X != Z.
holds(T,S,Y) :- holds(T,S,X), same(X,Y).
holds(T,Y,D) :- holds(T,X,D), same(X,Y).
attr(Y,K,V) :- attr(X,K,V), same(X,Y).
isa_star(Y,T) :- isa_star(X,T), same(X,Y), T != X.

% Exactly one (at least one, at most one): an object of the domain's (out; the
% range's, in) that the model doesn't relate by it to anything gets a new
% object -- of the range (out; the domain, in) -- which merging (above) makes
% the same as any other it must be. Only for the model's own individuals (see
% base/1), so new objects don't go on making more.
card_top(C) :- const(top,C).
card_of(T,out,X) :- card(T,out,Min,_), Min > 0, domain(T,C), not card_top(C), isa_star(X,C), base(X), individual(X), kind(X,node).
card_of(T,in,X) :- card(T,in,Min,_), Min > 0, range(T,C), not card_top(C), isa_star(X,C), base(X), individual(X), kind(X,node).
card_has(T,out,X) :- asserted_under(T,X,_).
card_has(T,in,X) :- asserted_under(T,_,X).
card_new(T,out,X) :- card_of(T,out,X), card(T,out,_,1), not card_has(T,out,X).
card_new(T,in,X) :- card_of(T,in,X), card(T,in,_,1), not card_has(T,in,X).
rule_new(new(T,N,(("of",X),))) :- card_new(T,out,X), name(T,N).
fired(T,T,X,new(T,N,(("of",X),))) :- card_new(T,out,X), name(T,N).
rule_isa(T,new(T,N,(("of",X),)),C) :- card_new(T,out,X), name(T,N), range(T,C), not card_top(C).
rule_new(new(T,N,(("to",X),))) :- card_new(T,in,X), name(T,N).
fired(T,T,new(T,N,(("to",X),)),X) :- card_new(T,in,X), name(T,N).
rule_isa(T,new(T,N,(("to",X),)),C) :- card_new(T,in,X), name(T,N), domain(T,C), not card_top(C).

% Too many, too few. Of what an object is related to, a merged new object is
% counted once (as the object it's the same as, or as the first of those that
% are the same: by term order), and too many is only known of the model's own
% objects (an invented one might be one of them).
card_counted(D) :- obj(D).
card_counted(N) :- new_obj(N), not card_merged(N).
card_merged(N) :- same(N,X), obj(X), new_obj(N).
card_merged(N) :- same(N,X), new_obj(N), new_obj(X), X < N.
violation0(cardinality_max, error, S, (T,N,M)) :- card(T,out,_,M), M >= 0, holds(T,S,_), individual(S),
    N = #count{ D : holds(T,S,D), obj(D) }, N > M.
violation0(cardinality_max_in, error, D, (T,N,M)) :- card(T,in,_,M), M >= 0, holds(T,_,D), individual(D),
    N = #count{ S : holds(T,S,D), obj(S) }, N > M.
violation0(cardinality_min, warning, X, (T,N,Min)) :- card(T,out,Min,_), card_of(T,out,X),
    N = #count{ D : holds(T,X,D), card_counted(D) }, N < Min.
violation0(cardinality_min_in, warning, X, (T,N,Min)) :- card(T,in,Min,_), card_of(T,in,X),
    N = #count{ S : holds(T,S,X), card_counted(S) }, N < Min.
violation0(bad_cardinality, warning, T, (K,M)) :- card_error(T,K,M).

%%% User rules' attribute conclusions ------------------------------------------

attr(X,K,V) :- rule_attr(_,X,K,V).

%%% Nodes defined by their links (Gaines's structural connectives) --------------
% See sn.model.reasoner.DEFINING. "For every defining link" without negation
% (which would make a loop through holds/3): the links are numbered 1..N
% (def_part/6), and def_ok(C,D,X,I) says X stands as required to C's links
% 1..I -- so to all of them at N. A positive link's other end stands as
% required to it (the order is reflexive).

def_ok(C,meet,X,1) :- def_part(C,meet,1,A,P,_), holds(P,X,A).
def_ok(C,meet,A,1) :- def_part(C,meet,1,A,_,pos).
def_ok(C,meet,X,I+1) :- def_ok(C,meet,X,I), def_part(C,meet,I+1,A,P,_), holds(P,X,A).
def_ok(C,meet,A,I+1) :- def_ok(C,meet,A,I), def_part(C,meet,I+1,A,_,pos).
def_ok(C,join,X,1) :- def_part(C,join,1,A,P,_), holds(P,A,X).
def_ok(C,join,A,1) :- def_part(C,join,1,A,_,pos).
def_ok(C,join,X,I+1) :- def_ok(C,join,X,I), def_part(C,join,I+1,A,P,_), holds(P,A,X).
def_ok(C,join,A,I+1) :- def_ok(C,join,A,I), def_part(C,join,I+1,A,_,pos).
fired(R,Q,X,C) :- def_ok(C,meet,X,N), def_last(C,meet,N,Q,R), X != C.
fired(R,Q,C,X) :- def_ok(C,join,X,N), def_last(C,join,N,Q,R), X != C.

% Truth attributes: def_key(C,D,I,A,Y,N) -- link I holds if A has Y, fails if
% it has N; and the links 1..I (def_*pre) or I..N (def_*suf) all hold (h) or
% all fail (f).
def_key(C,D,I,A,TK,FK) :- def_part(C,D,I,A,_,pos), def_marks(C,D,TK,FK,_).
def_key(C,D,I,A,FK,TK) :- def_part(C,D,I,A,_,neg), def_marks(C,D,TK,FK,_).
def_holds(C,D,I) :- def_key(C,D,I,A,Y,_), attr(A,Y,_).
def_fails(C,D,I) :- def_key(C,D,I,A,_,N), attr(A,N,_).
def_hpre(C,D,0) :- def_marks(C,D,_,_,_).
def_hpre(C,D,I) :- def_hpre(C,D,I-1), def_holds(C,D,I).
def_hsuf(C,D,N+1) :- def_marks(C,D,_,_,_), def_last(C,D,N,_,_).
def_hsuf(C,D,I) :- def_hsuf(C,D,I+1), def_holds(C,D,I).
def_fpre(C,D,0) :- def_marks(C,D,_,_,_).
def_fpre(C,D,I) :- def_fpre(C,D,I-1), def_fails(C,D,I).
def_fsuf(C,D,N+1) :- def_marks(C,D,_,_,_), def_last(C,D,N,_,_).
def_fsuf(C,D,I) :- def_fsuf(C,D,I+1), def_fails(C,D,I).
% A meet is true when all its links hold, a join false when they all fail; a
% false meet whose links but one hold makes that one fail, and a true join
% whose links but one fail makes that one hold -- unless one of them was
% given both marks (def_mixed/2: as KNet does, an inconsistent part blocks it).
rule_attr(R,C,TK,V) :- def_hpre(C,meet,N), def_last(C,meet,N,_,R), def_marks(C,meet,TK,_,V).
rule_attr(R,C,FK,V) :- def_fpre(C,join,N), def_last(C,join,N,_,R), def_marks(C,join,_,FK,V).
rule_attr(R,A,N,V) :- def_marks(C,meet,_,FK,V), attr(C,FK,_), def_key(C,meet,I,A,_,N), not def_mixed(C,meet),
                      def_hpre(C,meet,I-1), def_hsuf(C,meet,I+1), def_last(C,meet,_,_,R).
rule_attr(R,A,Y,V) :- def_marks(C,join,TK,_,V), attr(C,TK,_), def_key(C,join,I,A,Y,_), not def_mixed(C,join),
                      def_fpre(C,join,I-1), def_fsuf(C,join,I+1), def_last(C,join,_,_,R).

% Report only violations about the data (not about pattern elements).
violation(C,S,X,A) :- violation0(C,S,X,A), data(X).

% ... and, about pattern elements, a variable whose name says what it ranges
% over (see sn.model.names) though the object is the other: ?x as a type, or
% ^T as an individual. The name wins (see ClingoReasoner._patternBody()) --
% except that a variable used as a relation's type in a pattern ranges over
% relation types whatever its name (so an old ?r still works there).
violation(variable_kind, warning, X, (individual, "a type")) :- var_kind(X,individual), type(X).
violation(variable_kind, warning, X, (type, "an individual")) :- var_kind(X,type), individual(X).

% The isa closure, as reported: data only (a variable isn't an instance of anything).
isa_data(X,T) :- isa_star(X,T), data(X).
#show isa_data/2.
#show holds/3.
#show inferred/3.
#show inherited/3.
#show classify/2.
#show violation/4.
#show fired/4.
#show rule_attr/4.
#show rule_isa/3.
#show rule_new/1.
#show same/2.

%%% Worlds: exploring the cases of defined nodes (see sn.model.reasoner.DEFINING) --
% Solved after the program above (ClingoReasoner._explore()), with its marks
% as facts: world_mark0(X,K), X has the truth attribute K. The parts below are
% grounded only then: "explored" for the worlds -- the marks every one has are
% necessary -- and "preferred" too for the defaults (the marks every preferred
% one has).

#program marks.
% (with the program above: what the worlds start from)
def_mark_key(K) :- def_world(C,D,_,_), def_marks(C,D,K,_,_).
def_mark_key(K) :- def_world(C,D,_,_), def_marks(C,D,_,K,_).
world_mark0(X,K) :- attr(X,K,_), def_mark_key(K).
% (and whether there's anything to explore: a true join none of whose links
% hold, or a false meet none of whose fail -- not both)
world_open0(C,join) :- def_world(C,join,_,_), def_marks(C,join,TK,FK,_), attr(C,TK,_), not attr(C,FK,_),
                       not world_held0(C,join).
world_open0(C,meet) :- def_world(C,meet,_,_), def_marks(C,meet,TK,FK,_), attr(C,FK,_), not attr(C,TK,_),
                       not world_failed0(C,meet).
world_held0(C,D) :- def_holds(C,D,_).
world_failed0(C,D) :- def_fails(C,D,_).
#show world_mark0/2.
#show world_open0/2.

#program explored.
% A true join none of whose links hold (a false meet none of whose fail) --
% unless it was both -- is a choice of one of its links that didn't fail
% (didn't hold): it holds (fails) in that world, with the definition's
% necessaryValue. A world in which something gets both marks that didn't have
% them both isn't one.
def_mark_key(K) :- def_world(C,D,_,_), def_marks(C,D,K,_,_).
def_mark_key(K) :- def_world(C,D,_,_), def_marks(C,D,_,K,_).
world_both0(X) :- world_mark0(X,TK), world_mark0(X,FK), def_marks(_,_,TK,FK,_).
world_sat0(C,join) :- def_key(C,join,_,A,Y,_), world_mark0(A,Y).
world_sat0(C,meet) :- def_key(C,meet,_,A,_,N), world_mark0(A,N).
world_need(C,join) :- def_world(C,join,_,_), def_marks(C,join,TK,_,_), attr(C,TK,_),
                      not world_both0(C), not world_sat0(C,join).
world_need(C,meet) :- def_world(C,meet,_,_), def_marks(C,meet,_,FK,_), attr(C,FK,_),
                      not world_both0(C), not world_sat0(C,meet).
world_case(C,join,I) :- def_world(C,join,_,_), def_key(C,join,I,A,_,N), not world_mark0(A,N).
world_case(C,meet,I) :- def_world(C,meet,_,_), def_key(C,meet,I,A,Y,_), not world_mark0(A,Y).
1 { world_pick(C,D,I) : world_case(C,D,I) } 1 :- world_need(C,D).
rule_attr(R,A,Y,V) :- world_pick(C,join,I), def_key(C,join,I,A,Y,_), def_last(C,join,_,_,R), def_world(C,join,V,_).
rule_attr(R,A,N,V) :- world_pick(C,meet,I), def_key(C,meet,I,A,_,N), def_last(C,meet,_,_,R), def_world(C,meet,V,_).
:- def_marks(_,_,TK,FK,_), attr(X,TK,_), attr(X,FK,_), not world_both0(X).
world_mark(X,K) :- attr(X,K,_), def_mark_key(K), not world_mark0(X,K).
#show world_mark/2.

#program preferred.
% Preferences (KNet's normal defaults): in an explored join, a link whose end
% A yields to an end B (A -P-> B, for its def_prefer P) fails while B doesn't
% fail (B hasn't the mark A gets) -- and in an explored meet, holds while B
% doesn't hold. The preferred worlds are those in which the preferred ends
% that didn't fail (hold) already fail (hold) least: each node's preferences
% (def_rank: the highest first) before the next's.
world_pref(C,D,A,B) :- def_prefer(C,D,P), def_part(C,D,_,A,_,_), holds(P,A,B), A != B.
rule_attr(R,A,N,V) :- world_need(C,join), def_key(C,join,_,A,_,N), world_pref(C,join,A,B), not attr(B,N,_),
                      def_last(C,join,_,_,R), def_world(C,join,_,V).
rule_attr(R,A,Y,V) :- world_need(C,meet), def_key(C,meet,_,A,Y,_), world_pref(C,meet,A,B), not attr(B,Y,_),
                      def_last(C,meet,_,_,R), def_world(C,meet,_,V).
:~ world_need(C,join), def_key(C,join,_,A,_,N), world_pref(C,join,A,B), attr(B,N,_), not world_mark0(B,N),
   def_rank(C,join,K). [1@K,C,join,B]
:~ world_need(C,meet), def_key(C,meet,_,A,Y,_), world_pref(C,meet,A,B), attr(B,Y,_), not world_mark0(B,Y),
   def_rank(C,meet,K). [1@K,C,meet,B]

#program probe_marks.
% (with the program above: the marks a probe starts from -- see
% ClingoReasoner.probes(): probe_key(t,TK), probe_key(f,FK) are the
% attributes that say an object's true or false)
probe_value(X,K) :- probe_key(_,K), attr(X,K,_).
#show probe_value/2.

#program probed.
% Probes (Gaines's): the ways the probe_node/1 objects can be marked that the
% rules allow, from the marks probe_mark0/2 (what the program alone
% concluded) -- each answer set one. Consistent: each node that has no mark
% gets one, true or false, and nothing gets both that hadn't both. Compatible:
% each node not asserted (probe_asserted/1) is true, false or both, at least
% what it was, and just what the rules then make it.
probe_both0(X) :- probe_mark0(X,TK), probe_mark0(X,FK), probe_key(t,TK), probe_key(f,FK).
probe_marked0(X) :- probe_mark0(X,_).
1 { probe_set(X,K) : probe_key(_,K) } 1 :- probe_node(X), not probe_marked0(X), probe_kind(consistent).
:- probe_kind(consistent), probe_key(t,TK), probe_key(f,FK), attr(X,TK,_), attr(X,FK,_), not probe_both0(X).
{ probe_set(X,K) : probe_key(_,K) } :- probe_node(X), not probe_asserted(X), probe_kind(compatible).
probe_chosen(X) :- probe_set(X,_).
:- probe_kind(compatible), probe_node(X), not probe_asserted(X), not probe_chosen(X).
:- probe_kind(compatible), probe_node(X), not probe_asserted(X), probe_key(_,K), attr(X,K,_), not probe_set(X,K).
rule_attr(probe,X,K,probe) :- probe_set(X,K).
probe_out(X,K) :- probe_node(X), probe_key(_,K), attr(X,K,_).
#show probe_out/2.
