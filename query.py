
try:
    import cPickle as pickle
except ImportError:
    import pickle

import os.path
from lepl import *
from string import ascii_letters
from mpd import MPDClient

# MPD database functions.

def load_database(updating_callback):

    def do_load(path, timestamp):
        updating_callback()
        db = client.listallinfo()
        pickle.dump((timestamp, db), open(path, "wb"))
        return db, True
    
    db_time = client.stats()['db_update']
    path = os.path.expanduser("~/.pympddb")
    
    if not os.path.exists(path):
        db = do_load(path, db_time)

    try:
        pickled_time, db = pickle.load(open(path, "rb"))
    except (EOFError, PickleError):
        return do_load(path, db_time)

    if pickled_time != db_time:
        return do_load(path, db_time)
    
    return db, False

# Helper functions

def _coerce(E):
    if isinstance(E, (list, tuple)):
        return '; '.join(E)
    return E

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
    query  = Delayed()
    string = (String() | Word())  > 'string'
    tag    = Drop("<") + Any(ascii_letters)[:] + Drop(">")
    tag   |= Drop("%") + Any(ascii_letters)[:] + Drop("%")
    or_    = Drop(Or('||', '|', Regexp('[oO][rR]')))
    and_   = Drop(Or('&&', '&', Regexp('[aA][nN][dD]')))
    
    tagCO = tag  [:,or_ ] > _or
    tagCA = tagCO[:,and_] > _tagColl
    
    comparator = Or('=i=', '==', Regexp('[lL][iI][kK][eE]')) > 'op'
    comparison = Optional(tagCA & comparator) & string > _comparison
    
    atom = (Drop('(') & query & Drop(')')) | \
           (Drop('[') & query & Drop(']')) | \
           (Drop('{') & query & Drop('}')) | \
           comparison
    
    orExp  = atom [:,or_]  > _or
    query += orExp[:,and_] > _and

# Public interface.
    
def parse_query(string):
    for (ast,), leftover in query.match(string):
        if leftover == "":
            return ast
    # Fallback for old-style mpdgrep search.
    return ('compare', 'like', ('one', 'any'), string)

def search_ast(ast, database):
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

        if coll[1] == 'any':
            coll = ('or',) + tuple(D.keys())
        
        try:
            if coll[0] == 'one':
                return _compare_single(_coerce(value))
            elif coll[0] == 'or':
                return any(_compare_single(_coerce(D[t])) for t in coll[1:])
            elif coll[0] == 'and':
                return all(_compare_single(_coerce(D[t])) for t in coll[1:])
        except KeyError:
            pass
        return False

    def _check(node, D):
        if node[0] == 'compare':
            return _compare(node, D)
        if node[0] == 'and':
            return all(_check(n, D) for n in node[1:])
        elif node[0] == 'or':
            return any(_check(n, D) for n in node[1:])
    
    return [D for D in database if _check(ast, D)]

def search(query, database):
    return search_ast(parse_query(query), database)

def get_songids(filenames, add=False):
    results = []
    for file in filenames:
        if isinstance(file, dict):
            file = file['file']
        songs = client.playlistfind('file', file)
        if songs:
            results += [info['id'] for info in songs]
        elif add:
            results.append(client.addid(file))
    return results

client = MPDClient()
client.connect("localhost", 6600)
