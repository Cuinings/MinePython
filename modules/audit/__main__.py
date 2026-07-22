# -*- coding: utf-8 -*-
"""审计模块独立运行器：``python -m modules.audit`` —— 仅启动审计模块（端口 8003）。"""

from modules.audit import create_audit_app
from modules.common import run

app = create_audit_app()

if __name__ == "__main__":
    run(app, "0.0.0.0", 8003)
