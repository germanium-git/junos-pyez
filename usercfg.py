#! /usr/bin/env python

"""
===================================================================================================
   Author:         Petr Nemec
   Description:    Configure local accounts on Junos based devices by using the ConfigurationTable
   Date:           2017-12-27
===================================================================================================
"""

from j_commons import *
from pyez_cfg_tables.users.usertables import UserConfigTable

from pprint import pprint

import platform
if platform.system() != "Windows":
    import pwd

DESCRIPTION = "Configure local accounts"
SCRIPT_NAME = 'usercfg'


def main():

    # Initiate script variables ---------------------------------------------------------
    inventory, user, password, email_spec = script_menu(DESCRIPTION)
    devices = read_inventory(inventory)

    # Start logging into a file
    outfile, old_stdout = start_logging(SCRIPT_NAME)

    print("Action: Configure local accounts \nDevices to run this on:")
    for device in sorted(devices):
        print(device)


    # Specify the local acount's parameters ---------------------------------------------
    cprint("Enter the account to be modified or created", 'yellow')
    account = ''
    while not account:
        account = input("Account [%s]: " % 'Emergency') or 'Emergency'


    account_passw = getpass.getpass(prompt='Password: ', stream=None)
    if account_passw:
        failure = 0
        account_passw2 = getpass.getpass(prompt='Repeat the password: ', stream=None)
        while not (account_passw2 == account_passw or failure > 2):
            account_passw2 = getpass.getpass(prompt="Password doesn't match, repeat again: ",
                                             stream=None)
            failure += 1
        if failure == 3:
            print("Too many failures, password won't be configured")
            account_passw = ''


    fname = input("Full name[%s]: " % 'Local emergency user account')\
            or 'Local emergency user account'
    logclass = input("Login class[%s]: etc. operator, read-only, unauthorized"
                     % 'super-user') or 'super-user'
    sshkey_path = input("Path to SSH key[%s]: " % 'no key') or 'no key'
    ticket = input("Ticket: ")

    if sshkey_path != 'no key':
        key_found = False
        k = ''
        failure = 0
        while not (key_found or failure > 2):
            try:
                with open(sshkey_path, 'r') as f:
                    k = f.read()
                key_found = True
            except IOError:
                sshkey_path = input("SSH key not found. Path to SSH key[%s]: "
                                    % 'no key') or 'no-key'
                failure += 1
        if failure == 3:
            print("Too many failures, SSH key won't be configured")

    else:
        key_found = False

    # Print brief info what's going to happen -------------------------------------------
    cprint('\nThis script will create or update login account %s on following routers:'
           % account, 'yellow')
    for device in sorted(devices):
        print('  - ' + device)

    # Agreement -------------------------------------------------------------------------
    agree = ''
    while not (agree == "y" or agree == "Y"):
        agree = input("Do you want to continue? y/n[N]: ") or 'N'
        if agree == "n" or agree == "N":
            print("Script execution canceled")
            return

    # Enter administrator's credentials

    if user == None:
        if platform.system() != "Windows":
            user = input("\nUsername[%s]: " % os.getlogin() or os.getlogin())
        else:
            user = input("\nUsername[%s]: " % getpass.getuser() or getpass.getuser())

    if password == None:
        password = getpass.getpass(prompt='Password: ', stream=None)


    # Connect to devices and retrieve data ----------------------------------------------
    for device in sorted(devices):
        print("==== Connecting to {} =========".format(device))
        dev = Device(host=devices[device]['ip'], user=user, password=password,
                     gather_facts=False, port=22)
        connected = jun_open(dev)
        if connected:
            # Create an instance of UserConfigTable Class -------------------------------
            usercfg = get_table(dev, UserConfigTable)
            print("Local accounts:")
            pprint(usercfg.keys())

            # Create New User -----------------------------------------------------------
            usercfg.username = account
            if logclass:
                usercfg.userclass = logclass
            if account_passw:
                usercfg.password = account_passw
            if fname:
                usercfg.fullname = fname
            if key_found:
                # The keys must be added in a form of a list
                usercfg.sshkeys = [k]

            usercfg.append()

            """
            # to review XML syntax of configuration changes
            configXML = usercfg.get_table_xml()
            if (configXML is not None):
                print (etree.tostring(configXML, encoding='unicode', pretty_print=True))

            """

            update_configuration(dev, usercfg, ticket, user)

        # End the NETCONF session and close the connection
        dev.close()

    # Revert the output back to original settings
    stop_logging(outfile, old_stdout)

    outfile_html = ('{}.html'.format(outfile.name.split('.')[0]))

    # Send a copy of log file via email to the recipients
    if not email_spec:
        email_spec = input("Email[%s]: " % pwd.getpwuid(os.getuid())[4]) or pwd.getpwuid(os.getuid())[4]
        emailout(email_spec, 'Netops', 'This is the result of the script you ran', outfile_html)


if __name__ == "__main__":
        main()
