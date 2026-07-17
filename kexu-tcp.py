import tkinter as tk
from tkinter import messagebox
import socket
import threading
import time

class TcpClientGUI:
    def __init__(self, master):
        self.master = master
        master.title("TCP客户端自动发送工具")

        # 服务器地址和端口
        tk.Label(master, text="服务器地址:").grid(row=0, column=0, sticky='e')
        self.addr_entry = tk.Entry(master, width=15)
        self.addr_entry.grid(row=0, column=1, padx=2)

        tk.Label(master, text="端口:").grid(row=0, column=2, sticky='e')
        self.port_entry = tk.Entry(master, width=6)
        self.port_entry.grid(row=0, column=3, padx=2)

        tk.Label(master, text="循环次数:").grid(row=0, column=4, sticky='e')
        self.loop_entry = tk.Entry(master, width=6)
        self.loop_entry.insert(0, "1")
        self.loop_entry.grid(row=0, column=5, padx=2)

        # 循环发送和断开按钮
        self.loop_btn = tk.Button(master, text="循环发送", command=self.start_loop, width=8)
        self.loop_btn.grid(row=0, column=6, padx=2)
        self.disconnect_btn = tk.Button(master, text="断开", command=self.stop_all, width=8)
        self.disconnect_btn.grid(row=0, column=7, padx=2)

        # 5个可选文本框，选择框和文本框紧挨，后面加发送按钮
        self.check_vars = []
        self.text_entries = []
        self.send_btns = []
        for i in range(5):
            var = tk.IntVar()
            chk = tk.Checkbutton(master, variable=var)
            chk.grid(row=i+1, column=0, padx=(2,0), sticky='e')
            self.check_vars.append(var)
            entry = tk.Entry(master, width=40)
            entry.grid(row=i+1, column=1, columnspan=6, sticky='w', padx=(2,2))
            self.text_entries.append(entry)
            btn = tk.Button(master, text="发送", width=6, command=lambda idx=i: self.send_single(idx))
            btn.grid(row=i+1, column=7, padx=2)
            self.send_btns.append(btn)

        # 右侧按钮区（自动发送、手动发送、清除文本框）
        btn_frame = tk.Frame(master)
        btn_frame.grid(row=0, column=8, columnspan=3, padx=5, pady=2, sticky='n')
        self.once_auto_btn = tk.Button(btn_frame, text="自动发送", command=self.start_once_auto, width=8)
        self.once_auto_btn.pack(side=tk.LEFT, padx=2)
        self.manual_btn = tk.Button(btn_frame, text="手动发送", command=self.manual_connect, width=8)
        self.manual_btn.pack(side=tk.LEFT, padx=2)
        self.clear_btn = tk.Button(btn_frame, text="清除文本框", command=self.clear_log, width=10)
        self.clear_btn.pack(side=tk.LEFT, padx=2)

        # 日志文本框放右侧
        self.log_text = tk.Text(master, width=40, height=18, state='disabled')
        self.log_text.grid(row=1, column=8, rowspan=6, padx=5, pady=5, sticky='n')

        # 独立的运行标志和线程
        self.loop_running = False
        self.once_auto_running = False
        self.manual_running = False
        self.loop_thread = None
        self.once_auto_thread = None
        self.manual_socket = None
        self.once_auto_socket = None

    def start_loop(self):
        if self.loop_running or self.once_auto_running or self.manual_running:
            self.show_info("请先断开其他模式的连接")
            return
        addr = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        loop = self.loop_entry.get().strip()
        if not addr or not port:
            messagebox.showwarning("提示", "服务器地址和端口不能为空！")
            return
        try:
            port = int(port)
            loop = int(loop)
            if loop < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "端口和循环次数必须为正整数！")
            return
        self.loop_running = True
        self.loop_btn.config(state='disabled')
        self.manual_btn.config(state='disabled')
        self.once_auto_btn.config(state='disabled')
        self.disconnect_btn.config(state='normal')
        self.loop_thread = threading.Thread(target=self.loop_task, args=(addr, port, loop), daemon=True)
        self.loop_thread.start()

    def start_once_auto(self):
        if self.loop_running or self.once_auto_running or self.manual_running:
            self.show_info("请先断开其他模式的连接")
            return
        addr = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        if not addr or not port:
            messagebox.showwarning("提示", "服务器地址和端口不能为空！")
            return
        try:
            port = int(port)
        except ValueError:
            messagebox.showwarning("提示", "端口必须为正整数！")
            return
        self.once_auto_running = True
        self.loop_btn.config(state='disabled')
        self.manual_btn.config(state='disabled')
        self.once_auto_btn.config(state='disabled')
        self.disconnect_btn.config(state='normal')
        self.once_auto_thread = threading.Thread(target=self.once_auto_task, args=(addr, port), daemon=True)
        self.once_auto_thread.start()

    def manual_connect(self):
        if self.loop_running or self.once_auto_running or self.manual_running:
            self.show_info("请先断开其他模式的连接")
            return
        addr = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        if not addr or not port:
            messagebox.showwarning("提示", "服务器地址和端口不能为空！")
            return
        try:
            port = int(port)
        except ValueError:
            messagebox.showwarning("提示", "端口必须为正整数！")
            return
        if self.manual_socket is not None:
            self.show_info("已建立手动连接")
            return
        try:
            self.manual_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.manual_socket.settimeout(10)
            self.manual_socket.connect((addr, port))
            self.show_info("手动连接服务器成功")
            self.manual_running = True
            self.manual_btn.config(state='disabled')
            self.loop_btn.config(state='disabled')
            self.once_auto_btn.config(state='disabled')
            self.disconnect_btn.config(state='normal')
        except Exception as e:
            self.show_info(f"手动连接失败: {e}")
            self.manual_socket = None

    def stop_all(self):
        # 停止所有模式
        if self.loop_running:
            self.loop_running = False
        if self.once_auto_running:
            self.once_auto_running = False
        if self.manual_running:
            self.manual_running = False
        # 关闭socket
        if self.manual_socket:
            try:
                self.manual_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.manual_socket.close()
            except Exception:
                pass
            self.manual_socket = None
            self.show_info("手动连接已断开")
        if self.once_auto_socket:
            try:
                self.once_auto_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.once_auto_socket.close()
            except Exception:
                pass
            self.once_auto_socket = None
            self.show_info("自动发送连接已断开")
        self.loop_btn.config(state='normal')
        self.manual_btn.config(state='normal')
        self.once_auto_btn.config(state='normal')
        self.disconnect_btn.config(state='normal')

    def loop_task(self, addr, port, loop):
        for i in range(loop):
            if not self.loop_running:
                break
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(10)
                s.connect((addr, port))
                self.show_info(f"第{i+1}次：已连接服务器")
            except Exception as e:
                self.show_info(f"第{i+1}次：连接失败: {e}")
                time.sleep(10)
                continue
            time.sleep(10)
            for idx, var in enumerate(self.check_vars):
                if not self.loop_running:
                    break
                if var.get():
                    data = self.text_entries[idx].get().encode()
                    try:
                        s.settimeout(10)
                        s.sendall(data)
                        self.show_info(f"{time.strftime('%H:%M:%S')}-第{i+1}次：发送数据{idx+1}: {self.text_entries[idx].get()}")
                    except Exception as e:
                        self.show_info(f"发送失败: {e}")
                    time.sleep(10)
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            s.close()
            self.show_info(f"第{i+1}次：已断开连接")
            time.sleep(10)
        self.loop_running = False
        self.loop_btn.config(state='normal')
        self.manual_btn.config(state='normal')
        self.once_auto_btn.config(state='normal')
        self.disconnect_btn.config(state='normal')

    def once_auto_task(self, addr, port):
        try:
            self.once_auto_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.once_auto_socket.settimeout(10)
            self.once_auto_socket.connect((addr, port))
            self.show_info("自动发送：已连接服务器")
        except Exception as e:
            self.show_info(f"自动发送：连接失败: {e}")
            self.once_auto_socket = None
            self.once_auto_running = False
            self.loop_btn.config(state='normal')
            self.manual_btn.config(state='normal')
            self.once_auto_btn.config(state='normal')
            self.disconnect_btn.config(state='normal')
            return
        count = 1
        while self.once_auto_running:
            for idx, var in enumerate(self.check_vars):
                if not self.once_auto_running:
                    break
                if var.get():
                    data = self.text_entries[idx].get().encode()
                    try:
                        if self.once_auto_socket is None:
                            self.show_info("自动发送连接已断开")
                            self.once_auto_running = False
                            break
                        self.once_auto_socket.settimeout(10)
                        self.once_auto_socket.sendall(data)
                        self.show_info(f"{time.strftime('%H:%M:%S')}-自动第{count}次：发送数据{idx+1}: {self.text_entries[idx].get()}")
                    except Exception as e:
                        self.show_info(f"自动发送失败: {e}")
                    time.sleep(10)
            count += 1
        if self.once_auto_socket:
            try:
                self.once_auto_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.once_auto_socket.close()
            except Exception:
                pass
            self.once_auto_socket = None
            self.show_info("自动发送连接已断开")
        self.once_auto_running = False
        self.loop_btn.config(state='normal')
        self.manual_btn.config(state='normal')
        self.once_auto_btn.config(state='normal')
        self.disconnect_btn.config(state='normal')

    def send_single(self, idx):
        if not self.manual_running:
            self.show_info("请先点击手动发送建立连接")
            return
        addr = self.addr_entry.get().strip()
        port = self.port_entry.get().strip()
        if not addr or not port:
            messagebox.showwarning("提示", "服务器地址和端口不能为空！")
            return
        try:
            port = int(port)
        except ValueError:
            messagebox.showwarning("提示", "端口必须为正整数！")
            return
        data = self.text_entries[idx].get()
        if not data:
            self.show_info(f"未输入要发送的数据")
            return
        if self.manual_socket is None:
            self.show_info("未建立手动连接，请先点击手动发送建立连接")
            return
        try:
            self.manual_socket.settimeout(10)
            self.manual_socket.sendall(data.encode())
            self.show_info(f"{time.strftime('%H:%M:%S')}-手动发送数据{idx+1}: {data}")
        except Exception as e:
            self.show_info(f"手动发送失败: {e}")

    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def show_info(self, msg):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

if __name__ == "__main__":
    root = tk.Tk()
    app = TcpClientGUI(root)
    root.mainloop()