# -*- coding: utf-8 -*-
"""文件服务器模块独立运行器：``python -m modules.files`` —— 仅启动文件模块（端口 8002）。"""

from modules.common import run
from modules.files import create_files_app

app = create_files_app()

if __name__ == "__main__":
    run(app, "0.0.0.0", 8002)
