'''
PyMOL Plugins Engine

(c) 2011-2012 Thomas Holder, PyMOL OS Fellow
License: BSD-2-Clause

'''

from __future__ import print_function

import os
import sys
import pymol
from pymol import cmd
from pymol import colorprinting
from .legacysupport import *

# variables

PYMOLPLUGINSRC = os.path.expanduser('~/.pymolpluginsrc.py')

preferences = {
    'verbose': False,
    'instantsave': True,
}

autoload = {}

plugins = {}

HAVE_QT = False

# exception types

class QtNotAvailableError(Exception):
    pass

# plugins from PYMOL_DATA

startup.__path__.append(cmd.exp_path('$PYMOL_DATA/startup'))
N_NON_USER_PATHS = len(startup.__path__)

# API functions

def is_verbose(debug=0):
    verbose = pref_get('verbose')
    if debug and verbose < 0:
        return True
    return verbose and pymol.invocation.options.show_splash

def get_startup_path(useronly=False):
    if useronly:
        # assume last item is always from installation directory
        return startup.__path__[:-N_NON_USER_PATHS]
    return startup.__path__

def set_startup_path(p, autosave=True):
    if isinstance(p, list):
        startup.__path__[:-N_NON_USER_PATHS] = p
        if autosave:
            set_pref_changed()
    else:
        print(' Error: set_startup_path failed')

def pref_set(k, v):
    preferences[k] = v
    set_pref_changed()

def pref_get(k, d=None):
    return preferences.get(k, d)

def pref_save(filename=PYMOLPLUGINSRC, quiet=1):
    import pprint
    repr = pprint.pformat

    try:
        f = open(cmd.exp_path(filename), 'w')
    except IOError:
        print(' Plugin-Error: Cannot write Plugins resource file to', filename)
        return

    print('# AUTOGENERATED FILE', file=f)
    print('try:', file=f)
    print('  import', __name__, file=f)
    print('  ' + __name__ + '.autoload =', repr(autoload), file=f)
    print('  ' + __name__ + '.preferences =', repr(preferences), file=f)
    print('  ' + __name__ + '.set_startup_path(', repr(get_startup_path(True)), ', False)', file=f)
    print('except:', file=f)
    print('  import os', file=f)
    print('  print("Error while loading " + os.path.abspath(__script__))', file=f)
    f.close()

    if not int(quiet):
        print(' Plugin settings saved!')

def set_pref_changed():
    if pref_get('instantsave', True):
        verbose = pref_get('verbose', False)
        pref_save(quiet=not verbose)


def addmenuitemqt(label, command=None, menuName='PluginQt'):
    '''
    Adds plugin menu item to main 'Plugin' menu.
    Intended for plugins which open a PyQt window.
    '''
    if not HAVE_QT:
        raise QtNotAvailableError()

    addmenuitem(label, command, menuName)


def addmenuitem(label, command=None, menuName='Plugin'):
    '''
    Generic replacement for MegaWidgets menu item adding
    '''
    labels1 = [menuName] + label.split('|')
    labels2 = ['|'.join(labels1[0:i]) for i in range(1, len(labels1))]
    pmgapp = get_pmgapp()
    if pmgapp is not None:
        for i in range(1, len(labels2)):
            try:
                pmgapp.menuBar.addcascademenu(labels2[i-1], labels2[i], label=labels1[i])
            except ValueError:
                pass
        if labels1[-1] == '-':
            pmgapp.menuBar.addmenuitem(labels2[-1], 'separator')
        else:
            pmgapp.menuBar.addmenuitem(labels2[-1], 'command', label=labels1[-1],
                    command=command)

def plugin_load(name, quiet=1):
    '''
DESCRIPTION

    Load plugin from command line.
    '''
    if len(plugins) == 0:
        initialize(-2)
    if name not in plugins:
        print(' Error: no such plugin')
        return
    info = plugins[name]
    if info.loaded:
        if not int(quiet):
            print(' info: plugin already loaded')
        return
    info.load()

# helper functions and classes

