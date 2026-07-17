import sys
from PyQt5.QtWidgets import QApplication
from ui_app import DataFetcherApp


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataFetcherApp()
    window.show()
    sys.exit(app.exec_())


#
# 4.0协议解析分层架构/
# ├─ main.py                 # 程序入口
# ├─ ui_app.py               # DataFetcherApp 主界面逻辑
# ├─ config.py               # 菜单、复选框分组、处理函数映射
# ├─ parsers_common.py       # 通用解析函数
# ├─ parsers_protocol.py     # 第 1-9 章 display/process 解析函数
# └─ services_utils.py       # 服务器取数 + Excel 导出