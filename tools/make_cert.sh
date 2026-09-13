#!/usr/bin/env sh
# Self-signed certificate so phones can use camera / motion APIs over the LAN.
# Usage: sh tools/make_cert.sh   ->  then:  python main.py --ssl-cert cert.pem --ssl-key key.pem
# Phones will warn about the certificate once; accept it to continue.
set -e
IP=$(python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('10.255.255.255',1));print(s.getsockname()[0])" 2>/dev/null || echo 127.0.0.1)
openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem -days 30 \
  -subj "/CN=greenbuilding" -addext "subjectAltName=IP:$IP,IP:127.0.0.1,DNS:localhost"
echo "wrote cert.pem / key.pem for https://$IP"
