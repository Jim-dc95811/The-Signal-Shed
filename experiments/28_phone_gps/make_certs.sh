#!/bin/sh
# Generate the Lookout Fleet CA + a box server cert. Run once on the setup computer
# (or fold into Lookout Manager). Usage: ./make_certs.sh [box-ip]  (default 192.168.8.1)
set -e
IP="${1:-192.168.8.1}"
mkdir -p certs
cat > certs/san.cnf <<EOF
[req]
distinguished_name=dn
x509_extensions=v3
prompt=no
[dn]
CN=The Lookout
[v3]
subjectAltName=@alt
[alt]
DNS.1=lookout.lan
DNS.2=thelookout.box
IP.1=${IP}
IP.2=127.0.0.1
EOF
# private CA — valid 10 years; its KEY never leaves the setup computer / box
openssl genrsa -out certs/lookout-ca.key 2048
openssl req -x509 -new -nodes -key certs/lookout-ca.key -sha256 -days 3650 \
  -subj "/CN=Lookout Fleet CA" -out certs/lookout-ca.crt
# box server cert signed by the CA — 825 days (iOS trust cap)
openssl genrsa -out certs/server.key 2048
openssl req -new -key certs/server.key -subj "/CN=The Lookout" -out certs/server.csr
openssl x509 -req -in certs/server.csr -CA certs/lookout-ca.crt -CAkey certs/lookout-ca.key \
  -CAcreateserial -days 825 -sha256 -extfile certs/san.cnf -extensions v3 -out certs/server.crt
echo "Done. Install on each device:  certs/lookout-ca.crt   (the box serves it at /ca)"
echo "Box uses:  certs/server.crt + certs/server.key"
