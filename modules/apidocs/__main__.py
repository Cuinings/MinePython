# -*- coding: utf-8 -*-
"""API 文档模块独立运行器：``python -m modules.apidocs`` —— 仅启动文档门户（端口 8004）。"""

from modules.apidocs import create_apidocs_app
from modules.common import run

app = create_apidocs_app()

if __name__ == "__main__":
    run(app, "0.0.0.0", 8004)
