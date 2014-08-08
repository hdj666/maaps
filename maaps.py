#!/usr/bin/python
# coding=utf-8
#
# Author : hdj <helmut@oblig.at>
# Date   : 2014.06
# Project: maaps
# Description:
#   TODO: write a description
#
import copy
import logging, logging.config
import multiprocessing as mp
import Queue
import sys
import atexit
from maaps_parser                   import parse
from shared                         import *                # shared global definitions (enums, constants, ...)
from EPHttpListener.EPHttpListener  import EPHttpListener   # entrypoint
from EPLoop.EPLoop                  import EPLoop           # entrypoint
from ModPython.ModPython            import ModPython        # module
from ModPython.pycode               import PyCode           # low level python code object

class StepBase(object):
    def __init__(self, name, application, step_type, step_subtype, step_content):
        self.logger                 = logging.getLogger('maaps.step')
        self.application            = application
        self.name                   = name
        self.stype                  = step_type
        self.sub_stype              = step_subtype
        self.content                = step_content
        self.local_context          = dict()

        self.is_entrypoint          = False
        self.is_exception_handler   = False

        self.logger.debug(  'Creating Step: name "%s" type "%s" subtype "%s" content "%r"',
                            self.name,
                            self.stype,
                            self.sub_stype,
                            self.content
        )

    def apply_assignements_to_context(self):
        # self.content is a list with dicts from yacc
        # like: [
        #   {'subtype': 'assignement', 'type': 'expression', 'value': 'Path = "/testme"'},
        #   {'subtype': 'assignement', 'type': 'expression', 'value': 'Adress = "localhost"'},
        #   {'subtype': 'assignement', 'type': 'expression', 'value': 'Port = 8000'}
        # ]
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug( '#'*80 )
            self.logger.debug( "%s: apply_assignements_to_context content is:", self.name )
            for content in self.content:
                self.logger.debug('%s', content)
            self.logger.debug( '#'*80 )

        for content in self.content:
            expr = None
            if content['subtype'] == 'assignement':
                expr = content['value']
            elif content['subtype'] == 'code':
                expr = "code = %r" % (content['value'],)
            assert(expr is not None)
            exec(expr, self.local_context)

    def __str__(self):
        return "\t\tStep: %s" % (self.name,)


class StepEntrypoint(StepBase):
    def __init__(self, name, application, step_type, step_subtype, step_content):
        super(StepEntrypoint, self).__init__(name, application, step_type, step_subtype, step_content)
        self.logger        = logging.getLogger('maaps.ep')
        self.is_entrypoint = True
        self.instance      = None

        atexit.register(self.shutdown)

        self.apply_assignements_to_context()

        if self.sub_stype == 'HttpListener':
            self.logger   = logging.getLogger('maaps.ep.httplistener')
            self.instance = EPHttpListener(self.local_context, self.name)
        elif self.sub_stype == 'LOOP':
            self.logger = logging.getLogger('maaps.ep.loop')

            assert('code' in self.local_context)

            source_code = PyCode.tidy_source_code(self.local_context['code'])
            if not source_code:
                raise SyntaxError("%s: No CODE/CONTEXT block in LOOP statement!", self.name)

            self.instance = EPLoop(self.local_context, self.name, source_code)

        else:
            raise TypeError('%s: unknown entrypoint-type "%s"' % (self.name, self.sub_stype,))

    def run(self, runtime_context):
        result = self.instance.wait4data(runtime_context)
        self.logger.info('%s: Data from EP: %r', self.name, result)
        self.logger.debug('%s: and context is "%r".', self.name, runtime_context)
        return result

    def shutdown(self):
        self.logger.info('%s: Running SHUTDOWN!', self.name)
        success = self.instance.shutdown()
        if success:
            self.logger.info('%s: Instance shutdown successfull.', self.name)
        else:
            self.logger.error('%s: Failed to shutdown instance!', self.name)


