#!/usr/bin/python
#
# Author : hdj <helmut@oblig.at>
# Date   : 2014.06
# Project: maaps
# Description:
#   TODO: add some description!
#
import os
import copy
import ply.lex as lex
import ply.yacc as yacc
from templating import Templating
from re import IGNORECASE


reserved = {
    'if'    : 'IF',
    'then'  : 'THEN',
    'else'  : 'ELSE',
    'while' : 'WHILE',
    'python': 'PYTHON',
}


# list of tokens (always required)
tokens = [
    'IMPORT',
    'CHAIN',
    'ENTRYPOINT',
    'MODULE',
    'CALL',
    'LOOP',
    'ONEXCEPTION',

    'LBRACE',
    'RBRACE',

    'IDENTIFER',
    'COMMENT',
    'EQUAL',
    'STRING',
    'NUMBER',
    'CODE',
] + list(reserved.values())

states = (
     ('code', 'exclusive'),
)

t_EQUAL         = r'='
t_LBRACE        = r'\{'
t_RBRACE        = r'\}'
t_ignore        = ' \t'

def t_COMMENT(t):
    r'\#.*'
    pass

# =================================================================
# == START OF Code|Context Section
# =================================================================
def t_CODE(t):
    r'(CODE|CONTEXT)\s+=\s+\{'
    t.lexer.code_start = t.lexer.lexpos        # Record the starting position
    t.lexer.level = 1                          # Initial brace level
    t.lexer.begin('code')                     # Enter 'ccode' state

def t_code_LBRACE(t):
    r'\{'
    t.lexer.level += 1

def t_code_RBRACE(t):
    r'\}'
    t.lexer.level -= 1

    # If closing brace, return the code fragment
    if t.lexer.level == 0:
        t.value = t.lexer.lexdata[t.lexer.code_start:t.lexer.lexpos-1]
        t.type = "CODE"
        t.lexer.lineno += t.value.count('\n')
        t.lexer.begin('INITIAL')
        return t

# Any sequence of non-whitespace characters (not braces, strings)
def t_code_nonspace(t):
    r'[^\s\{\}\'\"]+'

# Ignored characters (whitespace)
t_code_ignore = " \t\n"

# For bad characters, we just skip over it
def t_code_error(t):
    t.lexer.skip(1)

# =================================================================
# == END OF Code|Context Section
# =================================================================
#
# this must stay under CODE section for propper parsing/identifying.
def t_NUMBER(t):
    r'\d+'
    t.value = int(t.value)
    return t
def t_STRING(t):
    r'[\'"]([^\\\n]|(\\.))*?[\'"]'
    #r'\"([^\\\n]|(\\.))*?\"'
    #t.value = t.value.lstrip('"').rstrip('"')
    return t

def t_MODULE(t):
    r'MODULE\s'
    t.value = t.value.upper().strip()
    return t

def t_CALL(t):
    r'CALL\s'
    t.value = t.value.upper().strip()
    return t

def t_LOOP(t):
    r'LOOP\s'
    t.value = t.value.upper().strip()
    return t

def t_IMPORT(t):
     r'IMPORT\s'
     t.value = t.value.upper().strip()
     return t

def t_CHAIN(t):
    r'CHAIN\s'
    t.value = t.value.upper().strip()
    return t

def t_ENTRYPOINT(t):
    r'ENTRYPOINT\s'
    t.value = t.value.upper().strip()
    return t

def t_ONEXCEPTION(t):
    r'ONEXCEPTION\s'
    t.value = t.value.upper().strip()
    return t

def t_IDENTIFER(t):
    r'[a-zA-Z_][a-zA-Z_0-9\.]*'
    t.type = reserved.get(t.value, 'IDENTIFER') # return from reserved or IDENTIFER
    return t
#
# ================================================================
#

# Define a rule so we can track line numbers
# TODO: make it work!
def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)

# Error handling rule
def t_error(t):
    print "Illegal character '%s'" % t.value[0]
    t.lexer.skip(1)

# =============================================================================
# Time for grammar ============================================================
# =============================================================================
g_chains          = []
g_steps           = [] # <== volatile
g_context         = [] # <== volatile
g_files_to_parse  = []
g_actual_filename = None


def p_application(p):
    '''application : imports chains
                   | chains
                   | imports '''


def p_imports_list(p):
    '''imports : import
               | import imports'''

def p_import(p):
    '''import : IMPORT STRING
              | IMPORT IDENTIFER
    '''
    if len(p) > 1:
        fn = p[2].replace('.', '/')
        g_files_to_parse.append(fn)


def p_chains(p):
    '''chains : chain
              | chain chains'''
    g_chains.append(p[1])

# def p_chains_chain(p):
#     '''chains : '''

