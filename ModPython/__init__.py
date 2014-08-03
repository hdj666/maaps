#
# Author : hdj <helmut@oblig.at>
# Date   : 2014.06
# Project: maaps
# Description:
#   TODO: add some description!
#
import os

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.sys.path.insert(0,parentdir)

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parentdir not in os.sys.path:
    os.sys.path.insert(0,parentdir)