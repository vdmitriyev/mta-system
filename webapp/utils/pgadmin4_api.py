import os
import json
import requests
import argparse
from bs4 import BeautifulSoup

def print_msg(msg, logger=None):
    ''' Prints a message into console and log (if needed)'''

    if logger is not None: logger.info(msg)
    print (msg)

def new_user_pgadmin4(user_email, user_password, admin_email=None, admin_password=None, logger = None):
    ''' Create a user in the pgadmin4 '''

    PGADMIN4_BASE_URL = os.environ.get('PGADMIN4_BASE_URL')
    PGADMIN_EMAIL = os.environ.get('PGADMIN_EMAIL')
    PGADMIN_PASSWORD=  os.environ.get('PGADMIN_PASSWORD')

    print_msg('Run method "new_user_pgadmin4"', logger)

    is_created = False
    if admin_email is None: admin_email = PGADMIN_EMAIL
    if admin_password is None: admin_password = PGADMIN_PASSWORD

    print_msg('Endpoint: {0}'.format(PGADMIN4_BASE_URL), logger)

    with requests.Session() as sess:

        # get auth together with csrf token
        url_base = PGADMIN4_BASE_URL
        res = sess.get(url_base + '/login')
        signin = BeautifulSoup(res._content, 'html.parser')
        csrf_token = signin.find('input', id='csrf_token')['value']

        print_msg('The csrf_token found: {0}'.format(csrf_token), logger)

        payload_auth = {'email': '{0}'.format(admin_email),
                        'password': '{0}'.format(admin_password)}
        payload_auth['csrf_token'] = csrf_token

        try:
            res = sess.post(url_base + '/login', data=payload_auth, timeout=60)
            print_msg('Status of getting csrf_token: {0}'.format(res.status_code), logger)
        except Exception as ex:
            print_msg('[e] Exception (POST): {0}'.format(ex), logger)
        # create new user
        url_new_user = '{baseURL}/user_management/user/'.format(baseURL=url_base)
        #payload_new_user = {}
        payload_new_user = '{' + '"email":"{0}","active":true,"role":"2","newPassword":"{1}","confirmPassword":"{1}"'''.format(user_email, user_password) + '}'

        headers = {}
        headers['X-pgA-CSRFToken'] = csrf_token
        headers['Referer'] = res.url

        res_new_user = sess.post(url_new_user, data=payload_new_user, headers=headers)

        if res_new_user.status_code == 200:
            is_created = True
            print_msg('User in "pgadmin4" backend was created successfully.', logger)

        if res_new_user.status_code != 200:

            print_msg('Status of creating new user (non 200): {0}'.format(res_new_user.status_code), logger)

            # handle situation with password change
            if 'UNIQUE constraint failed' in res_new_user.text:
                # get all users
                url_users = '{baseURL}/user_management/user/'.format(baseURL=url_base)
                res_users = sess.get(url_users, headers=headers)
                json_content = json.loads(res_users.text)
                found_user = None
                for value in json_content:
                    if (value['email'] == user_email):
                        found_user = value
                        break

                if found_user is not None:
                    user_id = found_user['id']
                    payload_new_password = '"id":{id},"newPassword":"{password}","confirmPassword":"{password}"'.format(id = user_id, password = user_password)
                    payload_new_password = '{' + payload_new_password + '}'

                    headers = {}
                    headers['X-pgA-CSRFToken'] = csrf_token
                    headers['Referer'] = res.url
                    res_new_password = sess.put(url_new_user + str(user_id), data=payload_new_password, headers=headers)
                    print_msg('New password operation response code: {0}. Text: {1}'.format(res_new_password.status_code, res_new_password.text), logger)
                    is_created = True
                else:
                    print_msg('Password is not changed, the user "{0}"was not found.'.format(user_email), logger)
                    is_created = False
            else:
                print_msg('Don not know how to handle following error.', logger)
                print_msg('Response body: \n {0}'.format(res_new_user._content), logger)
                is_created = False

    return is_created

def main(user_email, user_password):
    print ('[i] Create pgadmin4 user using a script approach')
    new_user_pgadmin4(user_email, user_password)

if __name__ == '__main__':
    # construct the argument parse and parse the arguments

    ap = argparse.ArgumentParser()
    ap.add_argument("-e", "--email", required=True, help="userEmail")
    ap.add_argument("-p", "--password", required=True, help="userPasword")

    args = vars(ap.parse_args())

    main(user_email = args['email'], user_password = args['password'])
