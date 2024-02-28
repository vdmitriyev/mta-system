## About

**mta-system** (**m**odular **t**eaching **a**ssistance **system**) was designed to help students to acquire new hands-on software experience. The solution was designed to be modular by design and to be hosted by a lecturer/faculty member for students.

## Dependencies

* Python 3.7+ 
    + Details in ```requirements/requirements.txt```
* Docker + Docker Compose

## Architecture

## Setup

### Create virtual environment for Python

* Create environment on Windows
    + Run ```scripts/cmdInitiateEnv.bat```
* Create environment on Ubuntu
    + Run ```scripts/initEnv.sh```

### Create configuration file

* Create ```.env``` file that will contain configuration parameters of the installation
    + Use the wizard script ```python init_config.py```
    + To create config file used commands: ```config``` or ```loadenv .env```
    + Parameters should be in the file ```.env-wizard```.
    + Change the name of the file to the desired version of deployment (e.g. ```.env```, ```.env-prod```, etc.)

## System UI

* User view. It is user by an user user to get access to the features of the system such as - services credentials, datasets imports, start/stop for services

![](./images/user-view.png)

* Admin view. It is used by an admin to monitor various parameters of a server - CPU usage, RAM usage, amount of containers running, logs, etc.

![](./images/admin-view.png)


## License

* Source Code - MIT
* Datasets - license is found directly inside the import module/dataset itself
