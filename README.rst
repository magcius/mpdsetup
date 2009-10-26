
query.py
========

query.py is a query engine for MPD using LEPL and python-mpd.


Requirements
------------

* `MPD >= 0.16`_
  
  - Older versions may work fine too
  
* `LEPL >= 3.3`_
  
  - ``easy_install lepl`` should work
  
* `python-mpd`_
  
  - You may need the development version from git. You may not.


Query Grammar
-------------

The grammar:

::
  
  String: /'[^']*'/ | /"[^"]*"/ | /[^\w]+/;
  
  Or:  '|' | '||' | /or/i;
  And: '&' | '&&' | /and/i;
  
  Tag: /%[a-zA-Z]+%/ | /<[a-zA-Z]+>/;
  TagCollectionOr:  Tag (Or Tag)*;
  TagCollectionAnd: TagCollectionOr (And TagCollectionOr)*;
  TagCollection: TagCollectionAnd;
  
  Comparator: '==' | '=i=' | /like/i;
  Comparison: TagCollectionAnd Comparator String;
  
  Atom: '(' AndExpression ')' |
        '{' AndExpression '}' |
        '[' AndExpression ']' | Comparison;
  
  OrExpression:  Atom (Or Atom)*;
  AndExpression: OrExpression (And OrExpression)*;
  
  Query: AndExpression EOS;

Notes:

  * ``{}``, ``[]`` are included as well as parens as some shells
    take any of those three as special characters.
  * Same with ``and`` and ``or``.
  * '==' is a strict match.
  * '=i=' is a case-insensitive but full match.
  * 'like' checks for a substring of the full value in the database.
    For instance, if the database contains "The Beatles" and you do
    "like Beatles", it will match. If the database contains "Beatles"
    and you do "like The Beatles", it will not match.
  * Tag collections allow you do things like:
    ``%artist% and %album% like "Gabe Dixon"``, which means
    that both the artist and the album must contain the substring
    "Gabe Dixon". %tag% or %tag% matches for either.

Query Examples
==============

* ``%artist% like Beatles and [%title% or %album% like "Let It Be"]``
* ``%file% like "Video Game OST" and&nbsp;%artist% == "Lisa Miskovsky"``
* ``%genre% like Rock or %genre% like Pop``

Front-ends
==========

There are currently two front-ends to query.py. mpdgrep, and gtkfind.
These are successors to my old tools mpdgrep and zenfind, both written
in BASH. query.py should be backwards-compatible with both of them for
the most part, except for the implementation-specific "artist - album - title"
and "artist;album;title" searches.

mpdgrep should be bash-quote compatible, so that means that it acts like a query
engine straight from bash. Something like:

``$ mpdgrep [%artist% like "Zac Mac Band"] and [%title% like "Radio"]``

works perfectly on my computer.

.. _MPD >= 0.16: http://www.musicpd.org/
.. _LEPL >= 3.3: http://www.acooke.org/lepl/
.. _python-mpd:  http://git.thejat.be/python-mpd.git
