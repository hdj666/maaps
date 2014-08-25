# Author : hdj <helmut@oblig.at>
# Date   : 2014.06
# Project: maaps
# Description:
#   TODO: add some description!
#

import os
import threading, Queue
import logging, logging.config
import traceback
from pycode import PyCode
# -----------------------------------------------------------------------------
# import global shared definitions
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parentdir not in os.sys.path:
    os.sys.path.insert(0,parentdir)
from shared import *
# -----------------------------------------------------------------------------
# configure logger
logging.config.fileConfig("%s/../logging.conf" % os.path.dirname(__file__))


class ModPython(object):
    def __init__(self, name, filename, source_code, timeout):
        self.logger        = logging.getLogger('maaps.module.python')
        self.code_logger   = logging.getLogger('maaps.module.python.code')
        self.name          = name
        self.long_name     = "%s(%s)" % (self.name, filename,)
        self.timeout       = float(timeout)
        self.pycode        = PyCode(name, filename, source_code)

    # def _execute_code(self, global_context, local_context):
    #     self.pycode.run(global_context, local_context)

    def run(self, global_context):
        # setup contexts
        global_context[CTX_LOGGER]  = self.code_logger
        local_context               = dict()
        exception_queue             = Queue.Queue()

        t = threading.Thread(   target=self.pycode.run,
                                args=(exception_queue, global_context, local_context,),
                                name=self.long_name
        )
        t.start()

        # execute code
        if self.timeout > 0.0:
            t.join( self.timeout )
            if t.is_alive():  # timeout happened
                # TODO: t.terminate() (the threading version of terminate)
                self.logger.error("%s: Timed out!", self.long_name)
                raise RuntimeError("Timeout!!")
                return
        else:
            t.join()
            try:
                exc_type, exc_obj, exc_trace = exception_queue.get(block=False)
                self.logger.error("%s Exception: %r", self.name, exc_type)
                self.logger.error("%s Exception: %r", self.name, exc_obj)
                raise exc_type(exc_obj)
            except Queue.Empty:
                pass




