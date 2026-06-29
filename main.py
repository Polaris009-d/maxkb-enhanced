import argparse
import logging
import os
import sys
import time

import django
from django.core import management

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # 项目根目录 D:\落地项目\MaxKB-v2
APP_DIR = os.path.join(BASE_DIR, 'apps') # Django 应用目录

os.chdir(BASE_DIR) # 切工作目录
sys.path.insert(0, APP_DIR) # 把 apps/ 加入 Python 搜索路径
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "maxkb.settings")  # 指定 Django 配置文件设置环境变量 DJANGO_SETTINGS_MODULE，值为 maxkb.settings


def collect_static():
    """
     收集静态文件到指定目录
     本项目主要是将前端vue/dist的前端项目放到静态目录下面
    :return:
    """
    logging.info("Collect static files")
    try:
        management.call_command('collectstatic', '--no-input', '-c', verbosity=0, interactive=False)
        logging.info("Collect static files done")
    except:
        pass


def perform_db_migrate():
    """
    初始化数据库表
    wait-for-it 仅检测 TCP 端口，PostgreSQL 崩溃恢复期间端口已开放但拒绝查询，
    因此在此处增加重试逻辑，等待数据库真正就绪后再执行 migrate。
    """
    logging.info("Check database structure change ...")
    logging.info("Migrate model change to database ...")
    max_retries = 10
    retry_interval = 5  # seconds
    for attempt in range(1, max_retries + 1):
        try:
            management.call_command('migrate') # 发起迁移尝试，把模型变更同步到数据库表结构。
            return
        except Exception as e: # 捕获异常
            err_msg = str(e)
            # 判断是否为数据库仍在启动中（崩溃恢复场景）
            is_db_starting = (
                'the database system is starting up' in err_msg # PostgreSQL 正在恢复 WAL 日志（最核心的崩溃恢复场景）
                or 'starting up' in err_msg   # 更宽泛的匹配，防止错误文本有细微差异
                or 'Connection refused' in err_msg   # 极端情况下，端口还没来得及完全握手
            )
            if is_db_starting and attempt < max_retries:
                logging.warning(
                    f'Database is not ready yet (attempt {attempt}/{max_retries}), '
                    f'retrying in {retry_interval}s... Error: {err_msg}'
                )   # 如果重试次数没到（最多 10 次，即容忍最多 50 秒的数据库恢复时间），就睡 5 秒再试
                time.sleep(retry_interval)
            else:
                logging.error('Perform migrate failed, exit', exc_info=True)
                sys.exit(11)  # 如果超过了重试次数，或者报错不是“数据库启动中”，直接调用 sys.exit(11) 终止整个 Python 进程


def start_services():
    services = args.services if isinstance(args.services, list) else [args.services]
    start_args = []
    if args.daemon:
        start_args.append('--daemon')
    if args.force:
        start_args.append('--force')
    if args.worker:
        start_args.extend(['--worker', str(args.worker)])
    else:
        worker = os.environ.get('MAXKB_CORE_WORKER')
        if isinstance(worker, str) and worker.isdigit():
            start_args.extend(['--worker', worker])

    try:
        management.call_command(action, *services, *start_args)
    except KeyboardInterrupt:
        logging.info('Cancel ...')
        time.sleep(2)
    except Exception as exc:
        logging.error("Start service error {}: {}".format(services, exc))
        time.sleep(2)


def dev(maxkb=None):
    services = args.services if isinstance(args.services, list) else args.services
    if services.__contains__('web'):
        management.call_command('runserver', "0.0.0.0:8080")
    elif services.__contains__('celery'):
        management.call_command('celery', 'celery')
    elif services.__contains__('local_model'):
        from maxkb.const import CONFIG
        bind = f'{CONFIG.get("LOCAL_MODEL_HOST")}:{CONFIG.get("LOCAL_MODEL_PORT")}'
        management.call_command('runserver', bind)


if __name__ == '__main__':
    os.environ['HF_HOME'] = '/opt/maxkb-app/model/base'
    os.environ['TMPDIR'] = '/opt/maxkb-app/tmp'
    parser = argparse.ArgumentParser(
        description="""
           qabot service control tools;

           Example: \r\n

           %(prog)s start all -d;
           """
    )
    parser.add_argument(
        'action', type=str,
        choices=("start", "dev", "upgrade_db", "collect_static"),
        help="Action to run"
    )
    args, e = parser.parse_known_args()
    parser.add_argument(
        "services", type=str, default='all' if args.action == 'start' else 'web', nargs="*",
        choices=("all", "web", "task") if args.action == 'start' else ("web", "celery", 'local_model'),
        help="The service to start",
    )

    parser.add_argument('-d', '--daemon', nargs="?", const=True)
    parser.add_argument('-w', '--worker', type=int, nargs="?")
    parser.add_argument('-f', '--force', nargs="?", const=True)
    args = parser.parse_args()
    action = args.action
    services = args.services if isinstance(args.services, list) else args.services
    if services.__contains__('web'):
        os.environ.setdefault('SERVER_NAME', 'web')
    elif services.__contains__('local_model'):
        os.environ.setdefault('SERVER_NAME', 'local_model')
    django.setup()
    if action == "upgrade_db":
        perform_db_migrate()
    elif action == "collect_static":
        collect_static()
    elif action == 'dev':
        collect_static()
        perform_db_migrate()
        dev()
    else:
        collect_static()
        perform_db_migrate()
        start_services()
