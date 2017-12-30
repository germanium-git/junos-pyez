import json
import argparse
import sys
import yaml
import getpass
import smtplib
import datetime
import os
from termcolor import cprint
from jnpr.junos import Device
from jnpr.junos.utils.config import Config
from jnpr.junos.exception import ConnectError
from jnpr.junos.exception import ConnectAuthError
from jnpr.junos.exception import LockError
from jnpr.junos.exception import UnlockError
from jnpr.junos.exception import ConfigLoadError
from jnpr.junos.exception import CommitError
#from jnpr.junos.exception import RpcError
from ansi2html import Ansi2HTMLConverter
from jinja2 import Template
from configobj import ConfigObj

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
#from email.mime.base import MIMEBase
from email.utils import formatdate


base_path = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_path, "j_settings.cfg")

if os.path.exists(config_path):
    cfg = ConfigObj(config_path)
    cfg_dict = cfg.dict()
else:
    print("Config not found! Exiting!")
    sys.exit(1)      
    
INVENTORY_FOLDER = cfg_dict["general"]["INVENTORY_FOLDER"]
OUTPUT_PATH = cfg_dict["general"]["OUTPUT_PATH"]
SMTP_SERVER = cfg_dict["smtp"]["SMTP_SERVER"]
SMTP_PORT = cfg_dict["smtp"]["SMTP_PORT"]
from_addr = cfg_dict["smtp"]["FROM"]

if "SMTP_USER" in cfg_dict["smtp"].keys():
    user = cfg_dict["smtp"]["SMTP_USER"]
else:
    user = None

if "SMTP_PASSWORD" in cfg_dict["smtp"].keys():
    password = cfg_dict["smtp"]["SMTP_PASSWORD"]
else:
    password = None

if "SMTP_TYPE" in cfg_dict["smtp"].keys():
    SMTP_TYPE = cfg_dict["smtp"]["SMTP_TYPE"]
else:
    SMTP_TYPE = None