class PluginInfo(object):
    '''
    Hold all information about a plugin.

    A instance with mod_name=None is considered a temporary instance which
    cannot be loaded (during installation, for extraction of metadata, ...)
    '''
    def __init__(self, name, filename, mod_name=None):
        self.name = name
        self.mod_name = mod_name
        self.filename = filename

        # set on loading
        self.loadtime = None
        self.commands = []

        # register
        if not self.is_temporary:
            plugins[name] = self

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.name)

    @property
    def autoload(self):
        return autoload.get(self.name, True)

    @autoload.setter
    def autoload(self, value):
        autoload[self.name] = bool(value)
        set_pref_changed()

    @property
    def module(self):
        return sys.modules.get(self.mod_name)

    @property
    def loaded(self):
        return self.loadtime is not None

    @property
    def is_temporary(self):
        return self.mod_name is None

    def get_metadata(self):
        '''
        Parse plugin file for metadata (hash-commented block at beginning of file).
        '''
        metadata = dict()
        f = open(self.filename, 'rb')
        for line in f:
            line = line.decode('utf-8', errors='replace')
            if line.strip() == '':
                continue
            if not line.startswith('#'):
                break
            if ':' in line:
                key, value = line[1:].split(':', 1)
                metadata[key.strip()] = value.strip()
        f.close()
        self.get_metadata = lambda: metadata
        return metadata

    def get_version(self):
        '''
        Get version as string. If no version available, return empty string.

        Preferred way to specify version is metadata "Version" field.
        '''
        v = self.get_metadata().get('Version', '')
        if not v and self.loaded:
            v = getattr(self.module, '__version__', '')
        return str(v)

    def get_citation_required(self):
        '''
        Return True if Citation-Required: Yes
        '''
        v = self.get_metadata().get('Citation-Required', 'No')
        return v.lower() == 'yes'

    def get_docstring(self):
        '''
        Get docstring either from loaded module, or try to parse first python
        statement from file, without executing any code.
        '''
        if self.loaded:
            return self.module.__doc__

        try:
            c = compile(b''.join(open(self.filename, 'rb')), 'x', 'exec', dont_inherit=True)
            s = c.co_consts[0]
            if cmd.is_string(s):
                return s
        except SyntaxError as e:
            if sys.version_info[0] > 2:
                return 'WARNING: Plugin not Python 3.x compatible: ' + str(e)
        except:
            pass

    def load(self, pmgapp=None, force=0):
        '''
        Load and initialize plugin.

        If pmgapp == -1, do not initialize.
        '''
        import time

        assert not self.is_temporary

        starttime = time.time()
        if pmgapp is None:
            pmgapp = get_pmgapp()

        verbose = pref_get('verbose', False)

        try:
            # overload cmd.extend to register commands
            extend_orig = cmd.extend
            def extend_overload(a, b=None):
                self.commands.append(a if b else a.__name__)
                return extend_orig(a, b)
            cmd.extend = extend_overload

            # do not use self.loaded here
            if force and self.module is not None:
                if sys.version_info[0] > 2:
                    from importlib import reload
                else:
                    from __builtin__ import reload
                reload(self.module)
            else:
                __import__(self.mod_name, level=0)

            if pmgapp != -1:
                self.legacyinit(pmgapp)

            cmd.extend = extend_orig

            self.loadtime = time.time() - starttime
            if verbose and pymol.invocation.options.show_splash:
                print(' Plugin "%s" loaded in %.2f seconds' % (self.name, self.loadtime))
        except QtNotAvailableError:
            colorprinting.warning("Plugin '%s' only available with PyQt GUI." % (self.name,))
        except:
            e = sys.exc_info()[1]
            if verbose:
                colorprinting.print_exc([__file__])
            elif 'libX11' in str(e) and sys.platform == 'darwin':
                colorprinting.error('Please install XQuartz (https://www.xquartz.org/)')
            else:
                colorprinting.error(e)
            colorprinting.warning("Unable to initialize plugin '%s' (%s)." % (self.name, self.mod_name))
            return False

        return True

    def legacyinit(self, pmgapp):
        '''
        Call the __init__ or __init_plugin__ function which takes the PMGApp
        instance as argument (usually adds menu items).

        This must be called after loading and after launching of the external
        GUI (PMGApp).

        Ignore the build-in <method-wrapper '__init__'> that takes a
        string as first argument. Only call __init__ if it's of type
        'function'.
        '''
        import types

        mod = self.module
        if mod is None:
            raise RuntimeError('not loaded')

        if hasattr(mod, '__init_plugin__'):
            mod.__init_plugin__(pmgapp)
        elif hasattr(mod, '__init__'):
            if isinstance(mod.__init__, types.FunctionType):
                mod.__init__(pmgapp)

    def uninstall(self, parent=None):
        '''
        Remove a plugin

        Removes the complete directory tree in case of a package.
        '''
        from .legacysupport import tkMessageBox

        if parent is None:
            parent = get_tk_focused()

        ok = tkMessageBox.askyesno('Confirm',
                'Do you really want to uninstall plugin "%s"' % (self.name), parent=parent)
        if not ok:
            return False

        showinfo = tkMessageBox.showinfo
        dirname, basename = os.path.split(self.filename)

        try:
            if basename == '__init__.py':
                import shutil
                shutil.rmtree(dirname)
            else:
                for suffix in ['', 'o', 'c']:
                    filename = self.filename + suffix
                    if os.path.exists(filename):
                        os.remove(filename)
        except OSError:
            showinfo('Error', 'Could not delete files for plugin "%s".' % (self.name), parent=parent)
            return False

        plugins.pop(self.name, None)
        autoload.pop(self.name, None)
        set_pref_changed()

        showinfo('Info', 'Plugin "%s" successfully removed. Please restart PyMOL.' % (self.name), parent=parent)
        return True

