
# Support library for gtkfind and mpdgrep.

import os.path
import sys

from lepl import Node, Word, Regexp, String, Drop, Delayed, Eos, Separator, Or
from mpd import MPDFactory
from twisted.internet import reactor, defer

# ================================================================================
# Helper functions
# ================================================================================

def CaseInsensitiveLiteral(word):
    L = []
    for char in word:
        if char.lower() != char.upper():
            L.append('[%s%s]' % (char.lower(), char.upper()))
        else:
            L.append(char)
    return Regexp(''.join(L))

CIL = CaseInsensitiveLiteral


# Unfolding turns this:
#    Comparison(AndNode(Tag("artist"), Tag("album")), "==", "foobar")
# into this:
#    AndNode(Comparison(Tag("artist"), "==", "foobar"), Comparison(Tag("album"), "==", "foobar"))
#
# This could also be called desugaring and distributing.

def _unfold(method_name):
    def unfold(self, *a):
        if len(self) == 1:
            return getattr(self[0], method_name)(*a)
        return self.__class__(*(getattr(node, method_name)(*a) for node in self))
    return unfold

# ================================================================================
# Node classes.
# ================================================================================

class Comparison(Node):
    def unfold_outer(self):
        return self.coll[0].unfold_collection(self)

    @defer.inlineCallbacks
    def search(self, client, state=None, order=None):
        op, tag, value = self.op[0], self.tag_[0], self.value[0]
        
        if state is None:
            state = {}
            order = []
        
        meth = client.search
        if op == '==':
            meth = client.find

        # Return a set to do intersections and unions on for AND and OR.
        # "state" contains the filename => info mapping.
        S = set()
        for D in (yield meth(tag, value)):
            if 'file' not in D:
                continue
            state[D['file']] = D
            order.append(D['file'])
            S.add(D['file'])
        
        defer.returnValue((S, state, order))
    
class CombiningOp(Node):
    unfold_outer = _unfold('unfold_outer')
    unfold_collection = _unfold('unfold_collection')

    @defer.inlineCallbacks
    def search(self, client, state=None, order=None):
        if state is None:
            state = {}
            order = []
        
        defer.returnValue((self.op(*(next(node.search(client, state, order)) for node in self)), state, order))

# Fix a problem with the descriptor problem by using staticmethod.
class AndNode(CombiningOp): op = staticmethod(set.intersection)
class OrNode (CombiningOp): op = staticmethod(set.union)
    
class Tag(Node):
    def unfold_collection(self, comparison):
        return Comparison(('tag_', self[0]), ('value', comparison.value[0]), ('op', comparison.op[0]))

# ================================================================================
# Grammar
# ================================================================================

spaces = Drop(Regexp(r'\s*'))

with Separator(spaces):
    andExp = Delayed()
    value  = (String() | Word()) > 'value'

    or_    = Drop(Or('||', '|', CIL('or')))
    and_   = Drop(Or('&&', '&', CIL('and')))
    
    tag    = (Drop("<") + Word() + Drop(">") |  Drop("%") + Word() + Drop("%")) > Tag
    
    tagCO  = tag  [:,or_ ] > OrNode
    tagCA  = tagCO[:,and_] > AndNode
    tagC   = tagCA > 'coll'
    
    comparator = Or('==', CIL('like')) > 'op'
    
    comparison = (tagC & comparator & value) > Comparison
    
    atom = (Drop('(') & andExp & Drop(')')) | \
           (Drop('[') & andExp & Drop(']')) | \
           (Drop('{') & andExp & Drop('}')) | \
           comparison
    
    orExp   = atom [:,or_ ] > OrNode
    andExp += orExp[:,and_] > AndNode

    query   = andExp & Eos()

# ================================================================================
# Public interface.
# ================================================================================

def parse_query(string):
    ast = query.parse(string)

    # Fallback for old-style mpdgrep search.
    if ast is None:
        return Comparison(('tag_', 'any'), ('op', 'like'), ('value', string))
    
    folded = ast[0].unfold_outer()
    if folded is not None:
        return folded
    return ast[0]

@defer.inlineCallbacks
def search_ast(ast, client):
    fileset, state, order = yield ast.search(client)
    L = [state[f] for f in order if f in fileset]
    defer.returnValue(L)

def search(query, client):
    return search_ast(parse_query(query), client)

@defer.inlineCallbacks
def play(filename, client):
    songs = list((yield client.playlistfind('file', filename)))
    songid = None
    if songs:
        songid = songs[0]['id']
    else:
        songid = yield client.addid(filename)
    yield client.playid(songid)
    

# This is sys.argv[1:], so any arguments that have spaces in them
# were quoted by the user in shell. Put quotes around the search
# terms that have spaces that have spaces in them to reserve this.

# This function is complicated because (%title% like "Q u o t e d")
# is sent to Python as ['(%title%', 'like', 'Q u o t e d)'], which
# is then converted into '(%title% like "Q u o t e d")'
def parse_bash_quotes(args):
    L = []
    for S in args:
        if ' ' in S:
            while S[0] in '([{':
                L.append(S[0])
                S = S[1:]
            R = []
            while S[-1] in ')]}':
                R.append(S[-1])
                S = S[:-1]
            L.append('"%s"' % S)
            L += R
        else:
            L.append(S)
    return ' '.join(L)

def run(main):
    factory = MPDFactory()
    factory.connectionMade = main
    reactor.connectTCP(os.getenv("MPD_HOST", "localhost"), os.getenv("MPD_PORT", 6600), factory)
    reactor.run()

if __name__ == '__main__':
    t = parse_bash_quotes(sys.argv[1:])
    print parse_query(t)
