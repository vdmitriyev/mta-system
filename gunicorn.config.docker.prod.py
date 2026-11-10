# -*- encoding: utf-8 -*-

bind = "0.0.0.0:5151"
workers = 4
threads = 2
timeout = 300
# loglevel = 'debug'
loglevel = "info"
capture_output = True
enable_stdio_inheritance = True
# folder for logs should exist
accesslog = ".logs/gunicorn-access.log"
errorlog = ".logs/gunicorn-error.log"
