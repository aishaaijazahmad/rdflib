from collections import OrderedDict
from types import MethodType

from pyparsing import ParseResults, TokenConverter, originalTextFor

from rdflib import BNode, Variable

"""

NOTE: PyParsing setResultName/__call__ provides a very similar solution to this
I didn't realise at the time of writing and I will remove a
lot of this code at some point

Utility classes for creating an abstract-syntax tree out with pyparsing actions

Lets you label and group parts of parser production rules

For example:

# [5] BaseDecl ::= 'BASE' IRIREF
BaseDecl = Comp('Base', Keyword('BASE') + Param('iri',IRIREF))

After parsing, this gives you back an CompValue object,
which is a dict/object with the parameters specified.
So you can access the parameters are attributes or as keys:

baseDecl.iri

Comp lets you set an evalFn that is bound to the eval method of
the resulting CompValue


"""


# This is an alternative

# Comp('Sum')( Param('x')(Number) + '+' + Param('y')(Number) )


def value(ctx, val, variables=False, errors=False):
    """
    utility function for evaluating something...

    Variables will be looked up in the context
    Normally, non-bound vars is an error,
    set variables=True to return unbound vars

    Normally, an error raises the error,
    set errors=True to return error

    """

    if isinstance(val, Expr):
        return val.eval(ctx)  # recurse?
    elif isinstance(val, CompValue):
        raise Exception("What do I do with this CompValue? %s" % val)

    elif isinstance(val, list):
        return [value(ctx, x, variables, errors) for x in val]

    elif isinstance(val, (BNode, Variable)):
        r = ctx.get(val)
        if isinstance(r, SPARQLError) and not errors:
            raise r
        if r is not None:
            return r

        # not bound
        if variables:
            return val
        else:
            raise NotBoundError

    elif isinstance(val, ParseResults) and len(val) == 1:
        return value(ctx, val[0], variables, errors)
    else:
        return val


class ParamValue(object):
    """
    The result of parsing a Param
    This just keeps the name/value
    All cleverness is in the CompValue
    """

    def __init__(self, name, tokenList, isList):
        self.isList = isList
        self.name = name
        if isinstance(tokenList, (list, ParseResults)) and len(tokenList) == 1:
            tokenList = tokenList[0]

        self.tokenList = tokenList

    def __str__(self):
        return "Param(%s, %s)" % (self.name, self.tokenList)


class Param(TokenConverter):
    """
    A pyparsing token for labelling a part of the parse-tree
    if isList is true repeat occurrences of ParamList have
    their values merged in a list
    """

    def __init__(self, name, expr, isList=False):
        self.isList = isList
        TokenConverter.__init__(self, expr)
        self.setName(name)
        self.addParseAction(self.postParse2)

    def postParse2(self, tokenList):
        return ParamValue(self.name, tokenList, self.isList)


class ParamList(Param):
    """
    A shortcut for a Param with isList=True
    """

    def __init__(self, name, expr):
        Param.__init__(self, name, expr, True)


class plist(list):
    """this is just a list, but we want our own type to check for"""

    pass


class CompValue(OrderedDict):

    """
    The result of parsing a Comp
    Any included Params are available as Dict keys
    or as attributes

    """

    def __init__(self, name, **values):
        OrderedDict.__init__(self)
        self.name = name
        self.update(values)

    def clone(self):
        return CompValue(self.name, **self)

    def __str__(self):
        return self.name + "_" + OrderedDict.__str__(self)

    def __repr__(self):
        return self.name + "_" + dict.__repr__(self)

    def _value(self, val, variables=False, errors=False):
        if self.ctx is not None:
            return value(self.ctx, val, variables)
        else:
            return val

    def __getitem__(self, a):
        return self._value(OrderedDict.__getitem__(self, a))

    def get(self, a, variables=False, errors=False):
        return self._value(OrderedDict.get(self, a, a), variables, errors)

    def __getattr__(self, a):
        # Hack hack: OrderedDict relies on this
        if a in ("_OrderedDict__root", "_OrderedDict__end"):
            raise AttributeError()
        try:
            return self[a]
        except KeyError:
            # raise AttributeError('no such attribute '+a)
            return None


class Expr(CompValue):
    """
    A CompValue that is evaluatable
    """

    def __init__(self, name, evalfn=None, **values):
        super(Expr, self).__init__(name, **values)

        self._evalfn = None
        if evalfn:
            self._evalfn = MethodType(evalfn, self)

    def eval(self, ctx={}):
        try:
            self.ctx = ctx
            return self._evalfn(ctx)
        except SPARQLError as e:
            return e
        finally:
            self.ctx = None


class Comp(TokenConverter):

    """
    A pyparsing token for grouping together things with a label
    Any sub-tokens that are not Params will be ignored.

    Returns CompValue / Expr objects - depending on whether evalFn is set.
    """

    def __init__(self, name, expr):
        self.expr = expr
        TokenConverter.__init__(self, expr)
        self.setName(name)
        self.evalfn = None

    def postParse(self, instring, loc, tokenList):
        if self.evalfn:
            res = Expr(self.name)
            res._evalfn = MethodType(self.evalfn, res)
        else:
            res = CompValue(self.name)
            if self.name == "ServiceGraphPattern":
                # Then this must be a service graph pattern and have
                # already matched.
                # lets assume there is one, for now, then test for two later.
                sgp = originalTextFor(self.expr)
                service_string = sgp.searchString(instring)[0][0]
                res["service_string"] = service_string

        for t in tokenList:
            if isinstance(t, ParamValue):
                if t.isList:
                    if t.name not in res:
                        res[t.name] = plist()
                    res[t.name].append(t.tokenList)
                else:
                    res[t.name] = t.tokenList
                # res.append(t.tokenList)
            # if isinstance(t,CompValue):
            #    res.update(t)
        return res

    def setEvalFn(self, evalfn):
        self.evalfn = evalfn
        return self


def prettify_parsetree(t, indent="", depth=0):
    out = []
    if isinstance(t, ParseResults):
        for e in t.asList():
            out.append(prettify_parsetree(e, indent, depth + 1))
        for k, v in sorted(t.items()):
            out.append("%s%s- %s:\n" % (indent, "  " * depth, k))
            out.append(prettify_parsetree(v, indent, depth + 1))
    elif isinstance(t, CompValue):
        out.append("%s%s> %s:\n" % (indent, "  " * depth, t.name))
        for k, v in t.items():
            out.append("%s%s- %s:\n" % (indent, "  " * (depth + 1), k))
            out.append(prettify_parsetree(v, indent, depth + 2))
    elif isinstance(t, dict):
        for k, v in t.items():
            out.append("%s%s- %s:\n" % (indent, "  " * (depth + 1), k))
            out.append(prettify_parsetree(v, indent, depth + 2))
    elif isinstance(t, list):
        for e in t:
            out.append(prettify_parsetree(e, indent, depth + 1))
    else:
        out.append("%s%s- %r\n" % (indent, "  " * depth, t))
    return "".join(out)


# hurrah for circular imports
from rdflib.plugins.sparql.sparql import NotBoundError, SPARQLError
