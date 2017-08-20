from http.server import BaseHTTPRequestHandler, HTTPServer


server_address = ('127.0.0.1', 8000)


class Server(HTTPServer):

    def __init__(self, cursor, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cursor = cursor


class HTTPHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        """Process (un-)subscription requests according to WebSub spec."""
        import urllib.parse
        import urllib.request
        import random, string, datetime
        global topics

        def validate_request(request):
            """Validate parameters of request according to WebSub spec."""
            import cgi

            def validate_url(url):
                """Return True if url is a valid URL, else False."""
                test = urllib.parse.urlparse(url)
                return False if '' in (test.scheme, test.netloc) else True

            # Ensure proper content type ("MUST have a Content-Type header of
            # application/x-www-form-urlencoded"). Ensure no wrong charset is
            # used ("MUST use UTF-8 as the document character encoding"), while
            # graciously assuming that lack of charset declaration in the
            # header means the proper one. 
            header = request.headers.get('content-type')
            parsed_header = cgi.parse_header(header)
            if not (type(parsed_header) == tuple and len(parsed_header) == 2):
                return 'No properly formed content-type header provided.'
            content_type, params = parsed_header
            expected_content_type = 'application/x-www-form-urlencoded'
            if not content_type == expected_content_type:
                return 'Wrong content-type, '\
                       'must be "%s".' % expected_content_type
            expected_charset = 'UTF-8'
            if 'charset' in params and \
                    params['charset'].upper() != expected_charset:
                return 'Invalid charset declared in content-type header, '\
                       'must be "%s".' % expected_charset

            # Ensure hub.callback, hub.mode, hub.topic are in request.
            header = request.headers.get('content-length')
            if not header.strip().isdigit():
                return 'No properly formed content-length header provided.'
            length = int(header)
            params = cgi.parse_qs(request.rfile.read(length))
            min_params = {b'hub.callback', b'hub.mode', b'hub.topic'}
            if not min_params == min_params & set(params):
                return 'Need all parameters hub.(callback|mode|topic).'

            # Ensure hub.mode is either "subscribe" or "unsubscribe".
            mode = params[b'hub.mode'][0].decode()
            if mode not in {'subscribe', 'unsubscribe'}:
                return 'hub.mode must be "subscribe" or "unsubscribe".'

            # Ensure hub.callback and hub.topic values validate as proper URLs.
            # "Hubs MUST always decode non-reserved characters for these URL
            # parameters".
            callback = urllib.parse.unquote(params[b'hub.callback'][0].
                                            decode())
            topic = urllib.parse.unquote(params[b'hub.topic'][0].decode())
            if (not validate_url(callback)) or (not validate_url(topic)):
                return 'Invalid topic or callback URL'

            # If hub.mode!="unsubscribe", ensure hub.lease_seconds is only
            # digits. ("MAY be present for unsubscription requests and MUST be
            # ignored by the hub in that case")
            lease_seconds = None
            if mode != 'unsubscribe' and b'hub.lease_seconds' in params:
                lease_seconds = params[b'hub.lease_seconds'][0].decode()
                if not lease_seconds.isdigit():
                    return 'hub.lease_seconds must be integer.'
                lease_seconds = int(lease_seconds)

            # Ensure any hub.secret is < 200 bytes. TODO: "This parameter
            # SHOULD only be specified when the request was made over HTTPS"
            secret = None
            if b'secret' in params:
                secret_bytes = params[b'secret'][0]
                if len(secret_bytes) >= 200:
                    secret = secret_bytes.decode()
                    return 'hub.secret must be less than 200 bytes in size'
            
            return callback, topic, mode, lease_seconds, secret

        def append_GET_params(url, dictionary):
            """Return as URL url with dictionary as GET parameters appended."""
            url = list(urllib.parse.urlparse(url))
            if url[2] is '':
                url[2] = '/'
            if url[4] is not '':
                url[4] = url[4] + '&'
            params = []
            for key in dictionary:
                key_encoded = urllib.parse.quote(key)
                val_encoded = urllib.parse.quote(str(dictionary[key]))
                params += [key_encoded + '=' + val_encoded]
            url[4] += '&'.join(params)
            return urllib.parse.urlunparse(url)

        # As lease seconds count "from the time the verification request was
        # made", we catch this as early as possible. TODO: Move below input
        # validation, use HTTP header to determine request datetime.
        now = datetime.datetime.utcnow()

        # Parse subscription/unsubscription data.
        result = validate_request(self)
        if type(result) == str:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(bytes(result, 'utf8'))
            return
        self.send_response(202)
        self.end_headers()
        callback, topic, mode, lease_seconds, secret = result
        lease_default = 10*60*60*24  # "10 days is a good default"
        if lease_seconds is None: lease_seconds = lease_default
        ends = now + datetime.timedelta(seconds = lease_seconds)

        # Validate subscription against available topics. 
        self.server.cursor.execute('SELECT id FROM topics WHERE url = ?',
                                   (topic,))
        result = self.server.cursor.fetchone()
        if result is None:
            url = append_GET_params(callback, {'hub.topic': topic,
                                               'hub.mode': 'denied',
                                               'hub.reason': 'not found'})
            req = urllib.request.Request(url)  # Default method is GET.
            urllib.request.urlopen(req)
            return
        topic_id = result[0]

        # Perform verification of intent.
        challenge_length = 100  # Arbitrary value, no recommendations by spec.
        challenge = ''.join([random.choice(string.ascii_letters) for
                             i in range(challenge_length)])
        url = append_GET_params(callback, {'hub.topic': topic,
                                           'hub.mode': mode,
                                           'hub.challenge': challenge,
                                           'hub.lease_seconds': lease_seconds})
        req = urllib.request.Request(url)  # Default method is GET.
        res = urllib.request.urlopen(req)
        code = res.getcode()
        if code == 404:
            return  # Subscriber disagrees.
        elif code < 200 or code > 299 or res.read() != challenge.encode():
            return  # Verification failed.

        # Enact request.
        self.server.cursor.execute('SELECT id FROM subscriptions WHERE '
                                   'topic = ? AND callback = ?',
                                   (topic_id, callback))
        result = self.server.cursor.fetchone()
        subscription_id = None
        if result is not None:
            subscription_id = result[0]
        if mode == 'unsubscribe':
            if subscription_id is not None:
                self.server.cursor.execute('DELETE FROM subscriptions '
                                           'WHERE id = ?', (subscription_id,))
        else:
            if subscription_id is None:
                self.server.cursor.execute('INSERT INTO subscriptions '
                                           '(topic, callback, secret, ends)'
                                           'VALUES (?, ?, ?, ?)',
                                           (topic_id, callback, secret, ends))
            else:
                self.server.cursor.execute('UPDATE subscriptions '
                                           'SET secret = ?, ends = ? '
                                           'WHERE id = ?',
                                           (secret, ends, subscription_id))
        self.server.cursor.connection.commit()

#from socketserver import ThreadingMixIn
#class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
#    """foo"""
#httpd = ThreadedHTTPServer(server_address, HTTPHandler)

db_file = 'db.sqlite'
import os.path
import sqlite3
create_new_DB = False
if not (os.path.isfile(db_file)):
    create_new_DB = True
conn = sqlite3.connect(db_file)
cursor = conn.cursor()
if create_new_DB:
    cursor.execute('CREATE TABLE topics ('
                   'id INTEGER PRIMARY KEY UNIQUE, '
                   'url TEXT UNIQUE)')
    cursor.execute('CREATE TABLE subscriptions ('
                   'id INTEGER PRIMARY KEY UNIQUE, '
                   'topic INTEGER, '
                   'callback TEXT UNIQUE, '
                   'secret TEXT, '
                   'ends TIMESTAMP, '
                   'FOREIGN KEY (topic) REFERENCES topics(id))')
    cursor.execute('INSERT INTO topics (url) VALUES (?)',
                   ('http://baz.quux',))
    cursor.connection.commit()

httpd = Server(cursor, server_address, HTTPHandler)
httpd.serve_forever()
