# -*- coding: utf-8 -*-
"""用户模块独立运行器：``python -m modules.user`` —— 仅启动用户/鉴权模块（端口 8001）。"""

from modules.common import run
from modules.user import create_user_app

app = create_user_app()

if __name__ == "__main__":
    run(app, "0.0.0.0", 8001)
