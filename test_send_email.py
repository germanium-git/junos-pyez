#! /usr/bin/env python

"""
===================================================================================================
   Author:         Petr Nemec
   Description:    Test send email
   Date:           2017-12-31
===================================================================================================
"""

from j_commons import *


DESCRIPTION = "Configure local accounts"
SCRIPT_NAME = 'usercfg'


def main():
    email_spec = input("Email: ")
    emailout(email_spec, 'Netops', 'This is testing email', 'test_send_email.py')


if __name__ == "__main__":
        main()
