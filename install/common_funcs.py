from subprocess import Popen, PIPE, STDOUT
from datetime import datetime
from pathlib import Path

import mysql.connector
import logging
import toml
import sys
import re
import os

#######################################
#           PRETTY PRINTING           #
#######################################

def get_pattern(letter):
    patterns = {
        'A': [
            "  ###  ",
            " #   # ",
            "#     #",
            "#######",
            "#     #",
            "#     #",
            "#     #"
        ],
        'B': [
            "###### ",
            "#     #",
            "#     #",
            "###### ",
            "#     #",
            "#     #",
            "###### "
        ],
        'C': [
            " ##### ",
            "#     #",
            "#      ",
            "#      ",
            "#      ",
            "#     #",
            " ##### "
        ],
        'D': [
            "###### ",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            "###### "
        ],
        'E': [
            "#######",
            "#      ",
            "#      ",
            "###### ",
            "#      ",
            "#      ",
            "#######"
        ],
        'F': [
            "#######",
            "#      ",
            "#      ",
            "#####  ",
            "#      ",
            "#      ",
            "#      "
        ],
        'G': [
            " ##### ",
            "#     #",
            "#      ",
            "#  ### ",
            "#     #",
            "#     #",
            " ##### "
        ],
        'H': [
            "#     #",
            "#     #",
            "#     #",
            "#######",
            "#     #",
            "#     #",
            "#     #"
        ],
        'I': [
            "#######",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "#######"
        ],
        'J': [
            "#######",
            "    #  ",
            "    #  ",
            "    #  ",
            "    #  ",
            "#   #  ",
            " ###   "
        ],
        'K': [
            "#    # ",
            "#   #  ",
            "#  #   ",
            "###    ",
            "#  #   ",
            "#   #  ",
            "#    # "
        ],
        'L': [
            "#      ",
            "#      ",
            "#      ",
            "#      ",
            "#      ",
            "#      ",
            "#######"
        ],
        'M': [
            "#     #",
            "##   ##",
            "# # # #",
            "#  #  #",
            "#     #",
            "#     #",
            "#     #"
        ],
        'N': [
            "#     #",
            "##    #",
            "# #   #",
            "#  #  #",
            "#   # #",
            "#    ##",
            "#     #"
        ],
        'O': [
            " ##### ",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            " ##### "
        ],
        'P': [
            "###### ",
            "#     #",
            "#     #",
            "###### ",
            "#      ",
            "#      ",
            "#      "
        ],
        'Q': [
            " ##### ",
            "#     #",
            "#     #",
            "#  #  #",
            "#   ## ",
            "#    # ",
            " #### #"
        ],
        'R': [
            "###### ",
            "#     #",
            "#     #",
            "###### ",
            "#  #   ",
            "#   #  ",
            "#    # "
        ],
        'S': [
            " ######",
            "#      ",
            "#      ",
            " ##### ",
            "      #",
            "      #",
            "###### "
        ],
        'T': [
            "#######",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   "
        ],
        'U': [
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            " ##### "
        ],
        'V': [
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            " #   # ",
            "  # #  ",
            "   #   "
        ],
        'W': [
            "#     #",
            "#     #",
            "#     #",
            "#  #  #",
            "#  #  #",
            "#  #  #",
            " ## ## "
        ],
        'X': [
            "#     #",
            " #   # ",
            "  # #  ",
            "   #   ",
            "  # #  ",
            " #   # ",
            "#     #"
        ],
        'Y': [
            "#     #",
            " #   # ",
            "  # #  ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   "
        ],
        'Z': [
            "#######",
            "     # ",
            "    #  ",
            "   #   ",
            "  #    ",
            " #     ",
            "#######"
        ],
        '1': [
            "  ###  ",
            " # ##  ",
            "#   #  ",
            "    #  ",
            "    #  ",
            "    #  ",
            "#######"
        ],
        '2': [
            " ##### ",
            "#     #",
            "      #",
            " ##### ",
            "#      ",
            "#      ",
            "#######"
        ],
        '3': [
            " ##### ",
            "#     #",
            "      #",
            " ##### ",
            "      #",
            "#     #",
            " ##### "
        ],
        '4': [
            "#      ",
            "#    # ",
            "#    # ",
            "#######",
            "     # ",
            "     # ",
            "     # "
        ],
        '5': [
            "#######",
            "#      ",
            "#      ",
            " ##### ",
            "      #",
            "#     #",
            " ##### "
        ],
        '6': [
            " ##### ",
            "#      ",
            "#      ",
            " ##### ",
            "#     #",
            "#     #",
            " ##### "
        ],
        '7': [
            "#######",
            "     # ",
            "    #  ",
            "   #   ",
            "  #    ",
            " #     ",
            "#      "
        ],
        '8': [
            " ##### ",
            "#     #",
            "#     #",
            " ##### ",
            "#     #",
            "#     #",
            " ##### "
        ],
        '9': [
            " ##### ",
            "#     #",
            "#     #",
            " ######",
            "      #",
            "#     #",
            " ##### "
        ],
        '0': [
            " ##### ",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            "#     #",
            " ##### "
        ],
        '?': [
            " ####  ",
            "#    # ",
            "    #  ",
            "   #   ",
            "  #    ",
            "       ",
            "  #    "
        ],
        '!': [
            "  #    ",
            "  #    ",
            "  #    ",
            "  #    ",
            "  #    ",
            "       ",
            "  #    "
        ],
        ':': [
            "       ",
            "   #   ",
            "       ",
            "       ",
            "   #   ",
            "       ",
            "       "
        ],
        ';': [
            "   #   ",
            "   #   ",
            "       ",
            "       ",
            "   #   ",
            "   #   ",
            "   #   "
        ],
        '#': [
            " # # # ",
            " # # # ",
            "#######",
            " # # # ",
            "#######",
            " # # # ",
            " # # # "
        ],
        '@': [
            " ##### ",
            "#     #",
            "# ### #",
            "# # # #",
            "# # # #",
            "#     #",
            " ##### "
        ],
        '$': [
            "  ###  ",
            " #   # ",
            " ##### ",
            "  #   #",
            " ##### ",
            " #   # ",
            "  ###  "
        ],
        '%': [
            "#    # ",
            " #  #  ",
            "  ##   ",
            "  ##   ",
            " #  #  ",
            "#    # ",
            "       "
        ],
        '&': [
            "  ###  ",
            " #   # ",
            " #   # ",
            "  ###  ",
            " # # # ",
            "#  # # ",
            "  ## # "
        ],
        '^': [
            "   #   ",
            "  # #  ",
            " #   # ",
            "       ",
            "       ",
            "       ",
            "       "
        ],
        '*': [
            "       ",
            "  # #  ",
            "   #   ",
            "#######",
            "   #   ",
            "  # #  ",
            "       "
        ],
        '~': [
            "       ",
            "       ",
            "       ",
            " ### # ",
            "#     #",
            "       ",
            "       "
        ],
        '`': [
            "  #    ",
            "   #   ",
            "       ",
            "       ",
            "       ",
            "       ",
            "       "
        ],
        '|': [
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   ",
            "   #   "
        ],
        '\\': [
            "#      ",
            " #     ",
            "  #    ",
            "   #   ",
            "    #  ",
            "     # ",
            "      #"
        ],
        '/': [
            "      #",
            "     # ",
            "    #  ",
            "   #   ",
            "  #    ",
            " #     ",
            "#      "
        ],
        '-': [
            "       ",
            "       ",
            "       ",
            "#####  ",
            "       ",
            "       ",
            "       "
        ],
        '_': [
            "       ",
            "       ",
            "       ",
            "       ",
            "       ",
            "       ",
            "#######"
        ],
        '+': [
            "       ",
            "   #   ",
            "   #   ",
            " ##### ",
            "   #   ",
            "   #   ",
            "       "
        ],
        '=': [
            "       ",
            "       ",
            "#######",
            "       ",
            "#######",
            "       ",
            "       "
        ],
        '<': [
            "    #  ",
            "   #   ",
            "  #    ",
            " #     ",
            "  #    ",
            "   #   ",
            "    #  "
        ],
        '>': [
            " #     ",
            "  #    ",
            "   #   ",
            "    #  ",
            "   #   ",
            "  #    ",
            " #     "
        ],
        '[': [
            "  ###  ",
            "  #    ",
            "  #    ",
            "  #    ",
            "  #    ",
            "  #    ",
            "  ###  "
        ],
        ']': [
            "  ###  ",
            "    #  ",
            "    #  ",
            "    #  ",
            "    #  ",
            "    #  ",
            "  ###  "
        ],
        '{': [
            "   ##  ",
            "  #    ",
            "  #    ",
            " ##    ",
            "  #    ",
            "  #    ",
            "   ##  "
        ],
        '}': [
            "  ##   ",
            "    #  ",
            "    #  ",
            "    ## ",
            "    #  ",
            "    #  ",
            "  ##   "
        ],
        '(': [
            "   ##  ",
            "  #    ",
            " #     ",
            " #     ",
            " #     ",
            "  #    ",
            "   ##  "
        ],
        ')': [
            "  ##   ",
            "    #  ",
            "     # ",
            "     # ",
            "     # ",
            "    #  ",
            "  ##   "
        ],
        '{': [
            "   ##  ",
            "  #    ",
            "  #    ",
            " ##    ",
            "  #    ",
            "  #    ",
            "   ##  "
        ],
        '}': [
            "  ##   ",
            "    #  ",
            "    #  ",
            "    ## ",
            "    #  ",
            "    #  ",
            "  ##   "
        ],
        '<': [
            "    #  ",
            "   #   ",
            "  #    ",
            " #     ",
            "  #    ",
            "   #   ",
            "    #  "
        ],
        '>': [
            "  #    ",
            "   #   ",
            "    #  ",
            "     # ",
            "    #  ",
            "   #   ",
            "  #    "
        ],
        ',': [
            "       ",
            "       ",
            "       ",
            "       ",
            "   ##  ",
            "   ##  ",
            "  ##   "
        ],
        '.': [
            "       ",
            "       ",
            "       ",
            "       ",
            "       ",
            "       ",
            "   ##  "
        ],
        ':': [
            "   ##  ",
            "   ##  ",
            "       ",
            "       ",
            "   ##  ",
            "   ##  ",
            "       "
        ],
        ' ': [
            "       ",
            "       ",
            "       ",
            "       ",
            "       ",
            "       ",
            "       "
        ],
    }
    return patterns.get(letter, [""] * 7)