class StepModule(StepBase):
    def __init__(self, name, application, step_type, step_subtype, step_content):
        super(StepModule, self).__init__(name, application, step_type, step_subtype, step_content)
        self.instance       = None
        self.timeout        = 0     # Execution timeout, comes from maaps-file
        self.filename       = None
        self.source         = None
        self.compiled       = None

        if self.sub_stype == 'python':
            self.apply_assignements_to_context()

            self.filename = self.local_context.get('FILENAME', None)
            self.timeout  = self.local_context.get('TIMEOUT',  0)
            self.source   = self.local_context.get('code',     None)

            if self.filename is not None:
                assert(self.source is None)
                with file(self.filename, 'r') as f:
                    self.source = f.read()
            else:
                self.filename = 'inline'

            if self.source is None:
                raise SyntaxError("module python: Need 'Filename' or 'Code' entry.")

            self.instance = ModPython(self.name, self.filename, self.source, self.timeout)
        else:
            raise TypeError('unknown module-type "%s"' % (self.sub_stype,))

    def run(self, runtime_context):
        self.instance.run(runtime_context) # <== Exceptions are handled in the chain


class StepExceptionHandler(StepBase):
    def __init__(self, name, application, step_type, step_subtype, step_content):
        super(StepExceptionHandler, self).__init__(name, application, step_type, step_subtype, step_content)
        self.is_exception_handler   = True
        self.call = None
        for instruction in step_content:
            if instruction['subtype'] == 'code':
                self.pycode = PyCode(self.name, 'inline', instruction['value'])
            elif instruction['subtype'] == 'gosub':
                self.call = instruction['value']

    def run(self, runtime_context):
        self.logger.debug('Executing ExceptionHandler "%s" code: "%r"', self.name, self.pycode.code)
        self.logger.info('Executing ExceptionHandler "%s".', self.name)
        exception_queue = Queue.Queue()
        self.pycode.run(exception_queue, runtime_context)
        try:
            exc_type, exc_obj, exc_trace = exception_queue.get(block=False)
            self.logger.error("%s Exception Info: %r", self.name, exc_obj)
            raise exc_obj
        except Queue.Empty:
            pass
        if self.call is not None:
            call_chain = self.application.get_chain(self.call)
            if not call_chain:
                raise SyntaxError('Chain "%s" does not exist!' % (self.call,))
            call_chain.run( runtime_context, False )


class StepCall(StepBase):
    def __init__(self, name, application, step_type, step_subtype, step_content):
        super(StepCall, self).__init__(name, application, step_type, step_subtype, step_content)
        self.call_chain_name=step_subtype
        self.pycode      = PyCode(self.name, 'inline(StepCall)', self.content[0]['value'])


    def run(self, runtime_context):
        assert(CTX_PAYLOAD in runtime_context)

        chain = self.application.get_chain(self.call_chain_name)
        if not chain:
            raise SyntaxError('Chain "%s" does not exist!' % (self.call_chain_name,))

        exception_queue = Queue.Queue()
        self.pycode.run( exception_queue, runtime_context)
        try:
            exception_info = exception_queue.get(block=False)
            raise RuntimeError(exception_info)
        except Queue.Empty:
            pass

        chain.run( runtime_context, False )
        self.logger.info("StepCall runtime_contex[payload] %s", runtime_context[CTX_PAYLOAD])


class StepFactory(object):
    @staticmethod
    def create_step(name, application, step_type, step_subtype, step_content):
        if step_type == 'MODULE':
            return StepModule(name, application, step_type, step_subtype, step_content)
        elif step_type == 'ENTRYPOINT':
            return StepEntrypoint(name, application, step_type, step_subtype, step_content)
        elif step_type == 'ONEXCEPTION':
            return StepExceptionHandler(name, application, step_type, step_subtype, step_content)
        elif step_type == 'CALL':
            return StepCall(name, application, step_type, step_subtype, step_content)
        else:
            raise SyntaxError('unknown step "%s" with type: "%s"' % (name, step_type,))


