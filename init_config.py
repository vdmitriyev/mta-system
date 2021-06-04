import os
import sys
import codecs
from dotenv import load_dotenv

from pypsi.shell import Shell
from pypsi.core import Command
from pypsi.commands.exit import ExitCommand
from pypsi.commands.help import HelpCommand
from pypsi.plugins.variable import VariablePlugin
from pypsi import wizard as wiz
from pypsi.ansi import AnsiCodes

FNAME_ENV_WIZARD = '.env-wizard'

class WizardConfig(Command):
    ''' Command to launch a configuration wizard. '''

    def __init__(self, name='config', **kwargs):
        super().__init__(name=name, **kwargs)

    def run(self, shell, args):
        cw = create_wizard_steps()
        ns = cw.run(shell)
        if ns:
            _dict = ns.__dict__
            cw_steps = cw.__dict__['steps']
            print (f'\nConfigurations to be saved: \n')
            with codecs.open(FNAME_ENV_WIZARD, 'w', 'utf-8') as _file:
                for item in cw_steps:
                    _file.write(f'\n#{item.name}\n')
                    _file.write(f'{item.id} = \'{_dict[item.id]}\'\n')
                    print(f'{item.id} = \'{_dict[item.id]}\'')
            print (f'\nCheck the following file with your ".env" configurations: {FNAME_ENV_WIZARD}\n')
        else:
            pass
        return 0

class WizardLoadEnv(WizardConfig):
    ''' Command to load .env file for the configuration wizard. '''

    def __init__(self, name='loadenv', **kwargs):
        super().__init__(name=name, **kwargs)

    def run(self, shell, args):
        env_file = FNAME_ENV_WIZARD
        if len(args) > 0: env_file = args[0]
        print(f'\nLoads environmental variables for the config from the file: {env_file}\n')
        load_envs(env_file = env_file)
        super().run(shell, args)

class ConfigShell(Shell):
    ''' Ran shell.'''

    wizard_config = WizardConfig()
    wizard_load   = WizardLoadEnv()
    exit_cmd = ExitCommand()
    help_cmd = HelpCommand()
    var_plugin = VariablePlugin(case_sensitive=False, env=False)

    def __init__(self):
        super().__init__()

        self.prompt = "{gray}[$time]{r} {cyan}mta-system{r} {green})>{r} ".format(
            gray=AnsiCodes.gray.prompt(), r=AnsiCodes.reset.prompt(),
            cyan=AnsiCodes.cyan.prompt(), green=AnsiCodes.green.prompt()
        )

    def on_cmdloop_begin(self):
        print(AnsiCodes.clear_screen)
        print (f'''\nStart your configuration by typing "config" command.
Entered configuration values will be saved in the file: {FNAME_ENV_WIZARD}\n''')

    def help_cmdout(self):
        print("this is the help message for the cmdout command")

    def do_cmdout(self, args):
        print("do_cmdout(", args, ")")
        return 0

def load_envs(env_file = None):
    ''' Loads environmental variables from the file'''

    basedir = os.path.abspath(os.path.dirname(__file__))
    if env_file is not None:
        if os.path.exists(env_file):
            load_dotenv(os.path.join(env_file))
        else:
            print (f'Give file with environmental variables does not exist: {env_file}')
            load_dotenv(os.path.join(basedir, FNAME_ENV_WIZARD))
    else:
        load_dotenv(os.path.join(basedir, FNAME_ENV_WIZARD))

def random_string(size=30):
    import random, string
    return "".join(random.choice(string.ascii_letters + string.digits) for i in range(size))

