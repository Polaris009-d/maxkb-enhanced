# -*- coding: utf-8 -*-
#
import os

from dotenv import load_dotenv

from .conf import ConfigManager

__all__ = ['BASE_DIR', 'PROJECT_DIR', 'VERSION', 'CONFIG']

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BASE_DIR)
LOG_DIR = os.path.join(PROJECT_DIR, 'logs')
VERSION = '2.0.0'

# load environment variables from .env file
# Search from PROJECT_DIR (parent of apps/) to find the .env in project root,
# also falling back to cwd for compatibility with main.py which chdir() there.
load_dotenv(os.path.join(PROJECT_DIR, '.env'))
# Also try cwd for celery/manage.py invoked from different directories
if not os.getenv('MAXKB_CONFIG_TYPE'):
    load_dotenv(os.path.join(os.getcwd(), '.env'))
# print(os.getenv('MAXKB_CONFIG'))
if os.getenv('MAXKB_CONFIG') is not None:
    CONFIG = ConfigManager.load_user_config(root_path=os.getenv('MAXKB_CONFIG'))
else:
    CONFIG = ConfigManager.load_user_config(root_path=PROJECT_DIR)