def print_pattern(word):
    patterns = [get_pattern(letter.upper()) for letter in word]
    max = 0
    for i in range(7):
        line = "".join([pattern[i] for pattern in patterns])
        print(line)
        if len(line) > max:
            max = len(line)
    return max


def print_decorated_title(title):
    decoration = '*' * (len(title) + 9)
    print(decoration)
    print("*" * 4 + "-" * (len(title) + 2) + "*" * 4)
    print("*  " + decorate_text(title) + " *")
    print("*" * 4 + "-" * (len(title) + 2) + "*" * 4)
    print(decoration)


def decorate_text(text):
    decorated_text = ''
    for char in text:
        if char.isalpha():
            decorated_text += char.upper() if char.islower() else char.lower()
        else:
            decorated_text += char
    return decorated_text


#######################################
#            GLOBAL FUNCS             #
#######################################

def get_app_paths(install_dir):
    return {
        "root": install_dir.parent,
        "updates": Path(os.path.join(install_dir,"updates")),
        "config_file": Path(os.path.join(install_dir.parent, "config.toml")),
        "template_config_file": Path(os.path.join(install_dir.parent, "config.toml.template")),
        "mysql_schema_file": Path(os.path.join(install_dir, "storages", "dbscheme.sql"))
    }

def get_logger(logging_dir, quiet=False):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if not quiet:
        if not os.path.isdir(logging_dir):
            pmask = os.umask(0)
            os.mkdir(logging_dir)
            os.umask(pmask)
        fh = logging.FileHandler(os.path.join(logging_dir,"setup.log"), 'a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    dh = logging.StreamHandler(sys.stdout)
    dh.setLevel(logging.DEBUG)
    dh.setFormatter(formatter)
    logger.addHandler(dh)

    return logger


#######################################
#           TOML HANDLING             #
#######################################


def load_toml_config(path):
    with open(path) as file:
        config = toml.loads(file.read())
    return config

def save_toml_config(config, path):
    with open(path,'w') as file:
        file.write(toml.dumps(config))

def merge_configs(base_config, merger):
    for k,v in base_config.items():
        if type(v) is dict:
            if k in merger:
                merge_configs(v, merger[k])
        elif type(v) in [str, int, float, bool, datetime]:
            if k in merger:
                base_config[k] = merger[k]
        else:
            raise Exception(f"Unable to merge configs containing values of type {type(v)}")
    for k,v in merger.items():
        if not k in base_config:
            base_config[k] = merger[k]
    return base_config




#######################################
#        MYSQL CREDENTIAL INPUT       #
#######################################


def is_valid_hostname(hostname):
    if hostname == "localhost":
        return True
    ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    if re.match(ip_pattern, hostname):
        return True
    return False


def get_mysql_credentials(host=None, port=None, user=None, password=None, database=None, no_confirm=False):
    print()

    host = os.environ.get('CARMAN_CRM_DB_HOST',host)
    while host is None:
        host = input("Enter you mysql host (default localhost):")
        if host == "" or host == "localhost":
            host = "127.0.0.1"
        if is_valid_hostname(host):
            break
        logger.warning(f"Invalid host: {host}")
        host = None

    port = os.environ.get('CARMAN_CRM_DB_PORT',port)
    while port is None:
        try:
            port = input("Enter you mysql port (default 3306):")
            if port == "":
                port = 3306
            port = int(port)
            if port >= 1024 and port <= 49151:
                break
            logger.warning(f"Invalid port (must be between 1024 and 49151)")
        except:
            logger.warning(f"Invalid port")
        port = None
    port = int(port)

    user = os.environ.get('CARMAN_CRM_DB_USER',user)
    if user is None:
        user = input("Enter your mysql user: ")
    password = os.environ.get('CARMAN_CRM_DB_PASSWORD',password)
    if password is None:
        password = input("Enter your mysql password:")
    database = os.environ.get('CARMAN_CRM_DB_DATABASE',database)
    if database is None:
        database = input("Enter your mysql database name:")

    if user == "":
        user = None
    if password == "":
        password == None

    if not no_confirm:
        print("\n\n"+"*"*20)
        print("Database: ")
        print(f"ip = {host}:{port}")
        print(f"user = {user}")
        print(f"password = {password}")
        print(f"database = {database}")
        rspn = input("confirm ? (y/*)").lower()
        if rspn == "y":
            return {"host":host,"port":port, "user":user, "password":password, "database": database}
    else:
        return {"host":host,"port":port, "user":user, "password":password, "database": database}
    return get_mysql_credentials()


def create_mysql_cmd(credentials):
    cmd = ["mysql","-s"]
    if credentials['host'] and not (credentials['host'] in ['127.0.0.1',"localhost"]):
        cmd.extend(["-h",credentials['host']])
    if credentials['port'] and credentials['port'] != 3306:
        cmd.extend(["-P",str(credentials['port'])])
    if credentials['user']:
        cmd.extend(["-u",credentials['user']])
    cmd.extend([credentials['database']])
    if credentials['password']:
        cmd.extend([f"-p{credentials['password']}"])
    return cmd


def execute_mysql_script(credentials, script_content):
    try:
        cmd = create_mysql_cmd(credentials)

        p = Popen(cmd, stdout=PIPE, stdin=PIPE, stderr=PIPE, text=True)
        stdout_data, stderr_data = p.communicate(input=script_content)
        no_password_warning = "\n".join(stderr_data.split('\n')[1:]).strip()
        if no_password_warning != "":
            LOGGER.warning("Mysql command execution returned error:")
            LOGGER.warning(f"{no_password_warning}")
    except:
        connexion = mysql.connector.connect(**credentials)
        cursor = connexion.cursor()
        cursor.execute(script_content, multi=True)
        try:
            cursor.close()
            connexion.close()
        except:
            pass
        no_password_warning = ""
    return no_password_warning == ""


#######################################
#             VIRTUAL ENV             #
#######################################


def detect_virtual_env(root_dir):
    print("\n")
    if os.path.isfile(os.path.join(root_dir,"venv","bin","activate")):
        print(f"A virtual env has been detected at {os.path.join(root_dir, 'venv')}.")
        rpsn = input("Are you using this virtual env ? (y/*)").lower()
        if rpsn == "y":
            return os.path.join(root_dir,"venv")
    rpsn = input("Using a virtual env is highly recommended. Are you using one ?").lower()
    if rpsn == "y":
        venv_path = None
        while venv_path is None:
            venv_path = input("Enter venv root path :")
            activation_file = os.path.join(venv_path,"bin","activate")
            if not os.path.isfile(activation_file):
                venv_path = None
                print(f"Cannot find venv activation file at {activation_file}")
                rpsn = input('Retry venv path input ? (y/*)').lower()
                if rpsn != "y":
                    break
        if venv_path is not None:
            return venv_path
    rpsn = input("Continue without using a venv ? (y/*)").lower()
    if rpsn == "y":
        return None
    return detect_virtual_env(root_dir)