def create_wizard_steps():

    config_wizard = wiz.PromptWizard(
        name="Configuration Manager",
        description="This wizard will guide you through the configuration steps required for the system start",
        # The list of input questions/request for the user
        steps=(
            wiz.WizardStep(
                id="FLASK_SECRET_KEY",# ID where the value will be stored
                # Display name
                name="{green}Key used by flask (FLASK_SECRET_KEY){r}".format(green=AnsiCodes.green.prompt(),
                                                                             r=AnsiCodes.reset.prompt()),
                help="Should be unique to your application", # Help message
                default=os.environ.get('FLASK_SECRET_KEY') or random_string(40) # Default value
            ),
            wiz.WizardStep(
                id='HASH_KEY_HIDDEN',
                name="Key for further hashes (HASH_KEY_HIDDEN)",
                help="Key used by the systems other hashes",
                default=os.environ.get('HASH_KEY_HIDDEN') or random_string(40)
            ),
            wiz.WizardStep(
                id='HASH_KEY_LINKS',
                name="Key to hash links (HASH_KEY_LINKS)",
                help="Key used by the systems to hash links",
                default=os.environ.get('HASH_KEY_LINKS') or random_string(40)
            ),
            wiz.WizardStep(
                id='COURSE_SECURITY_CODE',
                name="Registration security code (COURSE_SECURITY_CODE)",
                help="Security code used by the registration",
                default=os.environ.get('COURSE_SECURITY_CODE') or 'COURSECODE'
            ),
            wiz.WizardStep(
                id='COURSE_NAME_TITLE',
                name="Name used in a Web UI (COURSE_NAME_TITLE)",
                help="COURSE_NAME_TITLE",
                default=os.environ.get('COURSE_NAME_TITLE') or 'COURSETITLE'
            ),
            wiz.WizardStep(
                id='SERVER_FQDN',
                name="Full name the server (SERVER_FQDN)",
                help="The name is used further to configura Nginx and anble web access of the system",
                default=os.environ.get('SERVER_FQDN') or 'localhost'
            ),
            wiz.WizardStep(
                id='SYSTEM_ADMINS',
                name="List of system admins (SYSTEM_ADMINS)",
                help="SYSTEM_ADMINS - must be separated by ';'",
                default=os.environ.get('SYSTEM_ADMINS') or 'admin@localhost'
            ),

            # steps database to store users
            wiz.WizardStep(
                id='MTASBACKEND_DB_HOST',
                name="Database to store users - host name",
                help="Database to store users",
                default=os.environ.get('MTASBACKEND_DB_HOST') or 'localhost'
            ),
            wiz.WizardStep(
                id='MTASBACKEND_DB_HOST_PORT',
                name="Database to store users - host port",
                help="Database to store users",
                default=os.environ.get('MTASBACKEND_DB_HOST_PORT') or  '5431'
            ),
            wiz.WizardStep(
                id='MTASBACKEND_DB_NAME',
                name="Database to store users - database name",
                help="Database to store users",
                default=os.environ.get('MTASBACKEND_DB_NAME') or 'backend_db'
            ),
            wiz.WizardStep(
                id='MTASBACKEND_DB_USER',
                name="Database to store users - database user name",
                help="Database to store users",
                default=os.environ.get('MTASBACKEND_DB_USER') or f'db_user_{random_string(10)}'
            ),
            wiz.WizardStep(
                id='MTASBACKEND_DB_USER_PASSWORD',
                name="Database to store users - database user password",
                help="Database to store users",
                default=os.environ.get('MTASBACKEND_DB_USER_PASSWORD') or random_string(12)
            ),
            # steps to configure e-mail
             wiz.WizardStep(
                id='MAIL_SERVER',
                name="E-Mail for communication - server",
                help="E-Mail for communication",
                default=os.environ.get('MAIL_SERVER') or 'localhost'
            ),
            wiz.WizardStep(
                id='MAIL_PORT',
                name="E-Mail for communication - port",
                help="E-Mail for communication",
                default=os.environ.get('MAIL_PORT') or '587'
            ),
             wiz.WizardStep(
                id='MAIL_USERNAME',
                name="E-Mail for communication - user",
                help="E-Mail for communication",
                default=os.environ.get('MAIL_USERNAME') or f'EMAIL_USER_{random_string(4)}'
            ),
            wiz.WizardStep(
                id='MAIL_PASSWORD',
                name="E-Mail for communication - password",
                help="E-Mail for communication",
                default=os.environ.get('MAIL_PASSWORD') or random_string(12)
            ),
            wiz.WizardStep(
                id='MAIL_DEFAULT_SENDER',
                name="E-Mail for communication - default sender",
                help="E-Mail for communication",
                default=os.environ.get('MAIL_DEFAULT_SENDER') or 'admin@localhost'
            ),
            wiz.WizardStep(
                id='MAIL_ADMIN_NOTIFICATIONS',
                name="E-Mail for communication - admin e-mail for notifications",
                help="E-Mail for communication",
                default=os.environ.get('MAIL_ADMIN_NOTIFICATIONS') or 'admin@localhost'
            ),

            # steps database to store users data
            wiz.WizardStep(
                id='POSTGRESQL_DB_HOST',
                name="Database to store data - host name",
                help="Database to store data",
                default=os.environ.get('POSTGRESQL_DB_HOST') or 'localhost'
            ),
            wiz.WizardStep(
                id='POSTGRESQL_DB_HOST_PORT',
                name="Database to store data - host port",
                help="Database to store data",
                default=os.environ.get('POSTGRESQL_DB_HOST_PORT') or '5432'
            ),
            wiz.WizardStep(
                id='POSTGRESQL_DB_NAME',
                name="Database to store data - database name",
                help="Database to store data",
                default=os.environ.get('POSTGRESQL_DB_NAME') or 'postgres'
            ),
            wiz.WizardStep(
                id='MTASBACKEND_DB_USER',
                name="Database to store data - database user name",
                help="Database to store data",
                default=os.environ.get('MTASBACKEND_DB_USER') or 'postgres'
            ),
            wiz.WizardStep(
                id='POSTGRESQL_ADMIN_PASSWORD',
                name="Database to store data - database user password",
                help="Database to store data",
                default=os.environ.get('POSTGRESQL_ADMIN_PASSWORD') or random_string(12)
            ),

            # steps database to store demo data
            wiz.WizardStep(
                id='POSTGRESQL_DEMO_DB',
                name="Database to store DEMO data - database name",
                help="Database to store DEMO data",
                default=os.environ.get('POSTGRESQL_DEMO_DB') or 'db_demo'
            ),
            wiz.WizardStep(
                id='POSTGRESQL_DEMO_USER',
                name="Database to store DEMO data - database user name",
                help="Database to store DEMO data",
                default=os.environ.get('POSTGRESQL_DEMO_USER') or 'db_demo_user'
            ),
            wiz.WizardStep(
                id='POSTGRESQL_DEMO_PASSWORD',
                name="Database to store DEMO data - database user password",
                help="Database to store DEMO data",
                default=os.environ.get('POSTGRESQL_DEMO_PASSWORD') or random_string(12)
            ),

            # steps PGADmin4
            wiz.WizardStep(
                id='PGADMIN4_BASE_URL',
                name="Link to pgadmin4",
                help="Link to pgadmin4",
                default=os.environ.get('PGADMIN4_BASE_URL') or 'localhost:5050'
            ),
            wiz.WizardStep(
                id='PGADMIN_EMAIL',
                name="Admin e-mail of PGAdmin4",
                help="Admin e-mail of PGAdmin4",
                default=os.environ.get('PGADMIN_EMAIL') or 'pgadmin4@localhost'
            ),
            wiz.WizardStep(
                id='PGADMIN_PASSWORD',
                name="Admin e-mail password of PGAdmin4",
                help="Admin e-mail password of PGAdmin4",
                default=os.environ.get('PGADMIN_PASSWORD') or random_string(12)
            ),

            # steps superset
            wiz.WizardStep(
                id='SUPERSET_BASE_URL',
                name="Link to Apache Superset",
                help="Link to Apache Superset",
                default=os.environ.get('SUPERSET_BASE_URL') or 'localhost:8089'
            ),
            wiz.WizardStep(
                id='SUPERSET_LOGIN',
                name="Admin account of Apache Superset - login",
                help="Admin account of Apache Superset - login",
                default=os.environ.get('SUPERSET_LOGIN') or 'admin'
            ),
            wiz.WizardStep(
                id='SUPERSET_PASSWORD',
                name="Admin account of Apache Superset - password",
                help="Admin account of Apache Superset - password",
                default=os.environ.get('SUPERSET_PASSWORD') or random_string(12)
            ),

            # steps metabase
            wiz.WizardStep(
                id='METABASE_BASE_URL',
                name="Link to metabse config in the nginx",
                help="Link to metabse config in the nginx",
                default=os.environ.get('METABASE_BASE_URL') or 'localhost/metabase/'
            ),
            wiz.WizardStep(
                id='METABASE_TRY_COUNT',
                name="Try counts to wait for the docker container to start",
                help="Try counts to wait for the docker container to start",
                default=4
            ),
            wiz.WizardStep(
                id='METABASE_TRY_SLEEP_SEC',
                name="Sleep time in secords between attempts",
                help="Sleep time in secords between attempts",
                default=30
            ),

            # steps openrefine
            wiz.WizardStep(
                id='OPENREFINE_BASE_URL',
                name="Link to OpenRefine config in the nginx",
                help="Link to OpenRefine config in the nginx",
                default=os.environ.get('OPENREFINE_BASE_URL') or 'localhost/openrefine/'
            ),

            # steps nginx
            wiz.WizardStep(
                id='NGINX_BASIC_AUTH_DIR_ABSOLUTE',
                name="Absolute path to Basic Auth configuration file for Nginx",
                help="Absolute path to Basic Auth configuration file for Nginx",
                default=os.environ.get('NGINX_BASIC_AUTH_DIR_ABSOLUTE') or '/opt/mta-system/nginx_htpasswd'
            ),
            wiz.WizardStep(
                id='NGINX_BASIC_AUTH_DIR_RELATIVE',
                name="Relative path to Basic Auth configuration file for Nginx",
                help="Relative path to Basic Auth configuration file for Nginx",
                default=os.environ.get('NGINX_BASIC_AUTH_DIR_RELATIVE') or '../../nginx_htpasswd'
            ),
            wiz.WizardStep(
                id='NGINX_BASIC_AUTH_FILE',
                name="File name of the Basic Auth configuration file for Nginx",
                help="File name of the Basic Auth configuration file for Nginx",
                default=os.environ.get('NGINX_BASIC_AUTH_FILE') or '.htpasswd'
            ),
        )
    )

    return config_wizard

if __name__ == '__main__':
    shell = ConfigShell()
    rc = shell.cmdloop()
    sys.exit(rc)