def script_menu(description):
    """
    Unified parsing of parameters for netops scripts.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('inventory', help='Name of the inventory to run this script against')
    parser.add_argument('-u', '--user', help='[netconf] username to use')
    parser.add_argument('-p', '--password', help='[netconf] password to use')
    parser.add_argument('-e', '--email', help='Email to send the output to')
    args = parser.parse_args()
    return [args.inventory, args.user, args.password, args.email]


def read_inventory(inputfile):
    """
    Parses *.yml inventory file and returns it as dictionary
    """
    try:
        with open(INVENTORY_FOLDER + inputfile + '.yml', 'r') as f:
            invyaml = f.read()
    except IOError as err:
        print(err)
        onlyfiles = [f for f in os.listdir(INVENTORY_FOLDER) if os.path.isfile(os.path.join(INVENTORY_FOLDER, f))]
        inv_list = []
        for file in onlyfiles:
            inv_list.append(file.split('_')[-1][:-4])
        print('These are the valid inventories: {}'.format(inv_list))
        sys.exit(1)
    devices = yaml.load(invyaml)
    return devices


def emailout(to_addr, subject, body_text, files_to_attach):
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    if body_text:
        msg.attach(MIMEText(body_text))
    msg["To"] = to_addr
    # convert string to one item list
    files_to_attach = convert_string_to_list(files_to_attach)
    for file_to_attach in files_to_attach:
        try:
            with open(file_to_attach, "rb") as fh:
                data = fh.read()
            attachment = MIMEApplication(data)
            header = ('Content-Disposition', 'attachment', 'filename={}'.format(os.path.basename(file_to_attach)))
            attachment.add_header(*header)
            msg.attach(attachment)
        except IOError:
            msg = "Error opening attachment file {}".format(file_to_attach)
            print(msg)
            sys.exit(1)
    # Send the message via Google SSL
    if SMTP_TYPE == "SSL":
        server = smtplib.SMTP_SSL(SMTP_SERVER + ':' + SMTP_PORT)
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
    else:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.ehlo()
        if SMTP_TYPE == "SECURE":
            server.starttls()
            server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()


def start_logging(scriptname):
    """
    Redirects stdout to a file while still displaying output on screen
    """
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_filename = "{}{}_{}.txt".format(OUTPUT_PATH, scriptname, timestamp)
    outfile = open(out_filename, 'w+')
    old_stdout = sys.stdout
    sys.stdout = Tee(sys.stdout, outfile)
    return outfile, old_stdout


def stop_logging(outfile, old_stdout):
    """
    Stops logging to a file and returns the output to screen only
    """
    outfile.close()
    sys.stdout = old_stdout
    with open(outfile.name, 'r') as f:
        ansi = f.read()
    html = Ansi2HTMLConverter().convert(ansi)
    with open('{}.html'.format(outfile.name.split('.')[0]), 'w+') as f:
        f.write(html)


class Tee(object):
    """
    Helps achieve the logging to a file and terminal at the same time
    """
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush() # If you want the output to be visible immediately
    def flush(self) :
        for f in self.files:
            f.flush()



def jun_open(dev):
    """
    Attempts connecting to Junos device and returns boolean to indicate if it succeeds.
    There're three attempts to try to connect.
    If One Time Password is used and an authentication attempt fails new password can be passed in the input dialog
    """
    connected = False
    unreachable = False
    attempt = 0
    while not(connected or unreachable or attempt > 2):
        attempt += 1
        try:
            dev.open()
            dev.timeout = 60
            connected = True
        except ConnectAuthError as err:
            print("Cannot authenticate: {}".format(err))
            passw = getpass.getpass(prompt='Password: ', stream=None)
            dev.password = passw
        except ConnectError as err:
            print("Cannot connect to the device: {}".format(err))
            unreachable = True
    return connected


def load_yaml(path):
    """
    Load yaml from file for use in Jinja2
    """
    try:
        with open(path) as f:
            vars = f.read()
    except IOError as err:
        print(err)
        sys.exit(1)
    return yaml.load(vars)



def get_op_as_dict(dev, table):
    """ Get Table and returns it as dictionary  """
    op = table(dev).get()
    output_json = json.loads(op.to_json())
    return output_json



def get_table(dev, table):
    """
    Get an Operational or a Configuration Table and returns it as the object of the Class of that Table
    """
    tbl = table(dev).get()
    return tbl


def run_funct_on_devices(devices, optable, function, user, password):
    """
    Iterate over devices, retrieve result of one Operational Table as a dict and run a function on that result
    """
    for device in sorted(devices):
        print("==== Connecting to {} ====".format(device))
        dev = Device(host=devices[device]['ip'], user=user, password=password, gather_facts=False, port=22)
        connected = jun_open(dev)
        if connected:
            myOp = get_op_as_dict(dev, optable)
            function(myOp)
            dev.close()


# not used right now - letting pyez handle templating in push_template()    
def rendercfg(jipath, vars, nw_dev):
    """
    Generate config for router with Jinja2 template
    This function is intended to be used with Jinja2 templates
    """
    cprint("\nGenerating configuration for {}".format(nw_dev), 'yellow')
    with open(jipath) as f:
        s = f.read()
        template = Template(s)
    return template.render(vars)



def lock_configuration(dev):
    """
    Locks config on device and returns boolean indicating success
    This function is intended to be used with Jinja2 templates
    """
    #Lock device configuration 
    print("Locking the configuration")
    try: 
        dev.cu.lock()
        locked = True
    except LockError as err:
        print("Unable to lock configuration: \n {0}".format(err))
        dev.close()
        locked = False
    return locked



def push_template(dev, template, vars, format):
    """
    Pushes template and vars config to device (w/o commit) and returns string with configuration diff
    This function is intended to be used with Jinja2 templates
    """
    assert format in ["set", "xml", "text"]

    try:
        dev.cu.load(template_path=template, format=format, template_vars=vars)
        changes = dev.cu.diff()
    except (ConfigLoadError, Exception) as err:
        print("Unable to load configuration changes: {}".format(err))
        print("Unlocking the configuration")
        changes = None
        try:
            dev.cu.unlock()
        except UnlockError:
            print("Unable to unlock configuration {}".format(err))
    return changes


def commit_configuration(dev, ticket, username):
    """
    Commits configuration on device, requires ticket # +username for a comment;
    returns boolean indicating success.
    This function is intended to be used with Jinja2 templates
    """

    print("Committing the configuration")
    commited = False
    try:
        commited = dev.cu.commit(comment=ticket + "/" + username)
    except CommitError as err:
        print("Unable to commit configuration: {}".format(err))
        print("Unlocking the configuration")
    try:
        dev.cu.unlock()
    except UnlockError as err:
        print("Unable to unlock configuration {}".format(err))
    return commited


def rollback_configuration(dev):
    """
    Rollbacks configuration
    This function is intended to be used with Jinja2 templates
    """
    try:
        print("Discarding changes")
        dev.cu.rollback()
        dev.cu.unlock()
    except UnlockError as err:
        print("Unable to unlock configuration {}".format(err))


def update_configuration(dev, cfg, ticket, nwadmin):
    """
    It carries out the configuration procedure , i.e. Lock-Load-Diff-Commit-Unlock
    This function is NOT intended to be used with Jinja2 templates but with Configuration Tables
    """

    # Instantiate Class Config to get user friendly junos like diff output --------------
    cu = Config(dev)

    cprint("Review the configuration changes to be applied on %s" % dev, 'yellow')
    agree = 'N'
    try:
        cfg.lock()
        cfg.load()
        # rather than cfg.diff() use cu.diff() - it creates more user friendly outputs
        print(cu.diff())
        agree = input("Do you want to apply these changes? y/n[N]: " or 'N')
    except LockError as err:
        print("Unable to lock configuration: {0}".format(err))
    except (ConfigLoadError, Exception) as err:
        print("Unable to load configuration changes: {0}".format(err))
        print("Unlocking the configuration")
        try:
            cfg.unlock()
        except UnlockError:
            print("Unable to unlock configuration: {0}".format(err))

    # Proceed with updating configuration -----------------------------------------------
    if agree == "Y" or agree == "y":
        print("Committing the configuration")
        try:
            cfg.commit(comment=ticket + "/" + nwadmin)
        except CommitError as err:
            print("Unable to commit configuration: {0}".format(err))
            print("Unlocking the configuration")
        try:
            print("Unlocking the configuration")
            cfg.rollback()
            cfg.unlock()
        except UnlockError as err:
            print("Unable to unlock configuration: {0}".format(err))

    else:
        # Discard changes
        try:
            print("Discarding changes")
            cfg.rollback()
            cfg.unlock()
        except UnlockError as err:
            print("Unable to unlock configuration: {0}".format(err))



def convert_string_to_list(x):
    if isinstance(x, str):
        return [x]
    else:
        return x
        
def convert_bytes(num):
    """
    this function will convert bytes to whatever is more appropriate
    """
    for x in ['bytes', 'KiB', 'MiB', 'GiB', 'TiB']:
        if num < 1024.0:
            return "%3.1f %s" % (num, x)
        num /= 1024.0

def file_size(file_path):
    """
    this function will return the file size
    """
    if os.path.isfile(file_path):
        file_info = os.stat(file_path)
        return convert_bytes(file_info.st_size)
        
def file_size_bytes(file_path):
    """
    this function will return the file size in bytes
    """
    if os.path.isfile(file_path):
        file_info = os.stat(file_path)
        return file_info.st_size
