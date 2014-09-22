# Author : hdj <helmut@oblig.at>
# Date   : 2014.07
# Project: maaps
# Description:
#   TODO: add some description!
# 
import os, re, sys
import logging, logging.config
# -----------------------------------------------------------------------------
# import global shared definitions
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parentdir not in os.sys.path:
    os.sys.path.insert(0,parentdir)
from shared import *
# -----------------------------------------------------------------------------
# configure logger
logging.config.fileConfig("%s/../logging.conf" % os.path.dirname(__file__))


class PyCode(object):
    def __init__(self, name, filename, code):
        self.logger   = logging.getLogger('maaps.pycode')
        self.name     = name
        self.filename = filename
        # if the code is in a file dont touch it, but if it's inline-code then
        # we have to reformat it we need to remove leading withspaces (else the
        # interpreter would complain about unexpected indentation.
        self.logger.debug("creating code for name '%s' filename '%s' code '%r'", name, filename, code)
        if filename.startswith('inline'):
            self.code = PyCode.tidy_source_code(code)
        else:
            self.code = code

        # compile the code
        try:
            self._compiled = compile(self.code, self.name, 'exec')
        except Exception, e:
            self.logger.error("%s: compilation of %s failed.", self.name, self.filename)
            self.logger.error("%s: code is: [%s]", self.name, self.code)
            self.logger.exception("Exception is:")
            raise e

    @staticmethod
    def tidy_source_code(source_code):
        regex           = re.compile("^(\s+)[^\s]*.*$")
        
        comment_regex   = re.compile(r'^\s*#.*$')
        found_to_skip   = False
        pattern_to_skip = ""
        new_code        = []
        for line in source_code.split('\n'):
            if not found_to_skip:
                # if the whole line is acomment ignore it
                if comment_regex.match(line):
                    continue
                m = regex.match(line)
                if m:
                    pattern_to_skip   = "^%s" % (m.group(1),)
                    found_to_skip = True
            line = re.sub(pattern_to_skip, "", line)
            # skip empty lines
            if len( line.strip() ) == 0:
               continue
            new_code.append( line )
        return "\n".join(new_code,)

    def run(self, exception_queue, global_context, local_context=None):

        assert( CTX_PAYLOAD in global_context )

        import os, sys
        cwd = os.getcwd()
        if cwd not in sys.path:
            sys.path.append( os.getcwd() )
        save_logger = None
        if CTX_LOGGER not in global_context:
            save_logger = global_context.get(CTX_LOGGER, None)
            global_context[CTX_LOGGER] = self.logger

        if not local_context:
            local_context = {}

        try:
            exec(self.compiled, global_context, local_context)
            if CTX_PAYLOAD in local_context:
                self.logger.debug('payload   in local_context: %s', local_context[CTX_PAYLOAD])
                self.logger.debug('chainvars in local_context: %s', local_context.get(CTX_CHAINVARS))
                global_context[CTX_PAYLOAD] = local_context[CTX_PAYLOAD]
        except Exception:
            self.logger.error('%s: execution failed in "%r"', self.name, self.filename)
            self.logger.debug("%s:  code is: [%r]" % (self.name, self.code,))
            exception_queue.put(sys.exc_info())
        finally:
            if save_logger:
                global_context[CTX_LOGGER] = save_logger

    @property
    def compiled(self):
        return self._compiled

    @property
    def source_code(self):
        return self.code

