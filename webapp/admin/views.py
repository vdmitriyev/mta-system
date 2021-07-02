
from flask import render_template, redirect, request, url_for, escape, current_app, Markup, abort
from flask_login import login_required, current_user

from . import admin
from .. import db
from .. models import Users
from .. main.views import get_user_data, container_status_to_html, email_to_name

from subprocess import Popen, TimeoutExpired, PIPE

ADMIN_UI_URL = 'adminView'

@admin.route('/', methods=['GET'])
@admin.route('/index', methods=['GET'])
@login_required
def viewAdminIndex():
    ''' Admin interface - redirection'''
    return redirect(url_for('.viewAdmin'))

@admin.route('/adminView', methods=['GET'])
@login_required
def viewAdmin():
    ''' Handles admin view'''

    current_app.logger.info(f'[i] Try to access admin UI. User id: {current_user.get_id()}')

    is_admin = False
    user_data = get_user_data(current_user.get_id())
    if user_data:
        for admin_email in current_app.config["SYSTEM_ADMINS"]:
            if admin_email == user_data['email']:
                is_admin = True
                break

    if is_admin:
        containers = []
        try:
            import docker
            client = docker.from_env()
            lst_containers = client.containers.list(all=True)
            for container in lst_containers:
                container_status = container_status_to_html(container.status)
                def format_docker_logs(logs_in):
                    ''' Formats provided logs from docker (as byte) into html '''
                    try:
                        return logs_in.decode().replace('\n', '<br>')
                    except Exception as ex:
                        current_app.logging.error(e, exc_info=True)
                        return f'[e] exception while formatting docker logs: {ex}'
                    return None

                containers.append({
                    'id'     : container.short_id,
                    'name'   : container.name,
                    'image'  : str(container.image.tags),
                    'status' : Markup(container_status),
                    'logs'   : Markup(format_docker_logs(container.logs(tail=20)))}
                    )
        except ImportError as ex:
            current_app.logger.error(f'[e] No module installed: docker. Exception {ex}')
        except OSError as ex:
            current_app.logger.error(f'[e] No access to docker. Exception {ex}')
        except Exception as ex:
            current_app.logger.error(f'[e] Another docker relevant exception. Exception {ex}', exc_info=True)

        cmd_mb_generate_bash = 'generateBashMetabase'
        cmd_or_generate_bash = 'generateBashOpenrefine'
        cmd_nifi_generate_bash = 'generateBashNifi'
        cmd_jhub_generate_bash = 'generateBashJupyterhub'

        cmd = escape(request.values.get('cmd', None))
        jh_user = escape(request.values.get('jh_user', None))
        current_app.logger.info(f'[i] Command for admin received: {cmd}')

        cmd_output = admin_generate_cmds(cmd, cmd_mb_generate_bash, cmd_or_generate_bash,
                                              cmd_nifi_generate_bash, cmd_jhub_generate_bash, jh_user)

        server_summary = admin_server_summary()

        return render_template('admin/admin_ui.html', urlMBGenerateBash = f'{ADMIN_UI_URL}?cmd={cmd_mb_generate_bash}',
                                                      urlORGenerateBash = f'{ADMIN_UI_URL}?cmd={cmd_or_generate_bash}',
                                                      urlNifiGenerateBash = f'{ADMIN_UI_URL}?cmd={cmd_nifi_generate_bash}',
                                                      urlJHubGenerateBash = f'{ADMIN_UI_URL}?cmd={cmd_jhub_generate_bash}',
                                                      cmdOutput = Markup(cmd_output),
                                                      containers = containers,
                                                      serverSummary = server_summary,
                                                      menu = 'admin')

    abort(403)

