from flask import render_template, request, jsonify
from . import errors

@errors.errorhandler(401)
def page_unauthorized(e):
    return render_template('errors/401.html'), 401

@errors.errorhandler(403)
def page_forbidden(e):
    return render_template('errors/403.html'), 403

@errors.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@errors.app_errorhandler(401)
def page_unauthorized(e):
    print (request.accept_mimetypes.accept_json)
    print (request.accept_mimetypes.accept_html)
    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'unauthorized'})
        response.status_code = 401
        return response
    return render_template('errors/401.html'), 401

@errors.app_errorhandler(403)
def page_forbidden(e):
    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'forbidden'})
        response.status_code = 403
        return response
    return render_template('errors/403.html'), 403

@errors.app_errorhandler(404)
def page_not_found(e):
    if request.accept_mimetypes.accept_json and \
            not request.accept_mimetypes.accept_html:
        response = jsonify({'error': 'not found'})
        response.status_code = 404
        return response
    return render_template('errors/404.html'), 404

# @main.app_errorhandler(500)
# def internal_server_error(e):
#     if request.accept_mimetypes.accept_json and \
#             not request.accept_mimetypes.accept_html:
#         response = jsonify({'error': 'internal server error'})
#         response.status_code = 500
#         return response
#     return render_template('500.html'), 500
