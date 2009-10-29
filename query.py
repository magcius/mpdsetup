
# Support library for gtkfind and mpdgrep.

import os.path
import sys

import warnings
warnings.simplefilter('ignore', DeprecationWarning)

import axiom
from axiom.attributes import text, reference
from axiom.errors import CannotOpenStore
from axiom.item import Item
from axiom.store import Store

from lepl import *
from mpd import MPDClient

from itertools import izip

from twisted.internet.task import coiterate
from twisted.internet import reactor

# MPD database functions.

class MusicItem(Item):
    
    filename      = text()
    artist        = text()
    album         = text()
    title         = text()
    disc          = text()
    track         = text()
    last_modified = text()
    performer     = text()
    date          = text()
    albumartist   = text()
    genre         = text()
    
    def make_tags(self, D):
        #query = self.store.query(MusicTag, MusicTag.owner == self)
        #query.deleteFromStore()
        
        for name, value in D.iteritems():
            if isinstance(value, list):
                value = '; '.join(value)

            if name in TAG_NAME_MAP:
                name = TAG_NAME_MAP[name]

            try:
                setattr(self, name.decode('utf8'), value.decode('utf8'))
            except AttributeError:
                pass

TAG_NAME_MAP = {'file': 'filename', 'last-modified': 'last_modified'}
TAGS = dict((k, v) for k, v in MusicItem.__dict__.iteritems() if not k.startswith("__"))
            
class TimestampInfo(Item):
    timestamp = text()

def make_store(path):
    return Store(path)

def do_load(path, timestamp, callback, store=None):
    def done(e):
        time = TimestampInfo(store=store, timestamp=timestamp.decode('utf8'))
        return callback(store=store, done=True)
        
    def stop(*a, **b):
        reactor.stop()
    
    if store == None:
        store = make_store(path)

    callback()
    mpddb = client.listallinfo()
    callback(loaded_mpd=True)
    defer = coiterate(update_store(store, mpddb, callback))
    defer.addCallback(done)
    return None

TRANSACTION_INTERVAL = 1000

def _update_store_internal(store, it, total):
    for i in xrange(TRANSACTION_INTERVAL):
        D = it.next()
        if "file" not in D:
            continue

        filename = D.pop('file').decode('utf8')
        query = store.query(MusicItem, MusicItem.filename == filename)
        item = None
        
        if query.count() == 1:
            item = list(query)[0]
        else:
            query.deleteFromStore()
            item = MusicItem(store=store, filename=filename)
        
        item.make_tags(D)
    return filename

def update_store(store, mpddb, callback):
    total = len(mpddb)
    count = 0
    it = iter(mpddb)
    while True:
        filename = store.transact(_update_store_internal, store, it, total)
        count += TRANSACTION_INTERVAL
        callback(filename=filename, percent=(min(count, total) / float(total) * 100))
        yield True

def load_database(callback):
    mpd_time = client.stats()['db_update']
    path = os.path.expanduser("~/.pympddb.2")
    
    if not os.path.exists(path):
        return do_load(path, mpd_time, callback)
    try:
        store = make_store(path)
    except (EOFError, CannotOpenStore):
        return do_load(path, mpd_time, callback)

    timequery = store.query(TimestampInfo)
    for f in store.query(MusicItem):
        print f.filename
    
    db_time = None
    if timequery.count():
        db_time = list(timequery)[0].timestamp.encode("utf8")

    print db_time
    print mpd_time
    
    if db_time != mpd_time:
        if timequery.count():
            timequery.deleteFromStore()
        return do_load(None, mpd_time, callback)
    
    return store

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

# class CaseInsensitive(object):
#     implements(IColumn)

#     def __init__(self, column):
#         self.column = column
    
#     def getColumnName(self, store):
#         return "lower(%s)" % (self.column.getColumnName(store),)

#     def __getattr__(self, name):
#         return getattr(self.column, name)

class Comparison(Node):
    def __init__(self, kwargs):
        kwargs = dict(kwargs)
        self.coll  = kwargs.get('coll', Tag('any'))
        self.op    = kwargs.get('op', 'like')
        self.value = kwargs.get('value')

    def make_op(self, column):
        if column is None:
            return None
        if self.op == '==':
            return column == self.value
        elif self.op == '=i=':
            return column.like(self.value)
        else: # like
            return column.like('%' + self.value + '%')

    def make_query(self):
        return coll.make_query(self)
    
class OptimizingOp(Node):
    def __init__(self, *args):
        self.args = args
    
    def make_query(self, *a):
        if len(self.args) == 1:
            return self.args[0].make_query(*a)
        else:
            args = [v.make_query(*a) for v in self.args]
            args = [v for v in args if v is not None]
            return self.OP(*rgs)

class AndNode(OptimizingOp): OP = axiom.attributes.AND
class OrNode (OptimizingOp): OP = axiom.attributes.OR

class Tag(Node):
    def __init__(self, name):
        self.name = name

    def make_query(self, comparison):
        if self.name == 'any':
            return axiom.attributes.OR(*(comparison.make_op(C) for C in TAGS.itervalues()))
        return comparison.make_op(TAGS.get(TAG_NAME_MAP.get(self.name, self.name), None))

# def _tagColl(t):
#     t = _and(t)
#     if isinstance(t, tuple):
#         return 'tag', t
#     return ('tag', ('one', t))

# def _comparison(tuples):
#     if tuples[0][0] == 'tag':
#         tagColl, op, value = zip(*tuples)[1]
#         return 'compare', op, tagColl, value
#     elif tuples[0][0] == 'string':
#         return 'compare', 'like', ('one', 'any'), tuples[0][1]

# Grammar

spaces = Drop(Regexp(r'\s*'))

with Separator(spaces):
    andExp = Delayed()
    value  = (String() | Word()) > 'value'

    or_    = Drop(Or('||', '|', CIL('or')))
    and_   = Drop(Or('&&', '&', CIL('and')))
    
    tag    = Drop("<") + Word() + Drop(">")
    tag   |= Drop("%") + Word() + Drop("%")
    tag   >= Tag
    
    tagCO  = tag  [:,or_ ] > OrNode
    tagCA  = tagCO[:,and_] > AndNode
    
    comparator = Or('=i=', '==', CIL('like')) > 'op'
    
    comparison = (Optional(tagCA & comparator) & value) > Comparison
    
    atom = (Drop('(') & andExp & Drop(')')) | \
           (Drop('[') & andExp & Drop(']')) | \
           (Drop('{') & andExp & Drop('}')) | \
           comparison
    
    orExp   = atom [:,or_ ] > OrNode
    andExp += orExp[:,and_] > AndNode

    query   = andExp & Eos()

# Public interface.

def parse_query(string):
    for (ast,), leftover in query.match(string):
        if leftover == "":
            return ast
    # Fallback for old-style mpdgrep search.
    return Comparison(('value', string))

def search_ast(ast, store, addids=True):
    L = []
    #L = list(set(tag.owner for tag in store.query(MusicTag, ast.make_query())))
    if addids:
        add_songids(L)
    return L

def search(query, database):
    return search_ast(parse_query(query), database)

def add_songids(infos):
    for info in infos:
        if info.id == None:
            songs = client.playlistfind('file', info['file'])
            if songs:
                info.added = False
                info.id    = songs[0]['id']
            else:
                info.added = True
                info.added = client.addid(info['file'])

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
