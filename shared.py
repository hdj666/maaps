#!/usr/bin/python
#
# Author : hdj <helmut@oblig.at>
# Date   : 2014.06
# Project: maaps
# Description:
#   TODO: add some description!
# 

import os
import logging, logging.config

# configure logger
_logger_config_1 = "%s/../logging.conf" % os.path.dirname(__file__)
_logger_config_2 = "%s/logging.conf" % os.path.dirname(__file__)
if os.path.exists(_logger_config_1):
    logging.config.fileConfig(_logger_config_1)
elif os.path.exists(_logger_config_2):
    logging.config.fileConfig(_logger_config_2)
else:
    raise RuntimeError("No logger configuration-file found!")

# patch python logger to be more colorful
logging.addLevelName( logging.DEBUG,   "\033[0;34m%-8s\033[0;0m" % logging.getLevelName(logging.DEBUG))
logging.addLevelName( logging.INFO,    "\033[1;33m%-8s\033[0;0m" % logging.getLevelName(logging.INFO))
logging.addLevelName( logging.WARNING, "\033[1;36m%-8s\033[0;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName( logging.ERROR,   "\033[0;31m%-8s\033[0;0m" % logging.getLevelName(logging.ERROR))
logging.addLevelName( logging.CRITICAL,"\033[0;35m%-8s\033[0;0m" % logging.getLevelName(logging.CRITICAL))


# "global" internal used constants
WAIT_SECS_ON_SHUTDOWN = 1 # <== used in entrypoint, waitsecs to terminate process

# Enums for step(s)
STEP_TYPE_ENTRYPOINT = 'ENTRYPOINT'
STEP_TYPE_MODULE     = 'MODULE'
STEP_TYPE_CALL       = 'CALL'
STEP_TYPE_ONEXCEPTION= 'ONEXCEPTION'

STEP_SUBTYPE_HTTPLISTENER = 'HttpListener'
STEP_SUBTYPE_LOOP         = 'LOOP'
STEP_SUBTYPE_PYTHON       = 'python'


# Enums for default context entries
CTX_PAYLOAD         = 'payload'
CTX_CHAINVARS       = 'chainvars'
CTX_LOCK            = 'lock'
CTX_LOGGER          = 'logger'
CTX_STOP_EXECUTION  = 'abort'
CTX_EXCEPTION       = 'exception'

def create_global_context():
    return {
        CTX_PAYLOAD        : None,
        CTX_CHAINVARS      : dict(),
        CTX_STOP_EXECUTION : True,  # <== checked only in exception handlers
    }

def dbg_get_context_str(ctx):
    """
    extracts the context without hidden (aka __*) fields
    :param ctx: a context dictionary
    :return: content from context without hidden (buildins, ...)
    """
    ret = []
    for key, value in ctx.iteritems():
        if not key.startswith("__"):
            ret.append( "%-10s = %s" % (key, value,) )
    return "\n".join(ret)
