import os

# MASTER_PASSWORD_REQUIRED = True
MASTER_PASSWORD = False
AUTHENTICATION_SOURCES = ["webserver", "internal"]
WEBSERVER_AUTO_CREATE_USER = True
WEBSERVER_REMOTE_USER = "X-Forwarded-User"

# nginx logs the users in (basic auth) and passes the name on in X-Forwarded-User.
# Since pgAdmin 9.x, pgAdmin reads this header only when both settings below are set.
WEBSERVER_REMOTE_USER_FROM_HEADER = True
# Peers that may send the header: the private networks of Docker, where nginx runs.
# pgAdmin listens on IPv6 and sees IPv4 peers as ::ffff:<ip>, so both forms are listed.
WEBSERVER_TRUSTED_PROXIES = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "::ffff:10.0.0.0/104",
    "::ffff:172.16.0.0/108",
    "::ffff:192.168.0.0/112",
]
# nginx also sends a shared secret (envs/pgadmin4-proxy.env). Other containers in the
# network do not know it, so they cannot log in as another user with the header.
WEBSERVER_SHARED_SECRET = os.environ.get("PGADMIN_WEBSERVER_SECRET") or None
WEBSERVER_SHARED_SECRET_HEADER = "X-Pgadmin-Webserver-Secret"
