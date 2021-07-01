import os
import time
import argparse
import requests
from dataclasses import dataclass

@dataclass
class UserDataMetabase:
    fname: str
    lname: str
    email: str
    password: str

def create_user_and_docker(user_data, docker_port):
    ''' Creates docker containers and super use inside for metabase'''

    if not isinstance(user_data, UserDataMetabase):
        print ('[e] Must be UserDataMetabase data type')
        return False

    is_errors = create_docker_container(docker_port)
    if not is_errors:
        print (f'[e] Status docker creation: {is_errors}')
        print ('[i] Trying anyway to create superuser')

    if not run_create_user(user_data, docker_port):
        return False
    return True

def create_docker_container(port):
    ''' Creates containers for metabase and runs on the port given '''

    if port is None:
        return False

    try:
        # creates metabase docker
        import docker
        client = docker.from_env()
        res = client.containers.run(image = 'metabase/metabase',
                                    detach=True,
                                    name = f'metabase-{port}',
                                    ports = {'3000/tcp': ('127.0.0.1', port)},
                                    restart_policy = {"Name": "unless-stopped", "MaximumRetryCount": 0}
                                    )
        print (f'[i] Created container with id: {res.short_id}')
    except ImportError as ex:
        print(f'[e] No module installed: docker. Exception {ex}')
        return False
    except OSError as ex:
        print(f'[e] No access to docker. Exception {ex}')
        return False

    return True

def run_create_user(user_data, port):
    ''' Creates user inside started container '''
    METABASE_BASE_URL = os.environ.get('METABASE_BASE_URL') or 'localhost'
    METABASE_TRY_COUNT = os.environ.get('METABASE_TRY_COUNT') or 3
    METABASE_TRY_SLEEP_SEC = os.environ.get('METABASE_TRY_SLEEP_SEC') or 30

    base_url = METABASE_BASE_URL + str(port)
    setup_token = None

    # tries and wait until docker container really starts
    for index, _ in enumerate(range(int(METABASE_TRY_COUNT))):
        print (f'[i] Sleep for {METABASE_TRY_SLEEP_SEC} seconds. Re-try number: {index}')
        time.sleep(int(METABASE_TRY_SLEEP_SEC))
        setup_token = get_setup_token(base_url)
        if setup_token is not None:
            break

    if setup_token is not None:
        print (f'[i] Found setup-token: {setup_token}')
        if create_initialuser(base_url, user_data, setup_token):
            print ('[i] Initial user / superuser in metabase was created successfully')
            return True
        else:
            print ('[i] Initial user / superuser in metabase was NOT created')
    else:
        print ('[e] no "setup-token" found')

    return False

def get_setup_token(base_url):
    ''' Gets setup-token '''
    try:
        request_url = base_url + '/api/session/properties'
        res = requests.get(request_url)
        print (f'[i] Response status: {res.status_code}')
        json_data = res.json()
        return json_data['setup-token']
    except Exception as ex:
        print('[e] Exception (GET): {0}'.format(ex))
        return None

def create_initialuser(base_url, user_data, setup_token, logger = None):
    ''' Creates initial user in metabase '''

    url = base_url + '/api/setup'
    payload_setup = {}
    payload_setup['token'] = setup_token
    payload_setup['prefs'] = {}
    payload_setup['prefs']['site_name'] = "course"
    payload_setup['prefs']['site_locale'] = 'en'
    payload_setup['prefs']['allow_tracking'] = 'false'
    payload_setup['database'] = ""
    payload_setup['user'] = {}
    payload_setup['user']['first_name'] = user_data.fname
    payload_setup['user']['last_name'] = user_data.lname
    payload_setup['user']['email'] = user_data.email
    payload_setup['user']['password'] = user_data.password
    payload_setup['user']['site_name'] = 'Teaching Course'

    try:
        res = requests.post(url, json=payload_setup, timeout=60)
        print (f'[i] Response status: {res.status_code}')
        if res.status_code == 200:
            return True
        else:
            print (f'[i] Response content: {res.content}')
            print (payload_setup)

    except Exception as ex:
        print('[e] Exception (POST): {0}'.format(ex))

    return False

def main(docker_port, fname, lname, email, password):
    ''' To test from command line '''
    print ('[i] Create metabase docker and user inside it using a script approach')
    mb_user = UserDataMetabase(fname, lname, email, password)
    create_user_and_docker(user_data = mb_user, docker_port = docker_port)

if __name__ == '__main__':
    # construct the argument parse and parse the arguments

    ap = argparse.ArgumentParser()
    ap.add_argument("-dp", "--dockerport", required=True, help="Docker port")
    ap.add_argument("-f", "--fname", required=True, help="First name")
    ap.add_argument("-l", "--lname", required=True, help="Last name")
    ap.add_argument("-e", "--email", required=True, help="email")
    ap.add_argument("-p", "--password", required=True, help="password")

    args = vars(ap.parse_args())

    main(docker_port = args['dockerport'],
         fname = args['fname'],
         lname = args['lname'],
         email = args['email'],
         password = args['password'])
