# -*- coding: utf-8 -*-
"""MinePython 版本号唯一来源（single source of truth）。

所有模块与 server.py 入口都从这里 import VERSION，升级版本只改这一处。
对外暴露的 app.version、启动横幅、OpenAPI 元数据均以本值为准。
"""

VERSION = "4.7.0"
__version__ = VERSION  # PEP 396 约定，便于外部工具读取
