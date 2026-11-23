"""
文件操作功能实现 - 完全重写版本
支持多种文件格式的大文件生成，包括Office文档格式
"""

import os
import time
import random
import struct
import threading
import zipfile


class FileOperations:
    """文件操作类 - 完全重写版本"""

    def __init__(self):
        self.open_files = {}
        self.file_lock = threading.Lock()
        self.stop_creating_large_file_flag = False
        self.creation_lock = threading.Lock()

    def create_large_file_with_format(self, file_path, size_mb, file_format="exe"):
        """创建指定格式的大文件 - 完全重写版本"""
        self.stop_creating_large_file_flag = False
        target_size = size_mb * 1024 * 1024

        try:
            # 根据格式生成文件头和内容
            header, content_generator = self._get_file_format_data(file_format)
            header_size = len(header) if header else 0

            with open(file_path, 'wb') as f:
                current_size = 0

                # 写入文件头
                if header:
                    f.write(header)
                    current_size += header_size
                    progress = min(100, (current_size / target_size) * 100)
                    yield progress

                # 生成文件内容
                chunk_size = 1024 * 1024  # 1MB chunks

                while current_size < target_size and not self.stop_creating_large_file_flag:
                    remaining = target_size - current_size
                    write_size = min(chunk_size, remaining)

                    # 生成内容数据
                    content_chunk = content_generator(write_size)
                    actual_write = len(content_chunk)

                    f.write(content_chunk)
                    current_size += actual_write

                    progress = min(100, (current_size / target_size) * 100)
                    yield progress

                    # 稍微延迟以减少CPU占用
                    time.sleep(0.01)

                # 如果被停止，确保文件大小正确
                if self.stop_creating_large_file_flag and current_size < target_size:
                    # 填充剩余空间
                    remaining = target_size - current_size
                    if remaining > 0:
                        f.write(b'\x00' * remaining)
                        current_size = target_size
                        yield 100

        except Exception as e:
            raise Exception(f"创建{file_format.upper()}格式文件失败: {str(e)}")

    def _get_file_format_data(self, file_format):
        """获取不同文件格式的头数据和内容生成器"""
        format_handlers = {
            "exe": (self._generate_exe_header(), self._generate_exe_content),
            "zip": (self._generate_zip_header(), self._generate_zip_content),
            "rar": (self._generate_rar_header(), self._generate_binary_content),
            "mp3": (self._generate_mp3_header(), self._generate_mp3_content),
            "mp4": (self._generate_mp4_header(), self._generate_mp4_content),
            "pdf": (self._generate_pdf_header(), self._generate_pdf_content),
            "doc": (self._generate_doc_header(), self._generate_doc_content),
            "docx": (self._generate_docx_header(), self._generate_docx_content),
            "xls": (self._generate_xls_header(), self._generate_xls_content),
            "xlsx": (self._generate_xlsx_header(), self._generate_xlsx_content),
            "ppt": (self._generate_ppt_header(), self._generate_ppt_content),
            "pptx": (self._generate_pptx_header(), self._generate_pptx_content),
            "dat": (b'', self._generate_binary_content)
        }

        return format_handlers.get(file_format, (b'', self._generate_binary_content))

    def _generate_exe_header(self):
        """生成EXE文件头"""
        # PE文件头结构
        mz_header = b'MZ' + os.urandom(58)  # DOS头
        pe_header = b'PE\x00\x00'  # PE签名

        # 基本的PE文件头
        machine = b'\x4c\x01'  # i386
        number_of_sections = b'\x01\x00'  # 1个节
        time_date_stamp = struct.pack('<I', int(time.time()))
        pointer_to_symbol_table = b'\x00\x00\x00\x00'
        number_of_symbols = b'\x00\x00\x00\x00'
        size_of_optional_header = b'\xe0\x00'
        characteristics = b'\x01\x01'  # 可执行文件

        coff_header = (machine + number_of_sections + time_date_stamp +
                       pointer_to_symbol_table + number_of_symbols +
                       size_of_optional_header + characteristics)

        return mz_header + pe_header + coff_header

    def _generate_zip_header(self):
        """生成ZIP文件头"""
        # 本地文件头签名
        return b'PK\x03\x04' + os.urandom(26)

    def _generate_rar_header(self):
        """生成RAR文件头"""
        # RAR文件头
        return b'Rar!\x1a\x07\x00' + os.urandom(5)

    def _generate_mp3_header(self):
        """生成MP3文件头"""
        # ID3v2标签头
        return b'ID3' + bytes([0x03, 0x00]) + b'\x00' + os.urandom(6)

    def _generate_mp4_header(self):
        """生成MP4文件头"""
        # ftyp box
        ftyp_size = struct.pack('>I', 24)  # 24字节
        ftyp_type = b'ftyp'
        major_brand = b'mp42'
        minor_version = b'\x00\x00\x00\x00'
        compatible_brands = b'mp42mp41'

        return ftyp_size + ftyp_type + major_brand + minor_version + compatible_brands

    def _generate_pdf_header(self):
        """生成PDF文件头"""
        header = b'%PDF-1.4\n'
        header += b'%' + os.urandom(4) + b'\n'  # 二进制注释
        return header

    def _generate_doc_header(self):
        """生成DOC文件头 - Microsoft Word 97-2003格式"""
        # DOC文件头 (Microsoft Compound File)
        header = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'  # 复合文件签名
        header += os.urandom(16)  # 其他头信息
        return header

    def _generate_docx_header(self):
        """生成DOCX文件头 - Office Open XML格式"""
        # DOCX实际上是ZIP文件，包含特定的XML结构
        return b'PK\x03\x04' + os.urandom(26)  # ZIP头

    def _generate_xls_header(self):
        """生成XLS文件头 - Microsoft Excel 97-2003格式"""
        # XLS文件头 (Microsoft Compound File)
        header = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'  # 复合文件签名
        header += os.urandom(16)  # 其他头信息
        return header

    def _generate_xlsx_header(self):
        """生成XLSX文件头 - Office Open XML格式"""
        # XLSX实际上是ZIP文件
        return b'PK\x03\x04' + os.urandom(26)  # ZIP头

    def _generate_ppt_header(self):
        """生成PPT文件头 - Microsoft PowerPoint 97-2003格式"""
        # PPT文件头 (Microsoft Compound File)
        header = b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'  # 复合文件签名
        header += os.urandom(16)  # 其他头信息
        return header

    def _generate_pptx_header(self):
        """生成PPTX文件头 - Office Open XML格式"""
        # PPTX实际上是ZIP文件
        return b'PK\x03\x04' + os.urandom(26)  # ZIP头

    def _generate_exe_content(self, size):
        """生成EXE文件内容"""
        # 生成随机的代码段数据
        return os.urandom(size)

    def _generate_zip_content(self, size):
        """生成ZIP文件内容"""
        # 生成压缩数据（实际上是随机数据）
        return os.urandom(size)

    def _generate_mp3_content(self, size):
        """生成MP3文件内容"""
        # 生成类似MP3帧的数据
        data = bytearray()
        while len(data) < size:
            # MP3帧头 (11字节同步字 + 帧信息)
            frame_header = b'\xFF\xFB' + os.urandom(2)
            frame_size = min(1152, size - len(data) - 4)  # 典型MP3帧大小
            frame_data = os.urandom(frame_size)
            data.extend(frame_header)
            data.extend(frame_data)
        return bytes(data[:size])

    def _generate_mp4_content(self, size):
        """生成MP4文件内容"""
        # 生成类似MP4 box的数据
        data = bytearray()
        while len(data) < size:
            box_size = min(1024, size - len(data) - 8)
            if box_size <= 0:
                break
            box_header = struct.pack('>I', box_size + 8)  # 包含头部的大小
            box_type = b'mdat'  # 媒体数据box
            box_data = os.urandom(box_size)
            data.extend(box_header)
            data.extend(box_type)
            data.extend(box_data)
        return bytes(data[:size])

    def _generate_pdf_content(self, size):
        """生成PDF文件内容"""
        data = bytearray()

        # 添加一些PDF对象
        obj_count = max(1, size // 1000)  # 根据大小调整对象数量

        for i in range(min(obj_count, 100)):  # 最多100个对象
            if len(data) >= size:
                break

            obj_id = i + 1
            obj_content = f"{obj_id} 0 obj\n<<\n/Length 100\n>>\nstream\n"
            obj_content += 'A' * 100 + '\nendstream\nendobj\n\n'

            data.extend(obj_content.encode('utf-8'))

        # 如果数据不够，用随机数据填充
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_doc_content(self, size):
        """生成DOC文件内容"""
        # DOC文件使用复合文件格式，这里生成类似的结构
        data = bytearray()

        # 添加一些DOC格式的标记
        data.extend(b'\x01\x00\xFE\xFF')  # 一些DOC标记
        data.extend(os.urandom(16))  # 一些随机数据

        # 填充剩余空间
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_docx_content(self, size):
        """生成DOCX文件内容"""
        # DOCX是ZIP格式，包含XML文件
        data = bytearray()

        # 模拟ZIP文件结构
        data.extend(b'PK\x03\x04')  # 本地文件头签名

        # 添加一些XML内容标记
        xml_start = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        data.extend(xml_start)

        # 填充剩余空间
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_xls_content(self, size):
        """生成XLS文件内容"""
        # XLS文件使用复合文件格式
        data = bytearray()

        # 添加一些XLS格式的标记
        data.extend(b'\x09\x08\x10\x00\x00\x06\x05\x00')  # 一些XLS标记
        data.extend(os.urandom(16))  # 一些随机数据

        # 填充剩余空间
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_xlsx_content(self, size):
        """生成XLSX文件内容"""
        # XLSX是ZIP格式，包含XML文件
        data = bytearray()

        # 模拟ZIP文件结构
        data.extend(b'PK\x03\x04')  # 本地文件头签名

        # 添加一些XML内容标记
        xml_start = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        data.extend(xml_start)

        # 填充剩余空间
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_ppt_content(self, size):
        """生成PPT文件内容"""
        # PPT文件使用复合文件格式
        data = bytearray()

        # 添加一些PPT格式的标记
        data.extend(b'\x00\x6E\x1E\xF0')  # 一些PPT标记
        data.extend(os.urandom(16))  # 一些随机数据

        # 填充剩余空间
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_pptx_content(self, size):
        """生成PPTX文件内容"""
        # PPTX是ZIP格式，包含XML文件
        data = bytearray()

        # 模拟ZIP文件结构
        data.extend(b'PK\x03\x04')  # 本地文件头签名

        # 添加一些XML内容标记
        xml_start = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        data.extend(xml_start)

        # 填充剩余空间
        if len(data) < size:
            data.extend(os.urandom(size - len(data)))

        return bytes(data[:size])

    def _generate_binary_content(self, size):
        """生成二进制内容"""
        return os.urandom(size)

    # 兼容旧版本的方法
    def create_large_file(self, file_path, size_mb):
        """创建大文件 - 兼容旧版本"""
        for progress in self.create_large_file_with_format(file_path, size_mb, "dat"):
            yield progress

    def stop_creating_large_file(self):
        """停止创建大文件"""
        self.stop_creating_large_file_flag = True

    def delete_large_file(self, file_path):
        """删除大文件"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as e:
            print(f"删除文件失败: {e}")
            return False

    # 文件打开模式相关方法（保持原有功能）
    def open_file_with_mode(self, file_path, mode):
        """以指定模式打开文件"""
        try:
            file_key = f"{file_path}_{mode}"

            if mode == "exclusive":
                # 独占模式打开
                import win32file
                import win32con
                handle = win32file.CreateFile(
                    file_path,
                    win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                    0,  # 不共享
                    None,
                    win32con.OPEN_EXISTING,
                    0,
                    None
                )
                self.open_files[file_key] = {'handle': handle, 'type': 'win32'}
            else:
                # 普通模式打开
                if mode == "shared_read":
                    file_obj = open(file_path, 'rb')
                elif mode == "shared_write":
                    file_obj = open(file_path, 'rb+')
                else:
                    file_obj = open(file_path, 'rb')

                self.open_files[file_key] = {'handle': file_obj, 'type': 'standard'}

            return f"文件已以 {mode} 模式打开"

        except Exception as e:
            raise Exception(f"打开文件失败: {str(e)}")

    def close_file(self, file_path, mode):
        """关闭文件"""
        try:
            file_key = f"{file_path}_{mode}"
            if file_key in self.open_files:
                file_info = self.open_files[file_key]
                if file_info['type'] == 'win32':
                    import win32file
                    win32file.CloseHandle(file_info['handle'])
                else:
                    file_info['handle'].close()
                del self.open_files[file_key]
                return "文件已关闭"
            return "文件未找到或已关闭"
        except Exception as e:
            raise Exception(f"关闭文件失败: {str(e)}")

    def close_all_files(self):
        """关闭所有文件"""
        try:
            count = 0
            for file_key, file_info in list(self.open_files.items()):
                try:
                    if file_info['type'] == 'win32':
                        import win32file
                        win32file.CloseHandle(file_info['handle'])
                    else:
                        file_info['handle'].close()
                    count += 1
                except:
                    pass

            self.open_files.clear()
            return f"已关闭 {count} 个文件"
        except Exception as e:
            raise Exception(f"关闭所有文件失败: {str(e)}")

    def test_file_open(self, file_path, mode):
        """测试文件打开"""
        try:
            if mode == "exclusive" and not os.path.exists(file_path):
                # 独占模式可以创建新文件
                import win32file
                import win32con
                handle = win32file.CreateFile(
                    file_path,
                    win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                    0,
                    None,
                    win32con.CREATE_NEW,
                    0,
                    None
                )
                win32file.CloseHandle(handle)
                if os.path.exists(file_path):
                    os.remove(file_path)
                return "文件可以独占模式打开"

            elif os.path.exists(file_path):
                # 测试普通模式
                if mode == "shared_read":
                    with open(file_path, 'rb') as f:
                        pass
                elif mode == "shared_write":
                    with open(file_path, 'rb+') as f:
                        pass
                return f"文件可以 {mode} 模式打开"
            else:
                return "文件不存在"

        except Exception as e:
            return f"文件打开测试失败: {str(e)}"

    def get_open_files_status(self):
        """获取打开文件状态"""
        if not self.open_files:
            return "没有打开的文件"

        status = "当前打开的文件:\n"
        for file_key, file_info in self.open_files.items():
            file_path, mode = file_key.rsplit('_', 1)
            file_type = "Windows句柄" if file_info['type'] == 'win32' else "文件对象"
            status += f"- {file_path} ({mode}, {file_type})\n"

        return status