class Chain(object):
    """
    Chain execution happens in a (newly) created process with it's own context object.
    """
    def __init__(self, name, filename, application):
        self.name               = name
        self.filename           = filename
        self.application        = application
        self.entrypoint         = None
        self.steps              = []
        self.exception_handlers = []
        self.logger             = logging.getLogger('maaps.chain')
        self.stop_execution     = False

    def __str__(self):
        ret = ['\tchain: %s' % (self.name,),]

        if self.exception_handlers:
            ret.append("%s" % (self.entrypoint,))

        for s in self.steps:
            ret.append("%s" % (s,))

        if len(self.exception_handlers) > 0:
            for s in self.exception_handlers:
                ret.append("%s" % (s,))

        return "\n".join(ret)

    @property
    def with_entypoint(self):
        return self.entrypoint

    def add_step(self, a_step):
        self.logger.debug('%s: adding step "%s"', self.name, a_step.name)
        if a_step.is_exception_handler:
            self.exception_handlers.append( a_step )
        elif a_step.is_entrypoint:
            if self.entrypoint:
                raise SyntaxError('Multible Entrypoints defined in Chain "%s"', self.name)
            self.entrypoint = a_step
        else:
            self.steps.append( a_step )

    def _run_step(self, step, context):
        """
        returns True/False
        True => continue with execution
        False=> halt chain execution
        """
        self.logger.debug('Executing the step: "%s" context is "%r"', step.name, dbg_get_context_str(context))
        try:
            self.logger.debug('calling run() of %s', step.name)
            step.run(context)
            self.logger.debug('after "calling run() of %s"', step.name)
        except Exception, e:
            msg = 'Exception in chain "%s" at step "%s" Exception = %s' % (self.name, step.name, sys.exc_info()[1],)
            context[CTX_EXCEPTION] = msg
            self.logger.error( msg )

            for handler in self.exception_handlers:
                if handler.name == step.name:
                    self.logger.critical('ExceptionHandler "%s" raised a Exception'   , handler.name)
                    self.logger.info('Circular! Don\'t execute ExceptionHandler "%s"!', handler.name )
                else:
                    self.logger.info('Executing ExceptionHandler "%s".', handler.name)
                    self._run_step(handler, context)
            return not context.get(CTX_STOP_EXECUTION, True)
        else:
            return True


    def _finish_steps(self, steps_to_finish, context):
        self.logger.debug('%s._finish_steps(): context is "%r"', self.name, context)
        for step in steps_to_finish:
            if not self._run_step(step, context):
                self.logger.debug('_run_step of "%s" returned False.', step.name)
                break


    def run(self, chain_context, preserver_context = True):
        self.logger.info('Starting Chain "%s"', self.name)
        # every run has a complete copy of the global_context
        # so changes are only for this run valid
        if preserver_context:
            runtime_context = copy.copy(chain_context)
        else:
            runtime_context = chain_context
        if self.with_entypoint:
            while True:
                self.logger.debug('(endless loop) run entrypoint %s...', self.entrypoint.name)
                payload = self.entrypoint.run(runtime_context)
                self.logger.debug('returned payload is "%r".'          , payload)
                self.logger.debug('context is "%r"'                    , runtime_context)
                if payload:
                    self.logger.debug('starting execution-thread to finish the steps.')
                    runtime_context[CTX_PAYLOAD] = payload
                    proc = mp.Process(  target = self._finish_steps,
                                        args   = (self.steps, runtime_context,),
                                        name   = self.name
                    )
                    proc.daemon = True # We don't join() running chains.
                    proc.start()
                    # should we keep a list with started processes? (there should be only one ENTRYPOINT)
        else:
            # this chain has only excuting tasks (module, call, loops, ...)
            # so we iterate through all steps and executing them.
            for step in self.steps:
                self.logger.debug('running step: %s with context: %r', step.name, dbg_get_context_str(runtime_context))
                result = self._run_step(step, runtime_context)
                self.logger.info('step "%s" result "%s".', step.name, result)
                if not result:
                    self.logger.warning('step "%s" result "%s".', step.name, result)
                    break


