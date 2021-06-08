import os
import time
import argparse
import requests
from dataclasses import dataclass
from passlib.apache import HtpasswdFile
from sys import platform

@dataclass
class UserDataNiFi:
    userName: str
    password: str

def create_user_and_docker_nifi(user_data, docker_port, seprated_auth_file=True):
    ''' Creates docker containers and super use inside for nifi'''

    if not isinstance(user_data, UserDataNiFi):
        print ('[e] Must be UserDataNiFi data type')
        return False

    is_errors = create_docker_container(docker_port)
    if not is_errors:
        print (f'[e] Status docker creation: {is_errors}')
        print ('[i] Trying anyway to create superuser')

    if not create_user_basic_auth(user_data, docker_port, seprated_auth_file):
        print ('[i] Basic auth user for nifi was NOT created successfully')
        return False
    else:
        print ('[i] Basic auth user for nifi was created successfully')

    return True

def create_docker_container(port):
    ''' Creates containers for nifi and runs on the port given '''

    if port is None:
        return False

    try:
        # creates nifi docker
        import docker
        client = docker.from_env()
        environment = {'NIFI_WEB_HTTP_HOST'         : '0.0.0.0',
                       'NIFI_WEB_HTTP_PORT'         : '8080',
                       'NIFI_WEB_PROXY_CONTEXT_PATH': f'/nifi/{port}/'
                      }
        res = client.containers.run(image = 'nifi-custom',
                                    detach=True,
                                    name = f'nifi-{port}',
                                    ports = {'8080/tcp': ('127.0.0.1', port)},
                                    environment = environment,
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

def create_user_basic_auth(user_data, docker_port, seprated_auth_file, logger = None):
    ''' Creates initial user in nifi '''

    # tries and wait until docker container really starts
    # for index, _ in enumerate(range(or_conf.DOCKER_TRY_COUNT)):
    #     print (f'[i] Sleep for {or_conf.DOCKER_TRY_SLEEP_SEC} seconds. Re-try number: {index}')
    #     time.sleep(or_conf.DOCKER_TRY_SLEEP_SEC)

    NGINX_BASIC_AUTH_FILE = os.getenv('NGINX_BASIC_AUTH_FILE') or '.htpasswd' 
    NGINX_BASIC_AUTH_DIR_ABSOLUTE = os.getenv('NGINX_BASIC_AUTH_DIR_ABSOLUTE') or '.'
    NGINX_BASIC_AUTH_DIR_RELATIVE = os.getenv('NGINX_BASIC_AUTH_DIR_RELATIVE') or '.'


    nginx_basic_auth_dir = NGINX_BASIC_AUTH_DIR_ABSOLUTE

    # use relative path for windows
    if platform == "win32":
        nginx_basic_auth_dir = NGINX_BASIC_AUTH_DIR_RELATIVE

    if not os.path.exists(nginx_basic_auth_dir):
        os.mkdir(nginx_basic_auth_dir)

    auth_file = os.path.join(nginx_basic_auth_dir, NGINX_BASIC_AUTH_FILE)
    if seprated_auth_file:
        auth_file = os.path.join(nginx_basic_auth_dir, f'{docker_port}{NGINX_BASIC_AUTH_FILE}')

    if not os.path.exists(auth_file):
        print (f'[i] Create HtpasswdFile (basic auth) file: {auth_file}')
        ht = HtpasswdFile(auth_file, new=True)
    else:
        print (f'[i] Edit HtpasswdFile (basic auth) file: {auth_file}')
        ht = HtpasswdFile(auth_file)

    user_exists = ht.set_password(user_data.userName, user_data.password)
    if user_exists:
        print (f'[i] Password for existing user was updated: {user_data.userName}')
    else:
        print (f'[i] New user was created: {user_data.userName}')
    ht.save()

    return True

def main(docker_port, user_name, password, nginx_config = None):
    ''' To run from command line '''

    print ('[i] Create nifi docker and nginx basic auth user a script approach')
    or_user = UserDataNiFi(user_name, password)
    create_user_and_docker_nifi(user_data = or_user, docker_port = docker_port)


if __name__ == '__main__':
    # construct the argument parse and parse the arguments

    ap = argparse.ArgumentParser()
    ap.add_argument("-dp", "--dockerport", required=True, help="Docker port")
    ap.add_argument("-u", "--username", required=True, help="User name")
    ap.add_argument("-p", "--password", required=True, help="Password")

    args = vars(ap.parse_args())

    main(docker_port = args['dockerport'],
         user_name = args['username'],
         password = args['password'],
         nginx_config = args['nginxconfig'])
