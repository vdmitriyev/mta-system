import os

def create_nginx_configs(htpasswd_folder = None):
    ''' Creates nginx config to separate users for basic http auth '''

    nifi_port_offset = os.environ.get('NIFI_PORT_OFFSET') or 6000
    max_users = os.environ.get('MAX_USERS_NGINX_GENERATE') or 50

    if htpasswd_folder is None:
        htpasswd_folder = '/opt/mta-system/nginx_htpasswd/'

    nifi_nignx_tmpl = '''
    location /nifi/{port}/ {{

        auth_basic "Restricted Content";
        auth_basic_user_file {htpasswd_folder}{port}.htpasswd;
        proxy_pass http://127.0.0.1:{port}/;
        proxy_redirect off;

        proxy_set_header   Host                 $host;
        proxy_set_header   X-Real-IP            $remote_addr;
        proxy_set_header   X-Forwarded-For      $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto    $scheme;
        proxy_set_header   X-Forwarded-User     $remote_user;
        proxy_set_header   Authorization        "";
        proxy_set_header   X-ProxyScheme        $scheme;
        proxy_set_header   X-ProxyHost          $server_name;
        proxy_set_header   X-ProxyPort          $server_port;
        proxy_set_header   X-ProxyContextPath   /nifi/{port}/;
    }}
    '''
    nginx_header = '''\n
    ################################################################
    # START: Configuration for separated basic auth of NiFi
    ################################################################\n
    '''

    nginx_footer = '''\n
    ################################################################
    # END: Configuration for separated basic auth of NiFi
    ################################################################\n
    '''

    nginx_file_part_config = 'nginx_part_nifi.config'
    with open(nginx_file_part_config, 'w') as _file:
        _file.write(nginx_header)
        for i in range(1, max_users+1):
            _file.write(nifi_nignx_tmpl.format(port = nifi_port_offset + i, htpasswd_folder = htpasswd_folder))
        _file.write(nginx_footer)

    print (f'[i] part of nging config in file: {nginx_file_part_config}')

if __name__ == '__main__':
    # construct the argument parse and parse the arguments
    create_nginx_configs()
