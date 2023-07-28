#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright 2012 Matt Martz
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import builtins
import csv
import concurrent.futures
import datetime
import errno
import json
import math
import os
import platform
import re
import socket
import sys
import threading
import timeit
import time
import xml.parsers.expat
from argparse import ArgumentParser as ArgParser, SUPPRESS as ARG_SUPPRESS
from io import StringIO, BytesIO
from urllib.request import urlopen, Request, HTTPError, AbstractHTTPHandler, ProxyHandler, HTTPDefaultErrorHandler, HTTPRedirectHandler, HTTPErrorProcessor, OpenerDirector
from urllib.parse import urlparse
from urllib.error import URLError
from queue import Queue
from http.client import HTTPConnection, BadStatusLine
from hashlib import md5
from http.client import HTTPSConnection

try:
    import gzip
    GZIP_BASE = gzip.GzipFile
except ImportError:
    gzip = None
    GZIP_BASE = object
try:
    import xml.etree.ElementTree as ET
    try:
        from xml.etree.ElementTree import _Element as ET_Element
    except ImportError:
        pass
except ImportError:
    from xml.dom import minidom as DOM
    from xml.parsers.expat import ExpatError
    ET = None
try:
    from urllib.parse import parse_qs
except ImportError:
    from cgi import parse_qs
try:
    import ssl
    try:
        CERT_ERROR = (ssl.CertificateError,)
    except AttributeError:
        CERT_ERROR = tuple()
    HTTP_ERRORS = ((HTTPError, URLError, socket.error, ssl.SSLError, BadStatusLine) + CERT_ERROR)
except ImportError:
    ssl = None
    HTTP_ERRORS = (HTTPError, URLError, socket.error, BadStatusLine)

etree_iter = ET.Element.iter
thread_is_alive = threading.Thread.is_alive
DEBUG = False
_GLOBAL_DEFAULT_TIMEOUT = object()
PARSER_TYPE_INT = int
PARSER_TYPE_STR = str
PARSER_TYPE_FLOAT = float
_py3_print = getattr(builtins, 'print')
_py3_utf8_stdout = sys.stdout
_py3_utf8_stderr = sys.stderr
FakeSocket = None
__version__ = '2.2'

