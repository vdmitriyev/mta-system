import os
import json
import requests
import argparse
from bs4 import BeautifulSoup

class SupersetUser:

    def __init__(self, login, password, email):
        self.login = login
        self.password = password
        self.email = email

class SupersetAPIClient:

    def __init__(self, new_user, logger = None):
        self.new_user = new_user
        self.logger = logger
        self.load_env()
        self.start_session()

    def load_env(self):
        self.SUPERSET_BASE_URL = os.environ.get('SUPERSET_BASE_URL')
        self.SUPERSET_LOGIN = os.environ.get('SUPERSET_LOGIN')
        self.SUPERSET_PASSWORD = os.environ.get('SUPERSET_PASSWORD')

    def print_msg(self, msg):
        ''' Prints a message into console and log (if needed)'''

        if self.logger is not None:
            logger.info(msg)
        print(msg)

    def start_session(self, admin_login=None, admin_password=None):
        ''' Start HTTP session and get token '''

        if admin_login is None: admin_login = self.SUPERSET_LOGIN
        if admin_password is None: admin_password = self.SUPERSET_PASSWORD

        sess = requests.Session()

        # get auth together with csrf token
        res = sess.get(self.SUPERSET_BASE_URL + '/login/')
        signin = BeautifulSoup(res._content, 'html.parser')
        csrf_token = signin.find('input', id='csrf_token')['value']
        self.print_msg('The csrf_token found: {0}'.format(csrf_token))

        payload_auth = {'username': '{0}'.format(admin_login),
                        'password': '{0}'.format(admin_password)}
        payload_auth['csrf_token'] = csrf_token

        try:
            url = self.SUPERSET_BASE_URL + '/login/'
            res = sess.post(url, data=dict(payload_auth), timeout=60)
            self.print_msg('Status of getting csrf_token (login): {0}'.format(res.status_code))
            #signin = BeautifulSoup(res._content, 'html.parser')
            #print (signin)
            # csrf_token = signin.find('input', id='csrf_token')['value']
        except Exception as ex:
            self.print_msg('[e] Exception (POST): {0}'.format(ex))

        self.session = sess
        self.csrf_token = csrf_token

    def user_exists(self):
        ''' Checks if user exists or not '''

        url_list_users = '{baseURL}/users/api/read'.format(baseURL=self.SUPERSET_BASE_URL)
        headers = {}
        headers['X-CSRFToken'] = self.csrf_token
        response = self.session.get(url_list_users, headers=headers)
        print (response.status_code)
        response_json = json.loads(response._content)
        for _user in response_json['result']:
            if (_user['email'] == self.new_user.email or _user['username'] == self.new_user.login):
                return True
        return False

    def user_create(self):
        ''' Creates user, if possible'''

        url_new_user = '{baseURL}/users/api/create'.format(baseURL=self.SUPERSET_BASE_URL)

        full_name = self.new_user.email[0:self.new_user.email.find('@')]
        tokens = full_name.split('.')
        if len(tokens) < 2:
            tokens = ['Unknown', 'Unknown']

        payload_new_user = {}
        payload_new_user = {
                            'first_name': tokens[0].capitalize(), 'last_name': tokens[1].capitalize(),
                            'username': self.new_user.login, 'email': self.new_user.email,
                            'password': self.new_user.password, 'conf_password': self.new_user.password,
                            #'active': 'y', 'roles': [4, 7]
                            'active': 'y', 'roles': [3, 4, 7] # the maximum privileges, after admin
                            }

        headers = {}
        headers['X-CSRFToken'] = self.csrf_token
        #headers['Referer'] = res.url
        #headers['Content-Type'] = 'application/json'
        res_new_user = self.session.post(url_new_user, data=payload_new_user, headers=headers)

        if res_new_user.status_code == 500:
            res_json = json.loads(res_new_user._content)
            print (res_json)

            # TODO - New roles / Updates / Prove if exists

    def create_new_user(self):
        ''' Create a user in the superset '''

        #user_login, user_password, user_email, admin_login=None, admin_password=None, logger = None

        self.print_msg('Run method "new_user_superset"')
        self.print_msg('Main endpoint: {0}'.format(self.SUPERSET_BASE_URL))

        is_created = False

        # create new user
        if not self.user_exists():
            self.user_create()
        else:
            self.print_msg('User already exists: {0}'.format(self.new_user.login))

        return is_created

def main(user_login, user_password, user_email):
    print ('[i] Create superset user using a script approach')
    obj = SupersetAPIClient(SupersetUser(user_login, user_password, user_email))
    obj.create_new_user()

if __name__ == '__main__':
    # construct the argument parse and parse the arguments

    ap = argparse.ArgumentParser()
    ap.add_argument("-l", "--login", required=True, help="userEmail")
    ap.add_argument("-p", "--password", required=True, help="userPasword")
    ap.add_argument("-e", "--email", required=True, help="userEmail")

    args = vars(ap.parse_args())

    main(user_login = args['login'], user_password = args['password'], user_email = args['email'])
