"""
This implements the Tab Separated SPARQL Result Format

It is implemented with pyparsing, reusing the elements from the SPARQL Parser
"""

import codecs

from pyparsing import (
    FollowedBy,
    LineEnd,
    Literal,
    Optional,
    ParseException,
    ParserElement,
    Suppress,
    ZeroOrMore,
)

from rdflib import Literal as RDFLiteral
from rdflib.plugins.sparql.parser import (
    BLANK_NODE_LABEL,
    IRIREF,
    LANGTAG,
    STRING_LITERAL1,
    STRING_LITERAL2,
    BooleanLiteral,
    NumericLiteral,
    Var,
)
from rdflib.plugins.sparql.parserutils import Comp, CompValue, Param
from rdflib.query import Result, ResultParser

ParserElement.setDefaultWhitespaceChars(" \n")


String = STRING_LITERAL1 | STRING_LITERAL2

RDFLITERAL = Comp(
    "literal",
    Param("string", String)
    + Optional(
        Param("lang", LANGTAG.leaveWhitespace())
        | Literal("^^").leaveWhitespace() + Param("datatype", IRIREF).leaveWhitespace()
    ),
)

NONE_VALUE = object()

EMPTY = FollowedBy(LineEnd()) | FollowedBy("\t")
EMPTY.setParseAction(lambda x: NONE_VALUE)

TERM = RDFLITERAL | IRIREF | BLANK_NODE_LABEL | NumericLiteral | BooleanLiteral

ROW = (EMPTY | TERM) + ZeroOrMore(Suppress("\t") + (EMPTY | TERM))
ROW.parseWithTabs()

HEADER = Var + ZeroOrMore(Suppress("\t") + Var)
HEADER.parseWithTabs()


class TSVResultParser(ResultParser):
    def parse(self, source, content_type=None):

        if isinstance(source.read(0), bytes):
            # if reading from source returns bytes do utf-8 decoding
            source = codecs.getreader("utf-8")(source)

        r = Result("SELECT")

        header = source.readline()

        r.vars = list(HEADER.parseString(header.strip(), parseAll=True))
        r.bindings = []
        while True:
            line = source.readline()
            if not line:
                break
            line = line.strip("\n")
            if line == "":
                continue

            row = ROW.parseString(line, parseAll=True)
            r.bindings.append(dict(zip(r.vars, (self.convertTerm(x) for x in row))))

        return r

    def convertTerm(self, t):
        if t is NONE_VALUE:
            return None
        if isinstance(t, CompValue):
            if t.name == "literal":
                return RDFLiteral(t.string, lang=t.lang, datatype=t.datatype)
            else:
                raise Exception("I dont know how to handle this: %s" % (t,))
        else:
            return t
