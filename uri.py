"""
Simple implementation of URI-Templates
(http://bitworking.org/projects/URI-Templates/).

Some bits are inspired by or based on:

    * Joe Gregorio's example implementation
      (http://code.google.com/p/uri-templates/)

    * Addressable (http://addressable.rubyforge.org/)
    
Simple usage::

    >>> import uri
    
    >>> args = {'foo': 'it worked'}
    >>> uri.expand_template("http://example.com/{foo}", args)
    'http://example.com/it%20worked'

    >>> args = {'a':'foo', 'b':'bar', 'a_b':'baz'}
    >>> uri.expand_template("http://example.org/{a}{b}/{a_b}", args)
    'http://example.org/foobar/baz'
    
You can also use keyword arguments for a more pythonic style::
    
    >>> uri.expand_template("http://example.org/?q={a}", a="foo")
    'http://example.org/?q=foo'
    
"""

import re
import urllib
import itertools

__all__ = ["expand_template", "TemplateSyntaxError"]

class TemplateSyntaxError(Exception):
    pass

_template_pattern = re.compile(r"{([^}]+)}")
_varname_pattern = re.compile(r"^[A-Za-z0-9]\w*$")

def expand_template(template, values={}, **kwargs):
    """
    Expand a URI template::
    
        >>> expand_template("http://{host}/{-listjoin|/|path}", 
        ...                 host="example.com", path=["a", "b"])
        'http://example.com/a/b'
    """
    allargs = itertools.chain(values.iteritems(), kwargs.iteritems())
    return Template(template).expand(**dict(allargs))

class Template(object):
    """
    Deal with a URI template as a class::
    
        >>> t = Template("http://example.com/{p}?{-join|&|a,b,c}")
        >>> t.expand(p="foo", a="1")
        'http://example.com/foo?a=1'
        >>> t.expand(p="bar", b="2", c="3")
        'http://example.com/bar?c=3&b=2'
        
    """
    
    def __init__(self, template):
        self.template = template
        
    def expand(self, **values):
        """Expand a URI template."""
        values = percent_encode(values)
        return _template_pattern.sub(lambda m: self._handle_match(m, values), self.template)

    def _handle_match(self, match, values):
        """re.sub callback used by expand()"""
        op, arg, variables = parse_expansion(match.group(1))
        if op:
            try:
                return getattr(self, "operator_" + op)(variables, arg, values)
            except AttributeError:
                raise TemplateSyntaxError("Unexpected operator: %r" % op)
        else:
            assert len(variables) == 1
            key, default = variables.items()[0]
            return values.get(key, default)
                
    #
    # Operators; see Section 3.3.
    #

    def operator_opt(self, variables, arg, values):
        for k in variables.keys():
            v = values.get(k, None)
            if v is None or (hasattr(v, "__iter__") and len(v) == 0):
                continue
            else:
                return arg
        return ""

    def operator_neg(self, variables, arg, values):
        if self.operator_opt(variables, arg, values):
            return ""
        else:
            return arg

    def operator_listjoin(self, variables, arg, values):
        k = variables.keys()[0]
        return arg.join(values.get(k, []))

    def operator_join(self, variables, arg, values):
        return arg.join([
            "%s=%s" % (k, values.get(k, default))
            for k, default in variables.items()
            if values.get(k, default) is not None
        ])

    def operator_prefix(self, variables, arg, values):
        k, default = variables.items()[0]
        v = values.get(k, default)
        if v is not None and len(v) > 0:
            return arg + v
        else:
            return ""

    def operator_append(self, variables, arg, values):
        k, default = variables.items()[0]
        v = values.get(k, default)
        if v is not None and len(v) > 0:
            return v + arg
        else:
            return ""
    

#
# Parse an expansion
# Adapted directly from the spec (Appendix A); extra validation has been added
# to make it pass all the tests.
#

def parse_expansion(expansion):
    """
    Parse an expansion -- the part inside {curlybraces} -- into its component
    parts. Returns a tuple of (operator, argument, variabledict). 

    For example::

        >>> parse_expansion("-join|&|a,b,c=1")
        ('join', '&', {'a': None, 'c': '1', 'b': None})
    
        >>> parse_expansion("c=1")
        (None, None, {'c': '1'})
    
    """
    if "|" in expansion:
        (op, arg, vars_) = expansion.split("|")
        op = op[1:]
    else:
        (op, arg, vars_) = (None, None, expansion)

    vars_ = vars_.split(",")

    variables = {}
    for var in vars_:
        if "=" in var:
            (varname, vardefault) = var.split("=")
            if not vardefault:
                raise TemplateSyntaxError("Invalid variable: %r" % var)
        else:
            (varname, vardefault) = (var, None)
    
        if not _varname_pattern.match(varname):
            raise TemplateSyntaxError("Invalid variable: %r" % varname)
        variables[varname] = vardefault
    
    return (op, arg, variables)

