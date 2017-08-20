from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.parse


server_address = ('127.0.0.1', 8001)


class HTTPHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        qs = urllib.parse.parse_qs(self.path)
        challenge = qs['hub.challenge'][0]
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(bytes(challenge, 'utf8'))


# For some reason (maybe the re-binding of server_address that occurs in
# HTTPServer's super-class TCPServer's __init__?) this must come before the
# request to the WebSub server, as otherwise its callback attempt might
# encounter a TCP connection refusal (RST answer to SYN) when this program is
# re-run. The details are still unclear.
httpd = HTTPServer(server_address, HTTPHandler)

import urllib.request
import urllib.error
global server_address
url = 'http://127.0.0.1:8000'
data = urllib.parse.urlencode({
    'hub.mode': 'subscribe',
    'hub.callback': 'http://' + server_address[0] + ':' + str(server_address[1]),
    'hub.topic': 'http://baz.quux',
    'hub.lease_seconds': 23, 
    'secret': 'foo',
}).encode()
req = urllib.request.Request(url, data=data)
try:
    res = urllib.request.urlopen(req)
except urllib.error.HTTPError as e:
    print(e.read().decode())

print("SERVING", server_address)
httpd.serve_forever()
print('QUIT')
