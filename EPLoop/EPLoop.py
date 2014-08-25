# Author : hdj <helmut@oblig.at>
# Date   : 2014.07
# Project: maaps
# Description:
#   TODO: add some description!
# 
import os
import sys
import time
import multiprocessing as mp
import logging, logging.config
from Queue import Empty

# -----------------------------------------------------------------------------
# import global shared definitions
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parentdir not in os.sys.path:
    os.sys.path.insert(0,parentdir)
from shared import *
# -----------------------------------------------------------------------------
# configure logger
logging.config.fileConfig("%s/../logging.conf" % os.path.dirname(__file__))

class _Executor(object):
    def __init__(self, name, delay, source_code, queue):
        self.logger     = logging.getLogger('maaps.ep.loop.process')
        self.name       = name
        self.delay      = delay
        self.code       = source_code
        self.queue      = queue
        try:
            self.compiled = compile(self.code, self.name, 'exec')
        except Exception, e:
            self.logger.error('compilation failed for "%s"!', self.name)
            self.logger.error('code is: [%r]' % (self.code,))
            self.logger.exception('Exception is:')
            raise e
        self.logger.info('Loop Executor "%s" started.', self.name)

    def run(self):
        self.logger.info('Starting LOOP with a delay of %s secs.' % (self.delay,))
        while True:
            ctx             = create_global_context()
            local_ctx       = {}
            ctx[CTX_LOGGER] = self.logger

            exec(self.compiled, ctx, local_ctx)
            payload   = local_ctx.get(CTX_PAYLOAD, None)
            chainvars = ctx.get(CTX_CHAINVARS, dict(empty=True))

            if payload:
                self.logger.debug('Loop Executor (%s): got payload from code it\'s of type "%s"',
                                  self.name,
                                  type(payload))
                self.queue.put(payload)
                self.queue.put(chainvars)
            time.sleep(self.delay)


class EPLoop(object):
    def __init__(self, context, name, source_code):
        self.logger      = logging.getLogger('maaps.ep.loop')
        self.name        = name
        self.delay       = float(context.get('DELAY', 30.0))
        self.source_code = source_code
        self.queue       = mp.Queue()
        self.looper      = mp.Process( name  = self.name,
                                       target= self._run_looper,
                                       args  = ()
        )
        self.looper.daemon = True
        self.looper.start()

    def _run_looper(self):
        looper = _Executor(self.name, self.delay, self.source_code, self.queue)
        looper.run()

    def wait4data(self, runtime_context, timeout=None):
        """
        as the loop code runs in a separate process every data (payload, chainvars) exchange with context
        has to happen through the queue object.
        """
        assert timeout > 0.0 or timeout is None
        payload   = None
        chainvars = None
        try:
            payload   = self.queue.get(timeout=timeout)
            chainvars = self.queue.get(timeout=timeout)
        except Empty:  # timeout happened
            self.logger.error("%s: Timeout!", self.name)

        self.logger.debug('payload   is: %r', payload)
        self.logger.debug('chainvars is: %r', chainvars)
        runtime_context[CTX_PAYLOAD]   = payload
        runtime_context[CTX_CHAINVARS] = chainvars
        return payload

    def shutdown(self):
        """ This terminates the entrypoint process!
        Call this only on shutdown or bevor restarting the whole application!
        """
        self.looper.terminate()
        self.logger.debug('%s: Wait %s sec after termination to shutdown.', self.name, WAIT_SECS_ON_SHUTDOWN)
        time.sleep(WAIT_SECS_ON_SHUTDOWN)
        return not self.looper.is_alive()