def admin_generate_cmds(cmd, cmd_mb_generate_bash, cmd_or_generate_bash,
                             cmd_nifi_generate_bash, cmd_jhub_generate_bash, jh_user):
    ''' Generates CMDs for admin UI'''

    cmd_output = ''

    # metabase bash commands
    if cmd == cmd_mb_generate_bash:

        bash_commands = []
        bash_cmd_tpl = ' python metabase_api.py -dp {docker_port} -f {fname} -l {lname} -e {email} -p {password}'
        results = db.session.query(Users).filter(Users.metabase_docker_port == None)\
                                            .order_by(Users.created_at.asc())\
                                            .all()
        for user in results:
            tokens = email_to_name(user.email)
            # need to identify docker port here
            _user_name = str(user.postgresql_db)
            new_docker_port = int(_user_name[_user_name.rfind('_')+1:]) + settings.METABASE_PORT_OFFSET

            new_cmd = bash_cmd_tpl.format(docker_port = new_docker_port,
                                            fname = tokens[0].title(),
                                            lname = tokens[1].title(),
                                            email = user.email,
                                            password = user.metabase_password
                                            )
            bash_commands.append(new_cmd)

        cmd_output = '-- <i>metabase commands</i> </br></br>'
        cmd_output = cmd_output + '</br>'.join(bash_commands)

    # openrefine bash commands
    if cmd == cmd_or_generate_bash:

        bash_commands = []
        bash_cmd_tpl = ' python openrefine_api.py -dp {docker_port} -u {user_name} -p {password}'
        results = db.session.query(Users).filter(Users.openrefine_docker_port == None)\
                                            .order_by(Users.created_at.asc())\
                                            .all()
        for user in results:

            # need to identify docker port here
            _user_name = str(user.openrefine_user)
            print (_user_name)
            new_docker_port = int(_user_name[_user_name.rfind('_')+1:]) + settings.OPENREFINE_PORT_OFFSET

            new_cmd = bash_cmd_tpl.format(docker_port = new_docker_port,
                                            user_name = _user_name,
                                            password = user.openrefine_password
                                            )
            bash_commands.append(new_cmd)

        cmd_output = '-- <i>openrefine commands</i> </br></br>'
        cmd_output = cmd_output + '</br>'.join(bash_commands)


    # nifi bash commands
    if cmd == cmd_nifi_generate_bash:

        bash_commands = []
        bash_cmd_tpl = ' python nifi_api.py -dp {docker_port} -u {user_name} -p {password}'
        results = db.session.query(Users).filter(Users.nifi_docker_port == None)\
                                            .order_by(Users.created_at.asc())\
                                            .all()
        for user in results:

            # need to identify docker port here
            _user_name = str(user.nifi_user)
            print (_user_name)
            new_docker_port = int(_user_name[_user_name.rfind('_')+1:]) + settings.NIFI_PORT_OFFSET

            new_cmd = bash_cmd_tpl.format(docker_port = new_docker_port,
                                          user_name = _user_name,
                                          password = user.nifi_password
                                          )
            bash_commands.append(new_cmd)

        cmd_output = '-- <i>nifi commands</i> </br></br>'
        cmd_output = cmd_output + '</br>'.join(bash_commands)

    # jupyterhub bash commands
    if cmd == cmd_jhub_generate_bash:

        bash_commands = []
        bash_cmd_tpl = '''# should be executed on VM, where the docker is running under SUDO / or has access to docker
docker exec jupyterhub-2020 /bin/sh -c 'adduser --disabled-password --gecos "" {user}'
docker exec jupyterhub-2020 /bin/bash -c "echo '{user}:{password}'|chpasswd"
docker exec jupyterhub-2020 /bin/bash -c "mkdir -p /home/{user}/notebooks/"
docker exec jupyterhub-2020 /bin/bash -c "cp -r /srv/jupyterhub/datasets/sentiment-data /home/{user}/notebooks/"
docker exec jupyterhub-2020 /bin/bash -c "chown  -R {user}:{user} /home/{user}/notebooks/"

sleep 2

'''

        results = db.session.query(Users).filter(Users.jupyterhub_created == False)\
                                         .order_by(Users.created_at.asc())\
                                         .all()
        for user in results:

            if jh_user is not None:
                if jh_user == user.jupyterhub_user:
                    new_cmd = bash_cmd_tpl.format(user = user.jupyterhub_user, password = user.jupyterhub_password)
                    error = False
                    for cmd in new_cmd.split('\n'):
                        try:
                            if not cmd.startswith('#'):
                                current_app.logger.info(f'[i] Execute cmd for JHub: {cmd}')
                                proc = Popen(cmd, shell = True, stdout = PIPE, stderr = PIPE, stdin = PIPE)
                                outs, errs = proc.communicate(timeout=10)
                        except TimeoutExpired as ex:
                            current_app.logger.error(f'[e] Timeout exception: {ex}', exc_info=True)
                            error = True

                    if not error:
                        db.session.query(Users)\
                                  .filter(Users.jupyterhub_user == jh_user)\
                                  .update({'jupyterhub_created' : True})
                        db.session.commit()

                    continue

            new_cmd = bash_cmd_tpl.format(user = user.jupyterhub_user, password = user.jupyterhub_password)
            bash_commands.append(new_cmd.replace('\n', '</br>\n'))
            urlJHubСreateUser = f'{ADMIN_UI_URL}?cmd={cmd_jhub_generate_bash}&jh_user={user.jupyterhub_user}'
            bash_commands.append(f'<a class="btn bg-warning" type="button" name="{cmd_jhub_generate_bash}" href="{urlJHubСreateUser}">Create user: <b>{user.jupyterhub_user}</b></a>')
            bash_commands.append('<hr width="80%">')

        cmd_output = '-- <i>jupyterhub commands</i> </br></br>'
        cmd_output = cmd_output + '</br>'.join(bash_commands)

    return cmd_output

def admin_server_summary():
    ''' Gets performance summary of the server '''

    summary = {}
    try:
        import docker
        client = docker.from_env()
        lst_containers = client.containers.list(all=True)
        summary['totalContainers'] = len(lst_containers)
        lst_containers_run = client.containers.list()
        summary['runningContainers'] = len(lst_containers_run)
        summary['exitedContainers'] = summary['totalContainers'] - summary['runningContainers']

        import psutil
        summary['cpuUsage'] = psutil.cpu_percent()
        # convert that object to a dictionary
        memory = dict(psutil.virtual_memory()._asdict())
        if 'total' in memory: summary['totalMemory'] = '{:10.0f}'.format(memory['total'] / (1024*1024))
        if 'used' in memory: summary['usedMemory'] = '{:10.0f}'.format(memory['used'] / (1024*1024))
        if 'available' in memory: summary['availableMemory'] = '{:10.0f}'.format(memory['available'] / (1024*1024))
        if 'percent' in memory: summary['usedMemoryPercent'] = memory['percent']

    except ImportError as ex:
        current_app.logger.error(f'[e] No module installed: docker. Exception {ex}')
    except OSError as ex:
        current_app.logger.error(f'[e] No access to docker. Exception {ex}')
    except Exception as ex:
        current_app.logger.error(f'[e] Another docker relevant exception. Exception {ex}', exc_info=True)

    return summary