#
# Encode an entire dictionary of values
#
def percent_encode(values):
    """
    Percent-encode a dictionary of values, handling nested lists correctly::
    
        >>> percent_encode({'company': 'AT&T'})
        {'company': 'AT%26T'}
        >>> percent_encode({'companies': ['Yahoo!', 'AT&T']})
        {'companies': ['Yahoo%21', 'AT%26T']}
        
    """
    rv = {}
    for k, v in values.items():
        if hasattr(v, "__iter__"):
            rv[k] = [urllib.quote(s) for s in v]
        else:
            rv[k] = urllib.quote(v)
    return rv

#
# A bunch more tests that don't rightly fit in docstrings elsewhere
# Taken from Joe Gregorio's template_parser.py.
#
_test_pre = """
    >>> expand_template('{foo}', {})
    ''
    >>> expand_template('{foo}', {'foo': 'barney'})
    'barney'
    >>> expand_template('{foo=wilma}', {})
    'wilma'
    >>> expand_template('{foo=wilma}', {'foo': 'barney'})
    'barney'
    >>> expand_template('{-prefix|&|foo}', {})
    ''
    >>> expand_template('{-prefix|&|foo=wilma}', {})
    '&wilma'
    >>> expand_template('{-prefix||foo=wilma}', {})
    'wilma'
    >>> expand_template('{-prefix|&|foo=wilma}', {'foo': 'barney'})
    '&barney'
    >>> expand_template('{-append|/|foo}', {})
    ''
    >>> expand_template('{-append|#|foo=wilma}', {})
    'wilma#'
    >>> expand_template('{-append|&?|foo=wilma}', {'foo': 'barney'})
    'barney&?'
    >>> expand_template('{-join|/|foo}', {})
    ''
    >>> expand_template('{-join|/|foo,bar}', {})
    ''
    >>> expand_template('{-join|&|q,num}', {})
    ''
    >>> expand_template('{-join|#|foo=wilma}', {})
    'foo=wilma'
    >>> expand_template('{-join|#|foo=wilma,bar}', {})
    'foo=wilma'
    >>> expand_template('{-join|&?|foo=wilma}', {'foo': 'barney'})
    'foo=barney'
    >>> expand_template('{-listjoin|/|foo}', {})
    ''
    >>> expand_template('{-listjoin|/|foo}', {'foo': ['a', 'b']})
    'a/b'
    >>> expand_template('{-listjoin||foo}', {'foo': ['a', 'b']})
    'ab'
    >>> expand_template('{-listjoin|/|foo}', {'foo': ['a']})
    'a'
    >>> expand_template('{-listjoin|/|foo}', {'foo': []})
    ''
    >>> expand_template('{-opt|&|foo}', {})
    ''
    >>> expand_template('{-opt|&|foo}', {'foo': 'fred'})
    '&'
    >>> expand_template('{-opt|&|foo}', {'foo': []})
    ''
    >>> expand_template('{-opt|&|foo}', {'foo': ['a']})
    '&'
    >>> expand_template('{-opt|&|foo,bar}', {'foo': ['a']})
    '&'
    >>> expand_template('{-opt|&|foo,bar}', {'bar': 'a'})
    '&'
    >>> expand_template('{-opt|&|foo,bar}', {})
    ''
    >>> expand_template('{-neg|&|foo}', {})
    '&'
    >>> expand_template('{-neg|&|foo}', {'foo': 'fred'})
    ''
    >>> expand_template('{-neg|&|foo}', {'foo': []})
    '&'
    >>> expand_template('{-neg|&|foo}', {'foo': ['a']})
    ''
    >>> expand_template('{-neg|&|foo,bar}', {'bar': 'a'})
    ''
    >>> expand_template('{-neg|&|foo,bar}', {'bar': []})
    '&'
    >>> expand_template('{foo}', {'foo': ' '})
    '%20'
    >>> expand_template('{-listjoin|&|foo}', {'foo': ['&', '&', '|', '_']})
    '%26&%26&%7C&_'
    
    # Extra hoops to deal with unpredictable dict ordering
    >>> expand_template('{-join|#|foo=wilma,bar=barney}', {}) in ('bar=barney#foo=wilma', 'foo=wilma#bar=barney')
    True

"""

_syntax_errors = """
    >>> expand_template("{fred=}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: 'fred='
    
    >>> expand_template("{f:}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: 'f:'
    
    >>> expand_template("{f<}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: 'f<'
    
    >>> expand_template("{<:}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: '<:'
    
    >>> expand_template("{<:fred,barney}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: '<:fred'
    
    >>> expand_template("{>:}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: '>:'
    
    >>> expand_template("{>:fred,barney}")
    Traceback (most recent call last):
        ...
    TemplateSyntaxError: Invalid variable: '>:fred'
    
"""

__test__ = {"test_pre": _test_pre, "syntax_errors": _syntax_errors}

if __name__ == '__main__':
    import doctest
    doctest.testmod()