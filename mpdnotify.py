#!/usr/bin/env python
# mpdnotify.py
# Newer, shinier mpdnotify using Python!
# Coded on the night of Thu, Jun 25, 2009 (10:15 PM to be exact!)
# JP St. Pierre <jstpierre@mecheye.net>

# Requires:
#   
#   mpd >= 0.14
#   
#   pynotify
#   
#   mpd-python (latest development build)
#     found at http://git.thejat.be/python-mpd.git/
#   
#   pygtk (for icon finding)
#   
#   configobj (for config reading)
#     comes with bzr, you can also easy_install configobj

import sys
import os
import cgi
import pynotify
import gtk

from PIL import Image
from configobj import ConfigObj, Section
from string import Template
from mpd import MPDClient

pretty_state = dict(play="Playing", pause="Paused", stop="Stopped")

# Simple attribute access dict.
class AttrAccess(object):
    def __getattr__(self, attr):
        try:
            return self.__getitem__(attr)
        except KeyError, e:
            raise AttributeError(*e.args)

class NamedDict(dict, AttrAccess):
    pass

# string.Template subclass for parsing %artist% templates like
# those used by mpc and foobar.
class PercentTemplate(Template):
    pattern = "%(?P<named>[_a-z][_a-z0-9]*)%"

# Monkey-patch ConfigObj so we can get
# a named-dictionary setup going.
Section.__bases__ += (AttrAccess,)

config = ConfigObj(os.path.expanduser("~/.mpdnotify.conf"))

music_path  = os.path.realpath(os.path.expanduser(config.covers.music_path))
cover_names = config.covers.search_names
cover_exts  = config.covers.search_exts
cover_size  = tuple(int(n) for n in config.covers.size)

icon_theme = gtk.icon_theme_get_default()

def str_fn_index(s, fn, arg):
    if isinstance(arg, basestring):
        arg = arg,
    arg = iter(arg)
    for i, m in enumerate(arg):
        if fn(s.lower(), m.lower()):
            return True, i
    return False, None

# Hack for string.Template and the KeyError problem.
# Substitute a default instead of throwing a KeyError.
def template_substitute_default(self, args, default=''):
    while True:
        try:
            return self.substitute(args)
            break
        except KeyError, e:
            args[e.args[0]] = default

Template.substitute_default = template_substitute_default

def daemon():
    pynotify.init("mpdnotify")
    
    client = MPDClient()
    client.connect(config.daemon.host, config.daemon.port)

    if tuple(int(m) for m in client.mpd_version.split('.')) < (0, 14, 0):
        print "You need a version of mpd that is 0.14 or greater"
        sys.exit(1)

    try:
        while True:

            # Idle for a reason.
            reason, = client.idle()

            # If we don't want to display a notification,
            # don't do so.
            if "notification_%s" % reason not in config:
                continue

            not_cfg = config["notification_%s" % reason]

            title_format = PercentTemplate(not_cfg.title_format)
            body_format  = PercentTemplate(not_cfg.body_format)

            opts = NamedDict()

            opts.update(client.status())
            opts.update(client.stats())
            opts.update(client.currentsong())
            opts.update(dict(pretty_state=pretty_state[opts.state]))

            # Covers are enabled.
            if not_cfg.as_bool('covers'):
                path   = os.path.dirname(os.path.join(music_path, opts.file))
                covers = dict()
                for filename in os.listdir(path):
                    # This weights by the order in the cover_names, but also so that
                    # a shorter filename comes first, so we won't end up choosing
                    # cover.small.jpg
                    b1, i1 = str_fn_index(filename, str.startswith, cover_names)
                    b2, i2 = str_fn_index(filename, str.endswith, cover_exts)
                    if b1 and b2:
                        covers[(i1+i2)*100+len(filename)] = filename
                        cover = sorted(covers.items())[0][1]

                if len(covers) > 0:
                    cover = os.path.join(path, cover)
                    cover_small  = "%s.small%s" % os.path.splitext(cover)

                    if not os.path.exists(cover_small):
                        try:
                            img = Image.open(cover)
                            img.thumbnail(cover_size, Image.ANTIALIAS)
                            img.save(cover_small)
                        except IOError:
                            icon = None
                    icon = cover_small
                else:
                    icon = None

            # Else, use a standard icon. Can be a filename or a tango-named icon.
            elif not_cfg.icon:
                icon = not_cfg.icon
                if not os.path.exists(icon):
                    icon = icon_theme.lookup_icon(icon, 96, 0)
                    if icon:
                        icon = icon.get_filename()

            title = title_format.substitute_default(opts)
            body  = cgi.escape(body_format.substitute_default(opts))

            # And launch the notification!
            notification = pynotify.Notification(title, body, icon)
            notification.show()
    except KeyboardInterrupt:
        pass
        
if __name__ == "__main__":
    # Here we go.
    daemon()