class Application(object):
    def __init__(self, name):
        self.name           = name
        self.chains         = {} #OrderedDict()
        self.global_ctx     = create_global_context()
        self.logger         = logging.getLogger('maaps.app')

        self.running_chains = []

    def __str__(self):
        ret = ["AppName: %s" % self.name,]
        for c in self.chains.values():
            ret.append( "%s" % (c,) )
        return "\n".join(ret)

    def add_chain(self, a_chain):
        self.logger.debug('%s: adding chain "%s"', self.name, a_chain.name)
        self.chains[ a_chain.name ] = a_chain

    def get_chain(self, name):
        return self.chains.get(name, None)

    def chain_exists(self, chain_name):
        return chain_name in self.chains

    def get_context(self):
        return self.global_ctx

    def run(self):
        """
        starts every chain with ENTRYPOINT as a process,
        the context is passed as a copy from global_context.
        """
        if len(self.chains) < 1:
            self.logger.fatal('Application "%s" has no chain definied!', self.name)
            return False

        self.logger.debug('%s: run', self.name)
        for chain in self.chains.values():
            if chain.with_entypoint:
                proc = mp.Process( name   = chain.name,
                                   target = chain.run,
                                   args   = (copy.deepcopy(self.global_ctx),)
                )
                proc.start()
                self.running_chains.append(proc)
        return True

    def wait(self, timeout = None):
        for running in self.running_chains:
            running.join(timeout)

    def shutdown(self):
        self.logger.info('Shutting down Application "%s"', self.name)
        for running in self.running_chains:
            self.logger.debug("Shutdown: %s", running.name)
            running.terminate() # <== should we check the return?
            running.join()


class Maaps(object):
    def __init__(self):
        self.logger       = logging.getLogger('maaps')
        self.applications = {}

    def loop(self):
        if len(self.applications) < 1:
            self.logger.error('No Application to run!')
            return

        for app in self.applications.values():
            print app

        while True:
            for app in self.applications.values():
                app.wait(2)
           # self.logger.debug('Time for housekeeping ...')

    def start(self):
        for root, dirs, files in os.walk('./', topdown=True):
            for app_name in dirs:
                if not app_name.startswith('_'):
                    self.start_app(app_name)
            # we need only the first level of application directories
            del dirs[0:len(dirs)]

    def start_app(self, app_name):
        if app_name.startswith('_'):
            self.logger.debug('Application "%s", name starts with a "_", skipping application.', app_name)
            return
        self.logger.debug('Starting app "%s"', app_name)

        save_cwd = os.getcwd()
        os.chdir(app_name)
        assert(self.applications.get(app_name, None) is None)
        self.applications[app_name] = Application(app_name)

        chains = parse('MAIN')
        chains.reverse() # <= The yacc works bottom-up so we reverse() it

        self.logger.info('Application "%s" compiled. Instatiating it now ....', app_name)
        for c in chains:
            c['name'] = c['name'].lstrip('"').rstrip('"')

            chain_obj = Chain( c['name'], c['filename'], self.applications[app_name] )

            c['steps'].reverse()
            for s in c['steps']:
                s['name'] = s['name'].lstrip('"').rstrip('"')
                step_obj = StepFactory.create_step( s['name'],
                                                    self.applications[app_name],
                                                    s['type'],
                                                    s['subtype'],
                                                    s['content'] )
                chain_obj.add_step( step_obj )
            self.applications[app_name].add_chain(chain_obj)
        if not self.applications[app_name].run():
            self.logger.error('Failed to start Application "%s"!', app_name)
            del self.applications[app_name]
        os.chdir(save_cwd)

    def restart(self, app_name):
        raise NotImplementedError('restart() needs implementation!')

if __name__ == '__main__':
    os.chdir('Applications')
    maaps = Maaps()
    maaps.start()
    maaps.loop()
