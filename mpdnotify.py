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

# string.Template subclass for parsing %artist% templates like
# those used by mpc and foobar.
class PercentTemplate(Template):
    pattern = "%(?P<named>[_a-z][_a-z0-9]*)%"

config = ConfigObj(os.path.expanduser("~/.mpdnotify.conf"))

covers_config = config['covers']

music_path  = os.path.realpath(os.path.expanduser(covers_config['music_path']))
cover_names = covers_config['search_names']
cover_exts  = covers_config['search_exts']
cover_size  = tuple(int(n) for n in covers_config['size'])

icon_theme = gtk.icon_theme_get_default()

pynotify.init("mpdnotify")
    
client = MPDClient()
client.connect(config['daemon']['host'], config['daemon']['port'])

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
        except KeyError, e:
            args[e.args[0]] = default

Template.substitute_default = template_substitute_default

def get_opts():
    
    def parse_time(opts):
        if "time" in opts:
            elapsed, duration = (divmod(int(n), 60) for n in opts['time'].split(":"))
            return dict(elapsed="%d:%02d" % elapsed, duration="%d:%02d" % duration)
        return dict()
    
    opts = dict()
    
    opts.update(client.status())
    opts.update(parse_time(opts))
    opts.update(client.stats())
    opts.update(client.currentsong())
    opts.update(dict(pretty_state=pretty_state[opts['state']]))
    return opts

def display_notification(title, body, enable_covers=True, icon=None):
    # And format our stuff.
    title_format = PercentTemplate(title)
    body_format  = PercentTemplate(body)

    opts = get_opts()
    
    # Covers are enabled.
    if enable_covers and "file" in opts:
        path   = os.path.dirname(os.path.join(music_path, opts['file']))
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
    elif icon and not os.path.exists(icon):
        icon = icon_theme.lookup_icon(icon, 96, 0)
        if icon:
            icon = icon.get_filename()

    title = title_format.substitute_default(opts)
    body  = cgi.escape(body_format.substitute_default(opts))

    # And launch the notification!
    notification = pynotify.Notification(title, body, icon)
    notification.show()

def display_notification_config(config_name):
    # If we don't want to display a notification,
    # don't do so.
    if "notification_%s" % config_name not in config:
        return
    
    # Get our configuration
    not_cfg = config["notification_%s" % config_name]
    title  = not_cfg.get("title_format", "")
    body   = not_cfg.get("body_format",  "")
    covers = not_cfg.get("covers",    False)
    icon   = not_cfg.get("icon",         "")
    
    display_notification(title, body, covers, icon)

def daemon():
    if tuple(int(m) for m in client.mpd_version.split('.')) < (0, 14, 0):
        print "You need a version of mpd that is 0.14 or greater"
        sys.exit(1)
    try:
        while True:

            # Idle for a reason.
            # FIXED: can be more than one reason
            reasons = client.idle()
            
            for reason in reasons:
                # Show the notitication
                display_notification_config(reason)
                
    except KeyboardInterrupt:
        pass

def help_command(command=""):
    if command == "":
        print "mpdnotify - JP St. Pierre <jstpierre@mecheye.net>"
        print "email me or post comments on the wiki, or msg me on #mpd"
        print "for feature suggestions for this program"
        print ""
        print "commands:"
        print "  help    - display this message"
        print "  display - put up a notification"
    elif command == "display":
        print "  display - put up a notification"
        print "    display config_name"
        print "      display a notification where notification_$config_name"
        print "      is a format defined in ~/.mpdnotify.conf"
        print ""
        print "    display title [body] [icon]"
        print "      display a notification having those title, body, and icon"
        print '      use the name "cover" for the icon parameter if you want'
        print "      to show cover art"

def display_notification_command(arg1="", body="", icon=""):
    if ("notification_%s" % arg1) in config:
        display_notification_config(arg1)
    else:
        display_notification(arg1, body, icon == "cover", icon)

COMMANDS = {
    "help":     help_command,
    "display":  display_notification_command
}

if __name__ == "__main__":
    
    if len(sys.argv) < 2:
        # Start daemon.
        # Here we go.
        daemon()
        sys.exit(1)
        
    else:
        command = sys.argv[1].lower().lstrip("-")
        if command in COMMANDS:
            args = sys.argv[2:] if len(sys.argv) > 2 else ()
            COMMANDS[commands[0]](*args)
        else:
            print "no command by that name"
            print "use the 'help' command for available commands"
