# -*- coding: utf-8 -*-
"""合并入口运行器：``python -m modules`` —— 启动完整的 MinePython 应用（端口 8000）。"""

from modules.combined import create_combined_app
from modules.common import run

app = create_combined_app()

if __name__ == "__main__":
    run(app, "0.0.0.0", 8000)
