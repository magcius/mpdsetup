
# Support library for gtkfind and mpdgrep.

import os.path
import sys

from axiom.attributes import text, reference()
from axiom.errors import CannotOpenStore
from axiom.item import Item
from axiom.store import Store

from lepl import *
from string import ascii_letters
from mpd import MPDClient

from twisted.internet import reactor

# MPD database functions.

class MusicItem(Item):
    
    filename = text()
    
    def make_tag(self, name, value):
        return MusicTag(store=self.store, owner=self, name=tag, value=value)
    
    def make_tags(self, D):
        L = []
        for name, value in D.iteritems():
            query = self.store.query(name)
            if query.count() > 1:
                query.deleteFromStore()
            elif query.count() == 1:
                tag = list(query)[0]
                tag.value = value
                L.append(tag)
                continue
            
            L.append(self.make_tag(name, value))
            

class MusicTag(Item):
    owner = reference()
    name  = text()
    value = text()

class TimestampInfo(Item):
    timestamp = text()

def make_store(path):
    return Store(path)

def do_load(path, timestamp, store=None):
    if store == None:
        store = make_store()
    pipe.send(True)
    db = client.listallinfo()
    update_store(store, db, timestamp)
    pipe.send(store)

def update_store(store, mpddb, timestamp):
    for D in mpddb:
        if "file" not in D:
            continue
        
        item = MusicItem(store=store, filename=D.pop('file'))
        item.make_tags(D)

def load_database():
    
    timequery = store.query(TimestampInfo)
    db_time = None
    if timequery.count() > 1:
        timequery.deleteFromStore()
    elif timequery.count() == 1:
        db_time = list(timequery)[0]
    
    mpd_time = client.stats()['db_update']
    path = os.path.expanduser("~/.pympddb.2")
    
    if not os.path.exists(path):
        return do_load(path, mpd_time)
    try:
        store = make_store()
    except (EOFError, CannotOpenStore):
        return do_load(path, mpd_time)
    
    if db_time != mpd_time:
        return 

# Helper functions

def CaseInsensitiveLiteral(word):
    L = []
    for char in word:
        if char.lower() != char.upper():
            L.append('[%s%s]' % (char.lower(), char.upper()))
        else:
            L.append(char)
    return Regexp(''.join(L))

CIL = CaseInsensitiveLiteral

def _coerce(E):
    if isinstance(E, (list, tuple)):
        return '; '.join(E)
    return E

## 
## TODO: make Node subclasses.
## 

def _and(t):
    if len(t) >= 2:
        return ('and',) + tuple(t)
    elif t:
        return t[0]
    return ()

def _or(t):
    if len(t) >= 2:
        return ('or',) + tuple(t)
    elif t:
        return t[0]
    return ()

def _tagColl(t):
    t = _and(t)
    if isinstance(t, tuple):
        return 'tag', t
    return ('tag', ('one', t))

def _comparison(tuples):
    if tuples[0][0] == 'tag':
        tagColl, op, value = zip(*tuples)[1]
        return 'compare', op, tagColl, value
    elif tuples[0][0] == 'string':
        return 'compare', 'like', ('one', 'any'), tuples[0][1]

# Grammar

spaces = Drop(Regexp(r'\s*'))

with Separator(spaces):
    andExp  = Delayed()
    string = (String() | Word()) > 'string'
    tag    = Drop("<") + Any(ascii_letters)[:] + Drop(">")
    tag   |= Drop("%") + Any(ascii_letters)[:] + Drop("%")
    or_    = Drop(Or('||', '|', CIL('or')))
    and_   = Drop(Or('&&', '&', CIL('and')))
    
    tagCO = tag  [:,or_ ] > _or
    tagCA = tagCO[:,and_] > _tagColl
    
    comparator = Or('=i=', '==', CIL('like')) > 'op'
    comparison = Optional(tagCA & comparator) & string > _comparison
    
    atom = (Drop('(') & andExp & Drop(')')) | \
           (Drop('[') & andExp & Drop(']')) | \
           (Drop('{') & andExp & Drop('}')) | \
           comparison
    
    orExp   = atom [:,or_]  > _or
    andExp += orExp[:,and_] > _and

    query   = andExp & Eos()

# Public interface.

def parse_query(string):
    for (ast,), leftover in query.match(string):
        if leftover == "":
            return ast
    # Fallback for old-style mpdgrep search.
    return ('compare', 'like', ('one', 'any'), string)

def search_ast(ast, database, addids=True):
    def _compare(node, D):
        def _compare_single(V):
            if op == '==':
                if value == V:
                    return True
            elif op == '=i=':
                if value.lower() == V.lower():
                    return True
            else: # like
                if value.lower() in V.lower():
                    return True
            return False
        
        assert node[0] == 'compare'
        
        op, coll, value = node[1:]

        if coll == ('one', 'any'):
            coll = ('or',) + tuple(D.keys())
        
        try:
            if coll[0] == 'one':
                return _compare_single(_coerce(D[coll[1]]))
            elif coll[0] == 'or':
                return any(_compare_single(_coerce(D.get(t, ''))) for t in coll[1:])
            elif coll[0] == 'and':
                return all(_compare_single(_coerce(D.get(t, ''))) for t in coll[1:])
        except KeyError:
            pass
        return False

    def _check(node, D):
        if 'file' not in D:
            return False
        if node[0] == 'compare':
            return _compare(node, D)
        if node[0] == 'and':
            return all(_check(n, D) for n in node[1:])
        elif node[0] == 'or':
            return any(_check(n, D) for n in node[1:])
        return False
    
    L = [D for D in database if _check(ast, D)]
    if addids:
        add_songids(L)
    return L

def search(query, database):
    return search_ast(parse_query(query), database)

def add_songids(infos):
    for info in infos:
        if 'id' not in info:
            songs = client.playlistfind('file', info['file'])
            if songs:
                info['added'] = False
                info['id'] = songs[0]['id']
            else:
                info['added'] = True
                info['id'] = client.addid(info['file'])

# This is sys.argv[1:], so any arguments that have spaces in them
# were quoted by the user in shell. Put quotes around the search
# terms that have spaces that have spaces in them to reserve this.

# This function is complicated because (%title% like "Q u o t e d")
# is sent to Python as ['(%title%', 'like', 'Q u o t e d)'], which
# is then converted into '(%title% like "Q u o t e d)"'
def parse_bash_quotes(args):
    L = []
    for S in args:
        if ' ' in S:
            while S[0] in "([{":
                L.append(S[0])
                S = S[1:]
            R = []
            while S[-1] in ")]}":
                R.append(S[-1])
                S = S[:-1]
            L.append('"%s"' % S)
            L += R
        else:
            L.append(S)
    return ' '.join(L)

client = MPDClient()
client.connect(os.getenv("MPD_HOST") or "localhost", os.getenv("MPD_PORT") or 6600)

if __name__ == "__main__":
    t = parse_bash_quotes(sys.argv[1:])
    print parse_query(t)