def p_chain(p):
    '''chain : CHAIN STRING LBRACE steps RBRACE
             | CHAIN IDENTIFER LBRACE steps RBRACE'''
    global g_steps
    p[0] = dict( name=p[2], steps=g_steps, filename=g_actual_filename)
    g_steps = []
    #print "got a chain '%s'" % (p[2],)


def p_steps_step(p):
    '''steps : step steps'''
    g_steps.append(p[1])
    #print "I hear steps ... step: %s" % (p[1],)

def p_steps(p):
    '''steps : '''
    #print "I hear (empty) steps ..."

def p_step(p):
    '''step : entrypoint
            | module
            | call
            | onexception'''
    p[0] = p[1]
    #print "got a step %s" % (p[0],)


def p_entrypoint(p):
    '''entrypoint : ENTRYPOINT IDENTIFER STRING LBRACE context RBRACE
                  | ENTRYPOINT IDENTIFER IDENTIFER LBRACE context RBRACE
                  | ENTRYPOINT LOOP IDENTIFER LBRACE context RBRACE
                  | ENTRYPOINT LOOP STRING LBRACE context RBRACE
     '''
    global g_context
    p[0] = dict( type=p[1], subtype=p[2], name=p[3], content=g_context, filename=g_actual_filename)
    g_context = []
    #print "got a entrypoint %s" % (p[0],)


def p_module(p):
    ''' module : MODULE PYTHON STRING LBRACE context RBRACE
               | MODULE PYTHON IDENTIFER LBRACE context RBRACE
    '''
    global g_context
    p[0] = dict( type=p[1], subtype=p[2], name=p[3], content=g_context, filename=g_actual_filename )
    g_context = []
    #print "got a module %s" % (p[0],)


def p_call(p):
    '''call : CALL IDENTIFER STRING LBRACE context RBRACE
            | CALL IDENTIFER IDENTIFER LBRACE context RBRACE
            | CALL STRING STRING LBRACE context RBRACE
    '''
    global g_context
    p[0] = dict( type=p[1], subtype=p[2], name=p[3], content=g_context, filename=g_actual_filename)
    g_context = []


def p_onexception(p):
    '''onexception : ONEXCEPTION IDENTIFER LBRACE context RBRACE
                   | ONEXCEPTION STRING LBRACE context RBRACE
    '''
    global g_context
    p[0] = dict( type=p[1], subtype='exceptionHandler', name=p[2], content=g_context, filename=g_actual_filename )
    g_context = []


def p_context(p):
    '''context : expressions'''


def p_expression_list(p):
    '''expressions : expression expressions'''
    g_context.append(p[1])

def p_expressions(p):
    '''expressions : '''

def p_expression(p):
    '''expression : IDENTIFER EQUAL value
                  | CODE
                  | CALL EQUAL value'''
    if len(p) > 2 and p[2] == '=':
        if p[1] == 'CALL':
            p[0] = dict( type='call', subtype='gosub', value=p[3])
        else:
            p[0] = dict( type='expression', subtype='assignement', value="%s %s %s" % (p[1].upper(), p[2], p[3],) )
    else:
        p[0] = dict( type='expression', subtype='code', value="%s" % (p[1],) )
    p[0]['filename'] = g_actual_filename
    #print "got context %s" % (p[0],)


def p_value(p):
    '''value : IDENTIFER
             | STRING
             | NUMBER '''
    #print "got value ", p[1]
    p[0] = p[1]

# Error rule for syntax errors
def p_error(p):
    print 'Syntax error in file "%s" at line %s, msg: %s!' % (
        g_actual_filename,
        p.lineno,
        p,
    )

# =============================================================================
# End of tokenizer and yacc ===================================================
# =============================================================================

def _apply_template(code):
    if not os.path.exists('properties.py'):
        return code
    with open('properties.py', 'r') as fp:
        properties_code = fp.read()
        ctx = dict()
        exec(properties_code, ctx)
        template_data = ctx.get('template_data', None)
        if not template_data:
            print "No 'template_data' to apply."
            return code
        return Templating(code).substitute(template_data)


def _reset_globals():
    global g_chains
    global g_steps
    global g_context
    global g_files_to_parse
    global g_actual_filename
    g_chains          = []
    g_steps           = [] # <== volatile
    g_context         = [] # <== volatile
    g_files_to_parse  = []
    g_actual_filename = None


def parse(filename):
    global g_actual_filename
    g_files_to_parse.append(filename)

    lexer  = lex.lex(debug=0, reflags=IGNORECASE)
    parser = yacc.yacc()

    parsed_files = []
    while len(g_files_to_parse) > 0:
        g_actual_filename = g_files_to_parse.pop()
        if g_actual_filename in parsed_files:
            continue
        parsed_files.append(g_actual_filename)
        with open(g_actual_filename + '.maaps', 'r') as fp:
            data = fp.read()
        data = _apply_template(data)
        parser.parse(data, lexer=lexer, debug=0)

    ret = copy.deepcopy(g_chains)
    _reset_globals()
    return ret