class speedtest_cli(object):
    def __init__(self):
        pass

    def to_utf8(self, v):
        return v
    
    def _print(self, *args, **kwargs):
        if kwargs.get('file') == sys.stderr:
            kwargs['file'] = _py3_utf8_stderr
        else:
            kwargs['file'] = kwargs.get('file', _py3_utf8_stdout)
        _py3_print(*args, **kwargs)
    class SpeedtestException(Exception):
        pass
    
    class SpeedtestCLIError(SpeedtestException):
        pass
    
    class SpeedtestHTTPError(SpeedtestException):
        pass
    
    class SpeedtestConfigError(SpeedtestException):
        pass
    
    class SpeedtestServersError(SpeedtestException):
        pass
    
    class ConfigRetrievalError(SpeedtestHTTPError):
        pass
    
    class ServersRetrievalError(SpeedtestHTTPError):
        pass
    
    class InvalidServerIDType(SpeedtestException):
        pass
    
    class NoMatchedServers(SpeedtestException):
        pass
    
    class SpeedtestMiniConnectFailure(SpeedtestException):
        pass
    
    class InvalidSpeedtestMiniServer(SpeedtestException):
        pass
    
    class ShareResultsConnectFailure(SpeedtestException):
        pass
    
    class ShareResultsSubmitFailure(SpeedtestException):
        pass
    
    class SpeedtestUploadTimeout(SpeedtestException):
        pass
    
    class SpeedtestBestServerFailure(SpeedtestException):
        pass
    
    class SpeedtestMissingBestServer(SpeedtestException):
        pass
    
    def create_connection(self, address, timeout=_GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        host, port = address
        err = None
        for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
            af, socktype, proto, canonname, sa = res
            sock = None
            try:
                sock = socket.socket(af, socktype, proto)
                if timeout is not _GLOBAL_DEFAULT_TIMEOUT:
                    sock.settimeout(float(timeout))
                if source_address:
                    sock.bind(source_address)
                sock.connect(sa)
                return sock
            except socket.error:
                err = self.get_exception()
                if sock is not None:
                    sock.close()
        if err is not None:
            print(err)
            sys.exit(0)
        else:
            print(socket.error("getaddrinfo returns an empty list"))
            sys.exit(0)
    
    class SpeedtestHTTPConnection(HTTPConnection):
        def __init__(self, *args, **kwargs):
            source_address = kwargs.pop('source_address', None)
            timeout = kwargs.pop('timeout', 10)
            self._tunnel_host = None
            HTTPConnection.__init__(self, *args, **kwargs)
            self.source_address = source_address
            self.timeout = timeout
    
        def connect(self):
            try:
                self.sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
            except (AttributeError, TypeError):
                self.sock = self.create_connection((self.host, self.port), self.timeout, self.source_address)
    
    class SpeedtestHTTPSConnection(HTTPSConnection):
        default_port = 443
        def __init__(self, *args, **kwargs):
            source_address = kwargs.pop('source_address', None)
            timeout = kwargs.pop('timeout', 10)
            self._tunnel_host = None
            HTTPSConnection.__init__(self, *args, **kwargs)
            self.timeout = timeout
            self.source_address = source_address
    
        def connect(self):
            try:
                self.sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
            except (AttributeError, TypeError):
                self.sock = self.create_connection((self.host, self.port), self.timeout, self.source_address)
            if ssl:
                ssl._create_default_https_context = ssl._create_unverified_context
                self.sock = ssl.create_default_context().wrap_socket(self.sock, server_hostname=self.host)
                try:
                    self.sock.server_hostname = self.host
                except AttributeError:
                    pass
        
    def _build_connection(self, connection, source_address, timeout, context=None):
        def inner(host, **kwargs):
            kwargs.update({
                'source_address': source_address,
                'timeout': timeout
            })
            if context:
                kwargs['context'] = context
            return connection(host, **kwargs)
        return inner
    
    class SpeedtestHTTPHandler(AbstractHTTPHandler):
        def __init__(self, debuglevel=0, source_address=None, timeout=10):
            AbstractHTTPHandler.__init__(self, debuglevel)
            self.source_address = source_address
            self.timeout = timeout
        
        def http_open(self, req):
            return self.do_open(speedtest_cli()._build_connection(speedtest_cli().SpeedtestHTTPConnection, self.source_address, self.timeout), req)
        
        http_request = AbstractHTTPHandler.do_request_
    
    class SpeedtestHTTPSHandler(AbstractHTTPHandler):
        def __init__(self, debuglevel=0, context=None, source_address=None, timeout=10):
            AbstractHTTPHandler.__init__(self, debuglevel)
            self._context = context
            self.source_address = source_address
            self.timeout = timeout
        
        def https_open(self, req):
            return self.do_open(speedtest_cli()._build_connection(speedtest_cli().SpeedtestHTTPSConnection, self.source_address, self.timeout, context=self._context), req)
    
        https_request = AbstractHTTPHandler.do_request_
    
    def build_opener(self, source_address=None, timeout=10):
        self.printer('Timeout set to %d' % timeout, debug=True)
        if source_address:
            source_address_tuple = (source_address, 0)
            self.printer('Binding to source address: %r' % (source_address_tuple,),
                    debug=True)
        else:
            source_address_tuple = None
        handlers = [ProxyHandler(), speedtest_cli().SpeedtestHTTPHandler(source_address=source_address_tuple, timeout=timeout), speedtest_cli().SpeedtestHTTPSHandler(source_address=source_address_tuple, timeout=timeout), HTTPDefaultErrorHandler(), HTTPRedirectHandler(), HTTPErrorProcessor()]
        opener = OpenerDirector()
        opener.addheaders = [('User-agent', speedtest_cli().build_user_agent())]
        for handler in handlers:
            opener.add_handler(handler)
        return opener
    
    class GzipDecodedResponse(GZIP_BASE):
        def __init__(self, response):
            if not gzip:
                print(speedtest_cli().SpeedtestHTTPError('HTTP response body is gzip encoded, but gzip support is not available'))
                sys.exit(0)
            IO = BytesIO or StringIO
            self.io = IO()
            while 1:
                chunk = response.read(1024)
                if len(chunk) == 0:
                    break
                self.io.write(chunk)
            self.io.seek(0)
            gzip.GzipFile.__init__(self, mode='rb', fileobj=self.io)
    
        def close(self):
            try:
                gzip.GzipFile.close(self)
            finally:
                self.io.close()
    
    def get_exception(self):
        return sys.exc_info()[1]
    
    def distance(self, origin, destination):
        lat1, lon1 = origin
        lat2, lon2 = destination
        radius = 6371  # km
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) * math.sin(dlon / 2) *
             math.sin(dlon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        d = radius * c
        
        return d
    
    def build_user_agent(self):
        ua_tuple = ('Mozilla/5.0', '(%s; U; %s; en-us)' % (platform.platform(), platform.architecture()[0]), 'Python/%s' % platform.python_version(), '(KHTML, like Gecko)', 'speedtest-cli/%s' % __version__)
        user_agent = ' '.join(ua_tuple)
        self.printer('User-Agent: %s' % user_agent, debug=True)
        return user_agent
    
    def build_request(self, url, data=None, headers=None, bump='0', secure=False):
        if not headers:
            headers = {}
        if url[0] == ':':
            scheme = ('http', 'https')[bool(secure)]
            schemed_url = '%s%s' % (scheme, url)
        else:
            schemed_url = url
        if '?' in url:
            delim = '&'
        else:
            delim = '?'
        final_url = '%s%sx=%s.%s' % (schemed_url, delim, int(timeit.time.time() * 1000), bump)
        headers.update({'Cache-Control': 'no-cache'})
        self.printer('%s %s' % (('GET', 'POST')[bool(data)], final_url), debug=True)
        return Request(final_url, data=data, headers=headers)
    
    def catch_request(self, request, opener=None):
        if opener:
            _open = opener.open
        else:
            _open = urlopen
        try:
            uh = _open(request)
            if request.get_full_url() != uh.geturl():
                self.printer('Redirected to %s' % uh.geturl(), debug=True)
            return uh, False
        except HTTP_ERRORS:
            e = self.get_exception()
            return None, e
    
    def get_response_stream(self, response):
        try:
            getheader = response.headers.getheader
        except AttributeError:
            getheader = response.getheader
        if getheader('content-encoding') == 'gzip':
            return speedtest_cli().GzipDecodedResponse(response)
        return response
    
    def get_attributes_by_tag_name(self, dom, tag_name):
        elem = dom.getElementsByTagName(tag_name)[0]
        return dict(list(elem.attributes.items()))
    
    def print_dots(self, _):
        def inner(current, total, start=False, end=False):
            sys.stdout.write('.')
            if current + 1 == total and end is True:
                sys.stdout.write('\n')
            sys.stdout.flush()
        
        return inner
    
    def do_nothing(*args, **kwargs):
        pass
    
    class HTTPDownloader(threading.Thread):
        def __init__(self, i, request, start, timeout, opener=None):
            threading.Thread.__init__(self)
            self.request = request
            self.result = [0]
            self.start_time = start
            self.timeout = timeout
            self.i = i
            if opener:
                self._opener = opener.open
            else:
                self._opener = urlopen
    
        def run(self):
            concurrent.futures.ThreadPoolExecutor().submit(self.work).result()
    
        def work(self):
            try:
                if (timeit.default_timer() - self.start_time) <= self.timeout:
                    f = self._opener(self.request)
                    while (timeit.default_timer() - self.start_time) <= self.timeout:
                        self.result.append(len(f.read(10240)))
                        if self.result[-1] == 0:
                            break
                    f.close()
            except IOError:
                pass
            except HTTP_ERRORS:
                pass
    
    class HTTPUploaderData(object):
        def __init__(self, length, start, timeout):
            self.length = length
            self.start = start
            self.timeout = timeout
            self._data = None
            self.total = [0]
        
        def pre_allocate(self):
            chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            multiplier = int(round(int(self.length) / 36.0))
            IO = BytesIO or StringIO
            try:
                self._data = IO(('content1=%s' % (chars * multiplier)[0:int(self.length) - 9]).encode())
            except MemoryError:
                print(speedtest_cli().SpeedtestCLIError('Insufficient memory to pre-allocate upload data. Please \nuse --no-pre-allocate'))
        
        @property
        def data(self):
            if not self._data:
                self.pre_allocate()
            return self._data
    
        def read(self, n=10240):
            if ((timeit.default_timer() - self.start) <= self.timeout):
                chunk = self.data.read(n)
                self.total.append(len(chunk))
                return chunk
            else:
                print(speedtest_cli().SpeedtestUploadTimeout())
                sys.exit(0)
    
        def __len__(self):
            return self.length
    
    class HTTPUploader(threading.Thread):
        def __init__(self, i, request, start, size, timeout, opener=None):
            threading.Thread.__init__(self)
            self.request = request
            self.request.data.start = self.starttime = start
            self.size = size
            self.result = 0
            self.timeout = timeout
            self.i = i
            if opener:
                self._opener = opener.open
            else:
                self._opener = urlopen
    
        def run(self):
            concurrent.futures.ThreadPoolExecutor().submit(self.work).result()
    
        def work(self):
            request = self.request
            try:
                if ((timeit.default_timer() - self.starttime) <= self.timeout):
                    try:
                        f = self._opener(request)
                    except TypeError:
                        request = speedtest_cli().build_request(self.request.get_full_url(), data=request.data.read(self.size))
                        f = self._opener(request)
                    f.read(11)
                    f.close()
                    self.result = sum(self.request.data.total)
                else:
                    self.result = 0
            except (IOError, speedtest_cli().SpeedtestUploadTimeout):
                self.result = sum(self.request.data.total)
            except HTTP_ERRORS:
                self.result = 0
    
    class SpeedtestResults(object):
        def __init__(self, download=0, upload=0, ping=0, server=None, client=None, opener=None, secure=False):
            self.download = download
            self.upload = upload
            self.ping = ping
            if server is None:
                self.server = {}
            else:
                self.server = server
            self.client = client or {}
            self._share = None
            self.timestamp = '%sZ' % datetime.datetime.utcnow().isoformat()
            self.bytes_received = 0
            self.bytes_sent = 0
            if opener:
                self._opener = opener
            else:
                self._opener = speedtest_cli().build_opener()
            self._secure = secure
    
        def __repr__(self):
            return repr(self.dict())
        
        def share(self):
            if self._share:
                return self._share
            download = int(round(self.download / 1000.0, 0))
            ping = int(round(self.ping, 0))
            upload = int(round(self.upload / 1000.0, 0))
            api_data = ['recommendedserverid=%s' % self.server['id'], 'ping=%s' % ping, 'screenresolution=', 'promo=', 'download=%s' % download, 'screendpi=', 'upload=%s' % upload, 'testmethod=http', 'hash=%s' % md5(('%s-%s-%s-%s' % (ping, upload, download, '297aae72')).encode()).hexdigest(), 'touchscreen=none', 'startmode=pingselect', 'accuracy=1', 'bytesreceived=%s' % self.bytes_received, 'bytessent=%s' % self.bytes_sent, 'serverid=%s' % self.server['id']]
            headers = {'Referer': 'http://c.speedtest.net/flash/speedtest.swf'}
            request = speedtest_cli().build_request('https://www.speedtest.net/api/api.php', data='&'.join(api_data).encode(), headers=headers, secure=self._secure)
            f, e = speedtest_cli().catch_request(request, opener=self._opener)
            if e:
                print(speedtest_cli().ShareResultsConnectFailure(e))
                sys.exit(0)
            response = f.read()
            code = f.code
            f.close()
            if int(code) != 200:
                print(speedtest_cli().ShareResultsSubmitFailure('Could not submit results to speedtest.net'))
                sys.exit(0)
            qsargs = parse_qs(response.decode())
            resultid = qsargs.get('resultid')
            if not resultid or len(resultid) != 1:
                print(speedtest_cli().ShareResultsSubmitFailure('Could not submit results to speedtest.net'))
                sys.exit(0)
            self._share = 'https://www.speedtest.net/result/%s.png' % resultid[0]
        
        def dict(self):
            return {'download': self.download, 'upload': self.upload, 'ping': self.ping, 'server': self.server, 'timestamp': self.timestamp, 'bytes_sent': self.bytes_sent, 'bytes_received': self.bytes_received, 'share': self._share, 'client': self.client}
        
        @staticmethod
        def csv_header(delimiter=','):
            row = ['Server ID', 'Sponsor', 'Server Name', 'Timestamp', 'Distance', 'Ping', 'Download', 'Upload', 'Share', 'IP Address']
            out = StringIO()
            writer = csv.writer(out, delimiter=delimiter, lineterminator='')
            writer.writerow([speedtest_cli().to_utf8(v) for v in row])
            return out.getvalue()
        
        def csv(self, delimiter=','):
            data = self.dict()
            out = StringIO()
            writer = csv.writer(out, delimiter=delimiter, lineterminator='')
            row = [data['server']['id'], data['server']['sponsor'], data['server']['name'], data['timestamp'], data['server']['d'], data['ping'], data['download'], data['upload'], self._share or '', self.client['ip']]
            writer.writerow([speedtest_cli().to_utf8(v) for v in row])
            return out.getvalue()
        
        def json(self, pretty=False):
            kwargs = {}
            if pretty:
                kwargs.update({'indent': 4, 'sort_keys': True})
            return json.dumps(self.dict(), **kwargs)
    
    class Speedtest(object):
        def __init__(self, config=None, source_address=None, timeout=10, secure=False):
            self.config = {}
            self._source_address = source_address
            self._timeout = timeout
            self._opener = speedtest_cli().build_opener(source_address, timeout)
            self._secure = secure
            self.get_config()
            if config is not None:
                self.config.update(config)
            self.servers = {}
            self.closest = []
            self._best = {}
            self.results = speedtest_cli().SpeedtestResults(client=self.config['client'], opener=self._opener, secure=secure)
        
        @property
        def best(self):
            if not self._best:
                self.get_best_server()
            return self._best
        
        def get_config(self):
            headers = {}
            if gzip:
                headers['Accept-Encoding'] = 'gzip'
            request = speedtest_cli().build_request('https://www.speedtest.net/speedtest-config.php', headers=headers, secure=self._secure)
            uh, e = speedtest_cli().catch_request(request, opener=self._opener)
            if e:
                print(speedtest_cli().ConfigRetrievalError(e))
                sys.exit(0)
            configxml_list = []
            stream = speedtest_cli().get_response_stream(uh)
            while 1:
                try:
                    configxml_list.append(stream.read(1024))
                except (OSError, EOFError):
                    raise speedtest_cli().ConfigRetrievalError(speedtest_cli().get_exception())
                if len(configxml_list[-1]) == 0:
                    break
            stream.close()
            uh.close()
            if int(uh.code) != 200:
                return None
            configxml = ''.encode().join(configxml_list)
            speedtest_cli().printer('Config XML:\n%s' % configxml, debug=True)
            try:
                try:
                    root = ET.fromstring(configxml)
                except ET.ParseError:
                    e = speedtest_cli().get_exception()
                    raise speedtest_cli().SpeedtestConfigError(
                        'Malformed speedtest.net configuration: %s' % e
                    )
                server_config = root.find('server-config').attrib
                download = root.find('download').attrib
                upload = root.find('upload').attrib
                client = root.find('client').attrib
            except AttributeError:
                try:
                    root = DOM.parseString(configxml)
                except ExpatError:
                    e = speedtest_cli().get_exception()
                    print(speedtest_cli().SpeedtestConfigError('Malformed speedtest.net configuration: %s' % e))
                server_config = speedtest_cli().get_attributes_by_tag_name(root, 'server-config')
                download = speedtest_cli().get_attributes_by_tag_name(root, 'download')
                upload = speedtest_cli().get_attributes_by_tag_name(root, 'upload')
                client = speedtest_cli().get_attributes_by_tag_name(root, 'client')
            ignore_servers = [int(i) for i in server_config['ignoreids'].split(',') if i]
            ratio = int(upload['ratio'])
            upload_max = int(upload['maxchunkcount'])
            up_sizes = [32768, 65536, 131072, 262144, 524288, 1048576, 7340032]
            sizes = {'upload': up_sizes[ratio - 1:], 'download': [350, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000]}
            size_count = len(sizes['upload'])
            upload_count = int(math.ceil(upload_max / size_count))
            counts = {'upload': upload_count, 'download': int(download['threadsperurl'])}
            threads = {'upload': int(upload['threads']), 'download': int(server_config['threadcount']) * 2}
            length = {'upload': int(upload['testlength']), 'download': int(download['testlength'])}
            self.config.update({'client': client, 'ignore_servers': ignore_servers, 'sizes': sizes, 'counts': counts, 'threads': threads, 'length': length, 'upload_max': upload_count * size_count})
            try:
                self.lat_lon = (float(client['lat']), float(client['lon']))
            except ValueError:
                print(speedtest_cli().SpeedtestConfigError('Unknown location: lat=%r lon=%r' % (client.get('lat'), client.get('lon'))))
                sys.exit(0)
            speedtest_cli().printer('Config:\n%r' % self.config, debug=True)
            return self.config
        
        def get_servers(self, servers=None, exclude=None):
            if servers is None:
                servers = []
            if exclude is None:
                exclude = []
            self.servers.clear()
            for server_list in (servers, exclude):
                for i, s in enumerate(server_list):
                    try:
                        server_list[i] = int(s)
                    except ValueError:
                        print(speedtest_cli().InvalidServerIDType('%s is an invalid server type, must be int' % s))
                        sys.exit(0)
            urls = ['https://www.speedtest.net/speedtest-servers-static.php', 'https://c.speedtest.net/speedtest-servers-static.php', 'https://www.speedtest.net/speedtest-servers.php', 'https://c.speedtest.net/speedtest-servers.php']
            headers = {}
            if gzip:
                headers['Accept-Encoding'] = 'gzip'
            errors = []
            for url in urls:
                try:
                    request = speedtest_cli().build_request('%s?threads=%s' % (url, self.config['threads']['download']), headers=headers, secure=self._secure)
                    uh, e = speedtest_cli().catch_request(request, opener=self._opener)
                    if e:
                        errors.append('%s' % e)
                        print(speedtest_cli().ServersRetrievalError())
                        sys.exit(0)
                    stream = speedtest_cli().get_response_stream(uh)
                    serversxml_list = []
                    while 1:
                        try:
                            serversxml_list.append(stream.read(1024))
                        except (OSError, EOFError):
                            print(speedtest_cli().ServersRetrievalError(speedtest_cli().get_exception()))
                            sys.exit(0)
                        if len(serversxml_list[-1]) == 0:
                            break
                    stream.close()
                    uh.close()
                    if int(uh.code) != 200:
                        print(speedtest_cli().ServersRetrievalError())
                        sys.exit(0)
                    serversxml = ''.encode().join(serversxml_list)
                    speedtest_cli().printer('Servers XML:\n%s' % serversxml, debug=True)
                    try:
                        try:
                            try:
                                root = ET.fromstring(serversxml)
                            except ET.ParseError:
                                e = speedtest_cli().get_exception()
                                print(speedtest_cli().SpeedtestServersError('Malformed speedtest.net server list: %s' % e))
                                sys.exit(0)
                            elements = etree_iter(root, 'server')
                        except AttributeError:
                            try:
                                root = DOM.parseString(serversxml)
                            except ExpatError:
                                e = speedtest_cli().get_exception()
                                print(speedtest_cli().SpeedtestServersError('Malformed speedtest.net server list: %s' % e))
                                sys.exit(0)
                            elements = root.getElementsByTagName('server')
                    except (SyntaxError, xml.parsers.expat.ExpatError):
                        print(speedtest_cli().ServersRetrievalError())
                        sys.exit(0)
                    for server in elements:
                        try:
                            attrib = server.attrib
                        except AttributeError:
                            attrib = dict(list(server.attributes.items()))
                        if servers and int(attrib.get('id')) not in servers:
                            continue
                        if (int(attrib.get('id')) in self.config['ignore_servers'] or int(attrib.get('id')) in exclude):
                            continue
                        try:
                            d = speedtest_cli().distance(self.lat_lon, (float(attrib.get('lat')), float(attrib.get('lon'))))
                        except:
                            continue
                        attrib['d'] = d
                        try:
                            self.servers[d].append(attrib)
                        except KeyError:
                            self.servers[d] = [attrib]
                    break
                except speedtest_cli().ServersRetrievalError:
                    continue
            if (servers or exclude) and not self.servers:
                print(speedtest_cli().NoMatchedServers())
                sys.exit(0)
            return self.servers
        
        def set_mini_server(self, server):
            urlparts = urlparse(server)
            name, ext = os.path.splitext(urlparts[2])
            if ext:
                url = os.path.dirname(server)
            else:
                url = server
            request = speedtest_cli().build_request(url)
            uh, e = speedtest_cli().catch_request(request, opener=self._opener)
            if e:
                print(speedtest_cli().SpeedtestMiniConnectFailure('Failed to connect to %s' % server))
                sys.exit(0)
            else:
                text = uh.read()
                uh.close()
            extension = re.findall('upload_?[Ee]xtension: "([^"]+)"', text.decode())
            if not extension:
                for ext in ['php', 'asp', 'aspx', 'jsp']:
                    try:
                        f = self._opener.open('%s/speedtest/upload.%s' % (url, ext))
                    except:
                        pass
                    else:
                        data = f.read().strip().decode()
                        if (f.code == 200 and len(data.splitlines()) == 1 and re.match('size=[0-9]', data)):
                            extension = [ext]
                            break
            if not urlparts or not extension:
                print(speedtest_cli().InvalidSpeedtestMiniServer('Invalid Speedtest Mini Server: %s' % server))
                sys.exit(0)
            self.servers = [{'sponsor': 'Speedtest Mini', 'name': urlparts[1], 'd': 0, 'url': '%s/speedtest/upload.%s' % (url.rstrip('/'), extension[0]), 'latency': 0, 'id': 0}]
            return self.servers
        
        def get_closest_servers(self, limit=5):
            if not self.servers:
                self.get_servers()
            for d in sorted(self.servers.keys()):
                for s in self.servers[d]:
                    self.closest.append(s)
                    if len(self.closest) == limit:
                        break
                else:
                    continue
                break
            speedtest_cli().printer('Closest Servers:\n%r' % self.closest, debug=True)
            return self.closest
        
        def get_best_server(self, servers=None):
            if not servers:
                if not self.closest:
                    servers = self.get_closest_servers()
                
                else:
                    servers = self.closest
            if self._source_address:
                source_address_tuple = (self._source_address, 0)
            else:
                source_address_tuple = None
            user_agent = speedtest_cli().build_user_agent()
            results = {}
            for server in servers:
                cum = []
                url = os.path.dirname(server['url'])
                stamp = int(timeit.time.time() * 1000)
                latency_url = '%s/latency.txt?x=%s' % (url, stamp)
                for i in range(0, 3):
                    this_latency_url = '%s.%s' % (latency_url, i)
                    speedtest_cli().printer('%s %s' % ('GET', this_latency_url), debug=True)
                    urlparts = urlparse(latency_url)
                    try:
                        if urlparts[0] == 'https':
                            h = speedtest_cli().SpeedtestHTTPSConnection(urlparts[1], source_address=source_address_tuple)
                        else:
                            h = speedtest_cli().SpeedtestHTTPConnection(urlparts[1], source_address=source_address_tuple)
                        headers = {'User-Agent': user_agent}
                        path = '%s?%s' % (urlparts[2], urlparts[4])
                        start = timeit.default_timer()
                        h.request("GET", path, headers=headers)
                        r = h.getresponse()
                        total = (timeit.default_timer() - start)
                    except HTTP_ERRORS:
                        e = speedtest_cli().get_exception()
                        speedtest_cli().printer('ERROR: %r' % e, debug=True)
                        cum.append(3600)
                        continue
                    text = r.read(9)
                    if int(r.status) == 200 and text == 'test=test'.encode():
                        cum.append(total)
                    else:
                        cum.append(3600)
                    h.close()
                avg = round((sum(cum) / 6) * 1000.0, 3)
                results[avg] = server
            try:
                fastest = sorted(results.keys())[0]
            except IndexError:
                print(self.SpeedtestBestServerFailure('Unable to connect to servers to test latency.'))
                sys.exit(0)
            best = results[fastest]
            best['latency'] = fastest
            self.results.ping = fastest
            self.results.server = best
            self._best.update(best)
            speedtest_cli().printer('Best Server:\n%r' % best, debug=True)
            return best

        def do_nothing(self, *args, **kwargs):
            pass

        def download(self, callback=None, threads=None):
            urls = ['%s/random%sx%s.jpg' % (os.path.dirname(self.best['url']), size, size) for size in self.config['sizes']['download'] for _ in range(0, self.config['counts']['download'])]
            request_count = len(urls)
            requests = [speedtest_cli().build_request(url, bump=i, secure=self._secure) for i, url in enumerate(urls)]
            max_threads = threads or self.config['threads']['download']
            in_flight = {'threads': 0}
            def producer(q, requests, request_count):
                for i, request in enumerate(requests):
                    thread = speedtest_cli().HTTPDownloader(i, request, start, self.config['length']['download'], opener=self._opener)
                    while in_flight['threads'] >= max_threads:
                        time.sleep(1)
                    thread.start()
                    q.put(thread, True)
                    in_flight['threads'] += 1
                    callback(i, request_count, start=True)
            finished = []
            def consumer(q, request_count):
                _is_alive = thread_is_alive
                while len(finished) < request_count:
                    thread = q.get(True)
                    while _is_alive(thread):
                        thread.join(timeout=0.001)
                    in_flight['threads'] -= 1
                    finished.append(sum(thread.result))
                    callback(thread.i, request_count, end=True)
            
            def pro(q, req, req_c):
                concurrent.futures.ThreadPoolExecutor(os.cpu_count()*9999999).submit(producer, q, req, req_c).result()
    
            def cons(q, req_c):
                concurrent.futures.ThreadPoolExecutor(os.cpu_count()*9999999).submit(consumer, q, req_c).result()
            
            q = Queue(threads or self.config['threads']['upload'])
            prod_thread = threading.Thread(target=pro, daemon=True, args=(q, requests, request_count,))
            cons_thread = threading.Thread(target=cons, daemon=True, args=(q, request_count,))
            start = timeit.default_timer()
            prod_thread.start()
            cons_thread.start()
            _is_alive = thread_is_alive
            while _is_alive(prod_thread):
                prod_thread.join(timeout=0.001)
            while _is_alive(cons_thread):
                cons_thread.join(timeout=0.001)
            stop = timeit.default_timer()
            self.results.bytes_received = sum(finished)
            self.results.download = ((self.results.bytes_received / (stop - start)) * 8.0)
            if self.results.download > 100000:
                self.config['threads']['upload'] = 8
            return self.results.download
        
        def upload(self, callback=do_nothing, pre_allocate=True, threads=None):
            sizes = [size for size in self.config['sizes']['upload'] for _ in range(0, self.config['counts']['upload'])]
            request_count = self.config['upload_max']
            requests = []
            for i, size in enumerate(sizes):
                data = speedtest_cli().HTTPUploaderData(size, 0, self.config['length']['upload'])
                if pre_allocate:
                    data.pre_allocate()
                headers = {'Content-length': size}
                requests.append((speedtest_cli().build_request(self.best['url'], data, secure=self._secure,  headers=headers), size))
            max_threads = threads or self.config['threads']['upload']
            in_flight = {'threads': 0}
            def producer(q, requests, request_count):
                for i, request in enumerate(requests[:request_count]):
                    thread = speedtest_cli().HTTPUploader(i, request[0], start, request[1], self.config['length']['upload'], opener=self._opener)
                    while in_flight['threads'] >= max_threads:
                        time.sleep(1)
                    thread.start()
                    q.put(thread, True)
                    in_flight['threads'] += 1
                    callback(i, request_count, start=True)
            finished = []
            def consumer(q, request_count):
                _is_alive = thread_is_alive
                while len(finished) < request_count:
                    thread = q.get(True)
                    while _is_alive(thread):
                        thread.join(timeout=0.001)
                    in_flight['threads'] -= 1
                    finished.append(thread.result)
                    callback(thread.i, request_count, end=True)
    
            def pro(q, req, req_c):
                concurrent.futures.ThreadPoolExecutor(os.cpu_count()*9999999).submit(producer, q, req, req_c).result()
    
            def cons(q, req_c):
                concurrent.futures.ThreadPoolExecutor(os.cpu_count()*9999999).submit(consumer, q, req_c).result()
            
            q = Queue(threads or self.config['threads']['upload'])
            prod_thread = threading.Thread(target=pro, daemon=True, args=(q, requests, request_count,))
            cons_thread = threading.Thread(target=cons, daemon=True, args=(q, request_count,))
            start = timeit.default_timer()
            prod_thread.start()
            cons_thread.start()
            _is_alive = thread_is_alive
            while _is_alive(prod_thread):
                prod_thread.join(timeout=0.1)
            while _is_alive(cons_thread):
                cons_thread.join(timeout=0.1)
            stop = timeit.default_timer()
            self.results.bytes_sent = sum(finished)
            self.results.upload = ((self.results.bytes_sent / (stop - start)) * 8.0)
            return self.results.upload
    
    def version(self):
        self.printer('speedtest-cli %s' % __version__)
        self.printer('Python %s' % sys.version.replace('\n', ''))
        sys.exit(0)
    
    def csv_header(self, delimiter=','):
        self.printer(self.SpeedtestResults.csv_header(delimiter=delimiter))
        sys.exit(0)
    
    def parse_args(self):
        description = ('Command line interface for testing internet bandwidth using  speedtest.net.\n------------------------------------------------------------\n--------------\nhttps://github.com/sivel/speedtest-cli')
        parser = ArgParser(description=description)
        try:
            parser.add_argument = parser.add_option
        except AttributeError:
            pass
        parser.add_argument('--no-download', dest='download', default=True, action='store_const', const=False, help='Do not perform download test')
        parser.add_argument('--no-upload', dest='upload', default=True, action='store_const', const=False, help='Do not perform upload test')
        parser.add_argument('--single', default=False, action='store_true', help='Only use a single connection instead of multiple. This simulates a typical file transfer.')
        parser.add_argument('--bytes', dest='units', action='store_const', const=('byte', 8), default=('bit', 1), help='Display values in bytes instead of bits. Does not affect the image generated by --share, nor output from --json or --csv')
        parser.add_argument('--share', action='store_true', help='Generate and provide a URL to the speedtest.net share results image, not displayed with --csv')
        parser.add_argument('--simple', action='store_true', default=False, help='Suppress verbose output, only show basic information')
        parser.add_argument('--csv', action='store_true', default=False, help='Suppress verbose output, only show basic information in CSV format. Speeds listed in bit/s and not affected by --bytes')
        parser.add_argument('--csv-delimiter', default=',', type=PARSER_TYPE_STR, help='Single character delimiter to use in CSV output. Default ","')
        parser.add_argument('--csv-header', action='store_true', default=False, help='Print CSV headers')
        parser.add_argument('--json', action='store_true', default=False, help='Suppress verbose output, only show basic information in JSON format. Speeds listed in bit/s and not affected by --bytes')
        parser.add_argument('--list', action='store_true', help='Display a list of speedtest.net servers sorted by distance')
        parser.add_argument('--server', type=PARSER_TYPE_INT, action='append', help='Specify a server ID to test against. Can be supplied multiple times')
        parser.add_argument('--exclude', type=PARSER_TYPE_INT, action='append', help='Exclude a server from selection. Can be supplied multiple times')
        parser.add_argument('--mini', help='URL of the Speedtest Mini server')
        parser.add_argument('--source', help='Source IP address to bind to')
        parser.add_argument('--timeout', default=10, type=PARSER_TYPE_FLOAT, help='HTTP timeout in seconds. Default 10')
        parser.add_argument('--secure', action='store_true', help='Use HTTPS instead of HTTP when communicating with speedtest.net operated servers')
        parser.add_argument('--no-pre-allocate', dest='pre_allocate', action='store_const', default=True, const=False, help='Do not pre allocate upload data. Pre allocation is enabled by default to improve upload\nperformance. To support systems with insufficient memory, use this option to avoid a MemoryError')
        parser.add_argument('--version', action='store_true', help='Show the version number and exit')
        parser.add_argument('--debug', action='store_true', help=ARG_SUPPRESS, default=ARG_SUPPRESS)
        options = parser.parse_args()
        if isinstance(options, tuple):
            args = options[0]
        else:
            args = options
        return args
    
    def validate_optional_args(self, args):
        optional_args = {'json': ('json/simplejson python module', json), 'secure': ('SSL support', HTTPSConnection)}
        for arg, info in optional_args.items():
            if getattr(args, arg, False) and info[1] is None:
                print(SystemExit('%s is not installed. --%s is unavailable' % (info[0], arg)))
                sys.exit(0)
    
    def printer(self, string, quiet=False, debug=False, error=False, **kwargs):
        if debug and not DEBUG:
            return
        if debug:
            if sys.stdout.isatty():
                out = '\033[1;30mDEBUG: %s\033[0m' % string
            else:
                out = 'DEBUG: %s' % string
        else:
            out = string
        if error:
            kwargs['file'] = sys.stderr
        if not quiet:
            self._print(out, **kwargs)
    
    def shell(self):
        global DEBUG
        args = self.parse_args()
        if args.version:
            self.version()
        if not args.download and not args.upload:
            print(self.SpeedtestCLIError('Cannot supply both --no-download and --no-upload'))
            sys.exit(0)
        if len(args.csv_delimiter) != 1:
            print(self.SpeedtestCLIError('--csv-delimiter must be a single character'))
            sys.exit(0)
        if args.csv_header:
            self.csv_header(args.csv_delimiter)
        self.validate_optional_args(args)
        debug = getattr(args, 'debug', False)
        if debug == 'SUPPRESSHELP':
            debug = False
        if debug:
            DEBUG = True
        if args.simple or args.csv or args.json:
            quiet = True
        else:
            quiet = False
        if args.csv or args.json:
            machine_format = True
        else:
            machine_format = False
        if quiet or debug:
            callback = self.do_nothing
        else:
            callback = self.print_dots(0)
        self.printer('Retrieving speedtest.net configuration...', quiet)
        try:
            speedtest = self.Speedtest(source_address=args.source, timeout=args.timeout, secure=args.secure)
        except (self.ConfigRetrievalError,) + HTTP_ERRORS:
            self.printer('Cannot retrieve speedtest configuration', error=True)
            print(self.SpeedtestCLIError(self.get_exception()))
            sys.exit(0)
        if args.list:
            try:
                speedtest.get_servers()
            except (self.ServersRetrievalError,) + HTTP_ERRORS:
                self.printer('Cannot retrieve speedtest server list', error=True)
                print(self.SpeedtestCLIError(self.get_exception()))
                sys.exit(0)
            for _, servers in sorted(speedtest.servers.items()):
                for server in servers:
                    line = ('%(id)5s) %(sponsor)s (%(name)s, %(country)s) [%(d)0.2f km]' % server)
                    try:
                        self.printer(line)
                    except IOError:
                        e = self.get_exception()
                        if e.errno != errno.EPIPE:
                            sys.exit(0)
            sys.exit(0)
    
        self.printer('Testing from %(isp)s (%(ip)s)...' % speedtest.config['client'], quiet)
        if not args.mini:
            self.printer('Retrieving speedtest.net server list...', quiet)
            try:
                speedtest.get_servers(servers=args.server, exclude=args.exclude)
            except self.NoMatchedServers:
                print(self.SpeedtestCLIError('No matched servers: %s' % ', '.join('%s' % s for s in args.server)))
                sys.exit(0)
            except (self.ServersRetrievalError,) + HTTP_ERRORS:
                self.printer('Cannot retrieve speedtest server list', error=True)
                print(self.SpeedtestCLIError(self.get_exception()))
                sys.exit(0)
            except self.InvalidServerIDType:
                print(self.SpeedtestCLIError('%s is an invalid server type, must be an int'  % ', '.join('%s' % s for s in args.server)))
                sys.exit(0)
            if args.server and len(args.server) == 1:
                self.printer('Retrieving information for the selected server...', quiet)
            else:
                self.printer('Selecting best server based on ping...', quiet)
            speedtest.get_best_server()
        elif args.mini:
            speedtest.get_best_server(speedtest.set_mini_server(args.mini))
        results = speedtest.results
        self.printer('Hosted by %(sponsor)s (%(name)s) [%(d)0.2f km]: %(latency)s ms' % results.server, quiet)
        if args.download:
            self.printer('Testing download speed', quiet, end=('', '\n')[bool(debug)])
            speedtest.download(callback=callback, threads=(None, 1)[args.single])
            self.printer('Download: %0.2f M%s/s' % ((results.download / 1000.0 / 1000.0) / args.units[1], args.units[0]), quiet)
        else:
            self.printer('Skipping download test', quiet)
        if args.upload:
            self.printer('Testing upload speed', quiet, end=('', '\n')[bool(debug)])
            speedtest.upload(callback=callback, pre_allocate=args.pre_allocate, threads=(None, 1)[args.single])
            self.printer('Upload: %0.2f M%s/s' % ((results.upload / 1000.0 / 1000.0) / args.units[1], args.units[0]), quiet)
        else:
            self.printer('Skipping upload test', quiet)
        self.printer('Results:\n%r' % results.dict(), debug=True)
        if not args.simple and args.share:
            results.share()
        if args.simple:
            self.printer('Ping: %s ms\nDownload: %0.2f M%s/s\nUpload: %0.2f M%s/s' % (results.ping, (results.download / 1000.0 / 1000.0) / args.units[1], args.units[0], (results.upload / 1000.0 / 1000.0) / args.units[1], args.units[0]))
        elif args.csv:
            self.printer(results.csv(delimiter=args.csv_delimiter))
        elif args.json:
            self.printer(results.json())
        if args.share and not machine_format:
            self.printer('Share results: %s' % results.share())

    def __exit__(self, _, __, ___):
        pass

    def __enter__(self):
        try:
            self.shell()
        except KeyboardInterrupt:
            self.printer('\nCancelling...', error=True)
        except (self.SpeedtestException, SystemExit):
            e = self.get_exception()
            if getattr(e, 'code', 1) not in (0, 2):
                msg = '%s' % e
                if not msg:
                    msg = '%r' % e
                print(SystemExit('ERROR: %s' % msg))
                sys.exit(0)
        return ''

def main():
    with speedtest_cli() as speedtest:
        print(speedtest)

if __name__ == '__main__':
    main()