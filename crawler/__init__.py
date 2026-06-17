"""爬虫模块"""

import tempfile
from io import BytesIO


def write_temp_image(buf: BytesIO, suffix: str = ".png") -> str:
    """将 BytesIO 写入临时文件并返回文件路径。

    AstrBot 的 Image 组件只接受 str（文件路径或 URL），
    不接受 BytesIO，因此需要先落盘再传路径。
    """
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(buf.getvalue())
        return f.name

