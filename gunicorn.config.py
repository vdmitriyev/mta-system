# -*- encoding: utf-8 -*-

bind = 'unix:mta-system.sock'
workers = 2
timeout = 300
loglevel = 'debug'
capture_output = True
accesslog = 'gunicorn-access.log'
errorlog = 'gunicorn-error.log'
enable_stdio_inheritance = True
