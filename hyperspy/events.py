import inspect
import collections
from contextlib import contextmanager
from functools import wraps
import re


class Events(object):

    """
    Events container.

    All available events are attributes of this class.

    """
    def __init__(self):
        self._events = {}

    @contextmanager
    def suppress(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all events in the container. When the 'with' lock completes, the old
        suppression values will be restored.

        Example usage
        -------------
        >>> with obj.events.suppress():
        ...     # Any events triggered by assignments are prevented:
        ...     obj.val_a = a
        ...     obj.val_b = b
        >>> # Trigger one event instead:
        >>> obj.events.values_changed.trigger()

        See also
        --------
        Event.suppress
        Event.suppress_callback
        """

        old = {}

        try:
            for e in self._events.itervalues():
                old[e] = e._suppress
                e._suppress = True
            yield
        finally:
            for e, oldval in old.iteritems():
                e._suppress = oldval

    def _update_doc(self):
        """
        Updates the doc to reflect the events that are contained
        """
        new_doc = self.__class__.__doc__
        new_doc += '\n\tEvents:\n\t-------\n'
        for name, e in self._events.iteritems():
            edoc = inspect.getdoc(e) or ''
            doclines = edoc.splitlines()
            e_short = doclines[0] if len(doclines) > 0 else edoc
            new_doc += '\t%s :\n\t\t%s\n' % (name, e_short)
        new_doc = new_doc.replace('\t', '    ')
        self.__doc__ = new_doc

    def __setattr__(self, name, value):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        If it's an `Event`, store it in self._events, otherwise set attribute
        in normal way.
        """
        if isinstance(value, Event):
            self._events[name] = value
            self._update_doc()
        else:
            super(Events, self).__setattr__(name, value)

    def __getattr__(self, name):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        Returns Event attribute `name` (__getattr__ is only called if attribute
        could not be found in the normal way).
        """
        return self._events[name]

    def __delattr__(self, name):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        Deletes attribute from self._events if present, otherwise delete
        attribute in normal way.
        """
        if name in self._events:
            del self._events[name]
            self._update_doc()
        else:
            super(Events, self).__delattr__(name)

    def __dir__(self):
        """
        Magic to enable having `Event`s as attributes, and keeping them
        separate from other attributes.

        Makes sure tab-completion works in IPython etc.
        """
        d = dir(type(self))
        d.extend(self.__dict__.iterkeys())
        d.extend(self._events.iterkeys())
        return sorted(set(d))

    def __iter__(self):
        """
        Allows iteraction of all events in the container
        """
        return self._events.itervalues()

    def __repr__(self):
        text = "<hyperspy.events.Events: " + repr(self._events) + ">"
        return text.encode('utf8')


class Event(object):

    def __init__(self, doc='', arguments=None):
        """
        Create an Event object.

        Arguments:
        ----------
            doc : str
                Optional docstring for the new Event.
            arguments : iterable
                Pass to define the arguments of the trigger() function. Each
                element must either be an argument name, or a tuple containing
                the argument name and the argument's default value.

        Example usage:
        --------------
            >>> Event()
            <hyperspy.events.Event: {}
            >>> Event(doc="This event has a docstring!").__doc__
            'This event has a docstring!'
            >>> e1 = Event()
            >>> e2 = Event(arguments=('arg1', ('arg2', None)))
            >>> e1.trigger(12, 43, 'str', 4.3)  # Can trigger with whatever
            >>> e2.trigger(11, 22, 3.4)
            TypeError: trigger() takes at most 3 arguments (4 given)
        """
        self.__doc__ = doc
        self._arguments = tuple(arguments) if arguments else None
        self._connected = {}
        self._suppress = False

        if arguments:
            self._trigger_maker(arguments)

    @property
    def arguments(self):
        return self._arguments

    # Regex for confirming valid python identifier
    _re_arg_name = re.compile("[a-zA-Z_][a-zA-Z0-9_]*")

    def _trigger_maker(self, arguments):
        """
        Dynamically creates a function with a signature equal to `arguments`.

        Ensures that trigger can only be called with the correct arguments
        """
        orig_f = self.trigger
        # Validate code for exec!
        defaults = []
        for arg in arguments:
            if isinstance(arg, (tuple, list)):
                defaults.append(arg[1])
                arg = arg[0]
            elif len(defaults) > 0:
                raise SyntaxError(
                    "non-default argument follows default argument")
            m = self._re_arg_name.match(arg)
            if m is None or m.end() != len(arg):
                raise ValueError("Argument name invalid: %s" % arg)
        arguments = [a[0] if isinstance(a, (tuple, list))
                     else a for a in arguments]
        # Create the dynamic code:
        arglist = ', '.join(arguments)
        arg_pass = ', '.join([a + '=' + a for a in arguments])
        wrap_code = u"""
        @wraps(f)
        def trigger(self, %s):
            return f(%s)
        """ % (arglist, arg_pass)
        wrap_code = wrap_code.replace("        ", "")      # Remove indentation
        # Execute dynamic code:
        gl = globals()
        loc = locals()
        gl.update({'f': orig_f})    # Make sure it keeps the original!
        exec wrap_code in gl, loc
        new_f = loc['trigger']
        # Replace the trigger function with the new one
        if defaults:
            new_f.func_defaults = tuple(defaults)
        new_f = new_f.__get__(self, self.__class__)     # Bind method to self
        self.trigger = new_f

    @contextmanager
    def suppress(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all events in the container. When the 'with' lock completes, the old
        suppression values will be restored.

        Example usage
        -------------
        >>> with obj.events.myevent.suppress():
        ...     # These would normally both trigger myevent:
        ...     obj.val_a = a
        ...     obj.val_b = b
        >>> # Trigger manually once:
        >>> obj.events.myevent.trigger()

        See also
        --------
        suppress_callback
        Events.suppress
        """
        old = self._suppress
        self._suppress = True
        try:
            yield
        finally:
            self._suppress = old

    @contextmanager
    def suppress_callback(self, function):
        """
        Use this function with a 'with' statement to temporarily suppress
        a single callback from being called. All other connected callbacks
        will trigger. When the 'with' lock completes, the old suppression value
        will be restored.

        Example usage
        -------------

        >>> with obj.events.myevent.suppress_callback(f):
        ...     # Events will trigger as normal, but `f` will not be called
        ...     obj.val_a = a
        ...     obj.val_b = b
        >>> # Here, `f` will be called as before:
        >>> obj.events.myevent.trigger()

        See also
        --------
        suppress
        Events.suppress
        """
        found = []
        for nargs, c in self._connected.iteritems():
            for f in c:
                if f == function:
                    found.append(nargs)
                    break
        if found:
            self.disconnect(function)
            try:
                yield
            finally:
                for nargs in found:
                    self.connect(function, nargs)
        else:
            yield   # Do nothing

    def connected(self, nargs=None):
        """
        Connected functions. The default behavior is to include all
        functions, but by using the 'nargs' argument, it can be filtered by
        function signature.
        """
        if nargs is None:
            ret = set()
            ret.update(*self._connected.values())
            return ret
        else:
            if nargs in self._connected:
                return self._connected[nargs]
            else:
                return set()

    def connect(self, function, nargs='all'):
        """
        Connects a function to the event.
        Arguments:
        ----------
        function : callable
            The function to call when the event triggers.
        nargs : int, 'all' (default), or 'auto'
            The number of arguments to supply to the function. If 'all', it
            will be called with all arguments passed to trigger(). If 'auto'
            inspect.getargspec() will be used to determine the number of
            arguments the function accepts (arguments with default values will
            be included in the count). If the function accepts *args or
            **kwargs, all arguments will be passed.

        See also
        --------
        disconnect
        """
        if not callable(function):
            raise TypeError("Only callables can be registered")

        if nargs == 'auto':
            spec = inspect.getargspec(function)
            if spec.varargs or spec.keywords:
                nargs = 'all'
            elif spec.args is None:
                nargs = 0
            else:
                nargs = len(spec.args)
        elif nargs is None:
            nargs = 0
        if nargs not in self._connected:
            self._connected[nargs] = set()
        self._connected[nargs].add(function)

    def disconnect(self, function):
        """
        Disconnects a function from the event. The passed function will be
        disconnected irregardless of which 'nargs' argument was passed to
        connect().

        If you only need to temporarily prevent a function from being called,
        single callback suppression is supported by the `suppress_callback`
        context manager.

        See also
        --------
        connect
        suppress_callback
        """
        for c in self._connected.itervalues():
            if function in c:
                c.remove(function)

    def _trigger_nargs(self, f, args, kwargs, nargs):
        """
        Basic trigger resolution.
        """
        if len(args) < nargs:
            # To few args!
            # We try to fill with ordered kwargs if present.
            # If order kwargs not present, or not enough, fill with matching
            # kwargs in the order that function defines them
            args = list(args)
            kwargs = kwargs.copy()
            if self.arguments:
                i = 0
                while len(args) < nargs and i < len(self.arguments):
                    if self.arguments[i] in kwargs:
                        args.append(kwargs.pop(self.arguments[i]))
                    i += 1
            if len(args) < nargs:
                spec = inspect.getargspec(f)
                candidates = list(spec.args)[len(args):]
                if inspect.ismethod(f):
                    candidates = candidates.pop()     # Remove `self`
                matches = [kwargs[c] for c in candidates if c in kwargs]
                args.extend(matches[:nargs-len(args)])
        return f(*args[0:nargs])

    def trigger(self, *args, **kwargs):
        """
        Triggers the event. If the event is suppressed, this does nothing.
        Otherwise it calls all the connected functions with the arguments as
        specified when connected.

        See also
        --------
        suppress
        suppress_callback
        Events.suppress
        """
        if not self._suppress:
            # Loop on copy to deal with callbacks which change connections
            for nargs, c in self._connected.copy().iteritems():
                if nargs is 'all':
                    for f in c:
                        f(*args, **kwargs)
                else:
                    if len(args) + len(kwargs) < nargs:
                        raise ValueError(
                            ("Tried to call %s which require %d args " +
                             "with only %d.") % (str(c), nargs, len(args) +
                                                 len(kwargs)))
                    for f in c.copy():
                        self._trigger_nargs(f, args, kwargs, nargs)

    def __deepcopy__(self, memo):
        dc = type(self)()
        memo[id(self)] = dc
        return dc

    def __repr__(self):
        text = "<hyperspy.events.Event: " + repr(self._connected) + ">"
        return text.encode('utf8')


class EventSupressor(object):

    """
    Object to enforce a variety of suppression types simultaneously

    Targets to be suppressed can be added by the function `add()`, or given
    in the constructor. Valid targets are:
     - `Event`: The entire Event will be suppressed
     - `Events`: All events in th container will be suppressed
     - (Event, callback): The callback will be suppressed in Event
     - (Events, callback): The callback will be suppressed in each event in
         Events where it is connected.
     - Any iterable collection of the above target types

    Example usage
    -------------
    >>> es = EventSupressor((event1, callback1), (event1, callback2))
    >>> es.add(event2, callback2)
    >>> es.add(event3)
    >>> es.add(events_container1)
    >>> es.add(events_container2, callback1)
    >>> es.add(event4, (events_container3, callback2))
    >>>
    >>> with es.supress():
    ...     do_something()
    """

    def __init__(self, *to_suppress):
        self._cms = []
        if len(to_suppress) > 0:
            self.add(*to_suppress)

    def _add_single(self, target):
        # Identify and initializes the CM, but doesn't enter it
        if self._is_tuple_target(target):
            if isinstance(target[0], Event):
                cm = target[0].suppress_callback(target[1])
                self._cms.append(cm)
            else:
                # Don't check for function presence in event now:
                # suppress_callback does this when entering
                for e in target[0]:
                    self._cms.append(e.suppress_callback(target[1]))
        else:
            cm = target.suppress()
            self._cms.append(cm)

    def _is_tuple_target(self, candidate):
        v = (isinstance(candidate, collections.Iterable) and
             len(candidate) == 2 and
             isinstance(candidate[0], (Event, Events)) and
             callable(candidate[1]))
        return v

    def _is_target(self, candidate):
        v = (isinstance(candidate, (Event, Events)) or
             self._is_tuple_target(candidate))
        return v

    def add(self, *to_suppress):
        """
        Add one or more targets to be suppressed

        Valid targets are:
         - `Event`: The entire Event will be suppressed
         - `Events`: All events in the container will be suppressed
         - (Event, callback): The callback will be suppressed in Event
         - (Events, callback): The callback will be suppressed in each event
           in Events where it is connected.
         - Any iterable collection of the above target types
        """
        # Remove useless layers of iterables:
        while (isinstance(to_suppress, collections.Iterable) and
                len(to_suppress) == 1):
            to_suppress = to_suppress[0]
        # If single target passed, add directly:
        if self._is_target(to_suppress):
            self._add_single(to_suppress)
        elif isinstance(to_suppress, collections.Iterable):
            if len(to_suppress) == 0:
                raise ValueError("No viable suppression targets added!")
            for t in to_suppress:
                if self._is_target(t):
                    self._add_single(t)
        else:
            raise ValueError("No viable suppression targets added!")

    @contextmanager
    def suppress(self):
        """
        Use this function with a 'with' statement to temporarily suppress
        all events added. When the 'with' lock completes, the old suppression
        values will be restored.

        See also
        --------
        Events.suppress
        Event.suppress
        Event.suppress_callback
        """
        # We don't suppress any exceptions, so we can use simple CM management:
        cms = []
        try:
            for cm in self._cms:
                cm.__enter__()
                cms.append(cm)                  # Only add entered CMs to list
            yield
        finally:
            # Completed succefully or exception occured, unwind all
            for cm in reversed(cms):
                # We don't use exception info, so simply pass blanks
                cm.__exit__(None, None, None)
