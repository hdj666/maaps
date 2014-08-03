# !/usr/bin/python
#
# Created by: Helmut Djurkin <helmut.djurkin@s-itsolutions.at>
# Created at: 2014.Jul
#
# TODO: write short documentation
#
import string


class Templating(string.Template):
    delimiter = '${'
    pattern   = r'''
    \$\{(?:
    (?P<escaped>\{)|
    (?P<named>[_a-z]\.*[_a-z0-9.]*)\}|
    (?P<braced>[_a-z]\.*[_a-z0-9.]*)\}|
    (?P<invalid>)
    )
    '''


if __name__ == '__main__':
    data = { 'value.with.dots': 12,
             'nodots'         : 14,
             'one.dot'        : 16
    }
    templ= 'The value from with_dots: ${value.with.dots}, nodots: ${nodots} and one dot: ${one.dot}'
    t    = Templating(templ)
    print t.safe_substitute(data)
    print 'MATCHES:', t.pattern.findall(t.template)