def findPlugins(paths):
    '''
    Find all python modules (extension .py and directories with __init__.py)
    inside a list of directories.

    Returns a dictionary with names to filenames mapping.
    '''
    import time
    start = time.time()

    verbose = pref_get('verbose', False)

    modules = dict()

    for path in paths:
        if not os.path.isdir(path):
            continue

        for filename in os.listdir(path):
            # ignore names that start with dot or underscore
            if filename[0] in ['.', '_']:
                continue

            if '.' in filename:
                name, _, ext = filename.partition('.')
                if ext == 'py':
                    if name not in modules:
                        modules[name] = os.path.join(path, filename)
                    elif verbose:
                        print(' warning: multiple plugins named', name)
            else:
                name, filename = filename, os.path.join(path, filename, '__init__.py')
                if os.path.exists(filename):
                    if name not in modules:
                        modules[name] = filename
                    elif verbose:
                        print(' warning: multiple plugins named', name)

    if verbose:
        print(' Scanning for modules took %.4f seconds' % (time.time() - start))
    return modules

def initialize(pmgapp=-1):
    '''
    Searches for plugins and registers them.

    pmgapp == -2: No Autoloading
    pmgapp == -1: Autoloading but no legacyinit
    else:         Autoloading and legacyinit
    '''

    # check for obsolete development version of pymolplugins
    if 'pymolplugins' in sys.modules:
        from .legacysupport import tkMessageBox
        tkMessageBox.showwarning('WARNING',
                '"pymolplugins" now integrated into PyMOL as "pymol.plugins"! '
                'Please remove the old pymolplugins module and delete ~/.pymolrc_plugins.py')

    if os.path.exists(PYMOLPLUGINSRC):
        from pymol import parsing
        try:
            parsing.run_file(PYMOLPLUGINSRC, {'__script__': PYMOLPLUGINSRC}, {})
        except SyntaxError as e:
            colorprinting.warning(str(e))

    autoload = (pmgapp != -2)
    for parent in [startup]:
        modules = findPlugins(parent.__path__)

        for name, filename in modules.items():
            mod_name = parent.__name__ + '.' + name
            info = PluginInfo(name, filename, mod_name)
            if autoload and info.autoload:
                info.load(pmgapp)

# pymol commands
cmd.extend('plugin_load', plugin_load)
cmd.extend('plugin_pref_save', pref_save)

# autocompletion
cmd.auto_arg[0]['plugin_load'] = [ lambda: cmd.Shortcut(plugins), 'plugin', ''  ]

# vi:expandtab:smarttab:sw=4
