# Author : hdj <helmut@oblig.at>
# Date   : 2014.06
# Project: maaps
# Description:
#   TODO: add some description!
# 
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
import os, time
import multiprocessing as mp
import logging
import logging.config
import Queue
from Queue import Empty
import simplejson as json
import cgi                      # for parsing form-data
# -----------------------------------------------------------------------------
# import:
#   o) global shared definitions
#   o) necessary classes from "code" handling
import sys

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parentdir not in os.sys.path:
    os.sys.path.insert(0,parentdir)
from shared import *
from ModPython.pycode import PyCode
# -----------------------------------------------------------------------------
# configure logger
logging.config.fileConfig("%s/../logging.conf" % os.path.dirname(__file__))


def _fieldStorageToDict( fieldStorage ):
    ret = {}
    for key in fieldStorage.keys():
        ret[ key ] = fieldStorage.getvalue(key) #fieldStorage[ key ].value
    return ret


class EPHttpListener(object):
    def __init__(self, context, name):
        self.logger   = logging.getLogger('maaps.ep.httplistener')
        self.name     = name
        self.port     = context.get('PORT'   , 80)
        self.address  = context.get('ADDRESS', 'localhost')
        self.path     = context.get('PATH'   , '/')
        self.src      = context.get('code'   , None)
        self.code     = None
        self.queue    = mp.Queue()

        if self.src is not None:
            self.code = PyCode(self.name, 'inline', self.src)

        # create server process
        self.server = mp.Process(name  = self.name,
                                 target= self._run_server,
                                 args  = ()
        )

        # start server process
        self.server.daemon = True
        self.server.start()

    def wait4data(self, runtime_context, timeout=None):
        assert timeout > 0.0 or timeout is None
        data = {}
        try:
            data = self.queue.get(timeout=timeout)
        except Empty:  # timeout happened
            self.logger.error("%s: Timeout!", self.name)

        self.logger.debug('data is: %r' % (data,))
        runtime_context[CTX_PAYLOAD] = data
        return data

    def _run_server(self):
        "called from multiprocess.Process"
        self.logger.debug('Starting webserver %s:%s', self.address, self.port)
        server = TheHTTPServer( (self.address, self.port),
                                EPHttpRequestHandler,
                                path_to_use  = self.path,
                                message_queue= self.queue,
                                code         = self.code
        )
        server.serve_forever()

    def shutdown(self):
        """ This terminates the entrypoint process!
        Call this only on shutdown or bevor restarting the whole application!
        """
        self.server.terminate()
        self.logger.debug('%s: Wait %s after termination to shutdown.', self.name, WAIT_SECS_ON_SHUTDOWN)
        time.sleep(WAIT_SECS_ON_SHUTDOWN)
        return not self.server.is_alive()


class TheHTTPServer(HTTPServer, object):
    def __init__(self, server_address, handler_class, path_to_use, message_queue, code = None):
        super(TheHTTPServer, self).__init__(server_address, handler_class)
        self.logger              = logging.getLogger('maaps.ep.httplistener.instance')
        self.communication_queue = message_queue
        self.path                = path_to_use
        self.code                = code

        self.logger.info('Started HTTP with "http://%s:%s%s"', server_address[0], server_address[1], self.path)


class VerificationResult(object):
    def __init__(self, response_code=200, response_text='OK'):
        self.response_code = response_code
        self.response_text = response_text
        self.result_data   = None

    def __str__(self):
        return "response_code: %s response_text: '%r' / data: '%r'" % (self.response_code, self.response_text, self.result_data,)

    def __repr__(self):
        return self.__str__()

class EPHttpRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, m_format, *args):
        self.server.logger.info(('incoming %s' % (m_format,)) % args)

    def verify(self, incoming, runtime_context):
        ''' If the server has a code object then it will be executed ...
        '''
        result               = VerificationResult()
        result.result_data   = incoming

        if self.server.code is None:
            self.server.logger.debug('NO verify() code from user. Running without verification.')
            result.response_code = 200
            result.response_text = ''
        else:
            self.server.logger.info('#'*30)
            exception_queue = Queue.Queue()

            runtime_context[CTX_PAYLOAD] = result.response_text
            self.server.code.run(exception_queue, runtime_context)
            if not exception_queue.empty():
                pass
            else:
                result.response_code = 500
                result.result_data   = exception_queue.get(block=False)
        return result

    def do_POST(self):
        self.server.logger.debug('Header Keys: %s', self.headers.keys())
        self.server.logger.debug('Header Type: %s', type(self.headers))

        for key in self.headers.keys():
            self.server.logger.debug("%-20s %s", key, self.headers[key])

        # TODO(?): check self.path == self.server.path
        runtime_context = create_global_context()
        runtime_context[CTX_LOGGER] = self.server.logger

        if self.headers['content-type'].startswith('application/x-www-form-urlencoded'):
            # Parse the form data posted
            form = cgi.FieldStorage(
                fp                  = self.rfile,
                headers             = self.headers,
                keep_blank_values   = 1,
                environ             = { 'REQUEST_METHOD'   : 'POST',
                                        'CONTENT_TYPE'     : self.headers['Content-Type'],
                                      }
            )
            data = _fieldStorageToDict(form)
            result = self.verify(data, runtime_context)
        elif self.headers['content-type'].startswith('application/json'):
            varLen   = int(self.headers['content-length'])
            data_raw = self.rfile.read(varLen)
            data     = json.loads(data_raw)
            result   = self.verify(data, runtime_context)
        else:
            result               = VerificationResult()
            result.response_code = 501
            result.response_text = "Unknown Content-Type: %s" % (self.headers['Content-Type'],)
            self.server.logger.error(result.response_text)
        assert(result is not None)
        self.server.logger.debug('Result is "%r"', result)
        self.server.communication_queue.put( result.result_data )
        self.send_response(result.response_code, result.response_text)
        self.end_headers()


