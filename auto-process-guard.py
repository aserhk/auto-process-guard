import subprocess
import time
import os
from datetime import datetime
import threading
import signal
import sys
import json
import psutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import queue

class OneKeyRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("程序监控系统")
        self.root.geometry("900x750")
        self.root.minsize(900, 750)
        
        # 程序状态变量
        self.process = None
        self.monitoring = False
        self.cleanup_running = False
        self.restart_count = 0
        self.last_file_update_time = time.time()
        self.last_check_time = time.time()
        self.config_file = "monitor_config.json"
        self.log_file = "monitor_log.txt"
        
        # 两次检测机制相关变量
        self.first_check_time = None  # 第一次检测时间
        self.second_check_time = None  # 第二次检测时间
        
        # 功能开关
        self.features = {
            "process_monitor": True,      # 进程监控
            "file_activity": True,        # 文件活动监控
            "auto_cleanup": True,         # 自动清理
            "first_check": True,          # 第一次检测
            "second_check": True          # 第二次检测
        }
        
        # 队列用于线程间通信
        self.log_queue = queue.Queue()
        self.status_queue = queue.Queue()
        
        # 默认配置
        self.default_config = {
            "exec_path": "",
            "record_dir": "",
            "cleanup_hours": 20,
            "first_check_delay": 10,    # 第一次检测延迟（秒）
            "second_check_delay": 20,   # 第二次检测延迟（秒）
            "check_interval": 30,
            "file_extensions": [".ts", ".mp4", ".flv", ".mkv", ".avi"]
        }
        
        # 加载配置
        self.config = self.load_config()
        
        # 创建界面
        self.create_widgets()
        
        # 启动日志更新线程
        self.log_update_thread = threading.Thread(target=self.update_log_display, daemon=True)
        self.log_update_thread.start()
        
        # 定期检查状态
        self.root.after(1000, self.update_status)
        
    def create_widgets(self):
        """创建GUI界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(5, weight=1)
        
        # 标题
        title_label = ttk.Label(main_frame, text="程序监控系统", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=4, pady=(0, 10))
        
        # 第一行：可执行文件路径
        ttk.Label(main_frame, text="可执行文件路径:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        self.exec_path_var = tk.StringVar(value=self.config.get("exec_path", ""))
        self.exec_path_entry = ttk.Entry(main_frame, textvariable=self.exec_path_var, width=50)
        self.exec_path_entry.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(0, 5))
        exec_browse_btn = ttk.Button(main_frame, text="浏览", command=self.browse_exec_file)
        exec_browse_btn.grid(row=1, column=3, padx=(0, 5))
        
        # 第二行：监控目录
        ttk.Label(main_frame, text="监控目录:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5))
        self.record_dir_var = tk.StringVar(value=self.config.get("record_dir", ""))
        self.record_dir_entry = ttk.Entry(main_frame, textvariable=self.record_dir_var, width=50)
        self.record_dir_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=(0, 5))
        record_browse_btn = ttk.Button(main_frame, text="浏览", command=self.browse_record_dir)
        record_browse_btn.grid(row=2, column=3, padx=(0, 5))
        
        # 第三行：控制按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=4, pady=10)
        
        self.start_btn = ttk.Button(button_frame, text="开始监控", command=self.start_monitoring)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_btn = ttk.Button(button_frame, text="停止监控", command=self.stop_monitoring, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        config_btn = ttk.Button(button_frame, text="配置参数", command=self.open_config_dialog)
        config_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        feature_btn = ttk.Button(button_frame, text="功能开关", command=self.open_feature_dialog)
        feature_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        save_btn = ttk.Button(button_frame, text="保存配置", command=self.save_current_config)
        save_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 第四行：功能状态显示
        feature_frame = ttk.LabelFrame(main_frame, text="功能状态", padding="5")
        feature_frame.grid(row=4, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.feature_status_vars = {}
        feature_names = [
            ("进程监控", "process_monitor"),
            ("文件监控", "file_activity"),
            ("自动清理", "auto_cleanup"),
            ("首次检测", "first_check"),
            ("二次检测", "second_check")
        ]
        
        for i, (display_name, key) in enumerate(feature_names):
            var = tk.StringVar(value="启用" if self.features[key] else "禁用")
            self.feature_status_vars[key] = var
            ttk.Label(feature_frame, text=f"{display_name}:").grid(row=0, column=i*2, padx=(0, 5))
            ttk.Label(feature_frame, textvariable=var, foreground="green" if self.features[key] else "red").grid(row=0, column=i*2+1, padx=(0, 15))
        
        # 第五行：状态显示
        status_frame = ttk.LabelFrame(main_frame, text="运行状态", padding="5")
        status_frame.grid(row=5, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        
        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, font=("Arial", 10))
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        # 第六行：日志显示
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding="5")
        log_frame.grid(row=6, column=0, columnspan=4, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 第七行：统计信息
        stats_frame = ttk.Frame(main_frame)
        stats_frame.grid(row=7, column=0, columnspan=4, sticky=(tk.W, tk.E))
        stats_frame.columnconfigure((0, 1, 2, 3), weight=1)
        
        self.restart_count_var = tk.StringVar(value="重启次数: 0")
        restart_label = ttk.Label(stats_frame, textvariable=self.restart_count_var)
        restart_label.grid(row=0, column=0)
        
        self.idle_time_var = tk.StringVar(value="空闲时间: 0秒")
        idle_label = ttk.Label(stats_frame, textvariable=self.idle_time_var)
        idle_label.grid(row=0, column=1)
        
        self.last_update_var = tk.StringVar(value="最后更新: 无")
        update_label = ttk.Label(stats_frame, textvariable=self.last_update_var)
        update_label.grid(row=0, column=2)
        
        self.check_status_var = tk.StringVar(value="检测状态: 无")
        check_label = ttk.Label(stats_frame, textvariable=self.check_status_var)
        check_label.grid(row=0, column=3)
        
    def browse_exec_file(self):
        """浏览选择可执行文件"""
        file_path = filedialog.askopenfilename(
            title="选择可执行文件",
            filetypes=[
                ("可执行文件", "*.exe;*.bat;*.cmd;*.sh"),
                ("批处理文件", "*.bat"),
                ("命令文件", "*.cmd"),
                ("Shell脚本", "*.sh"),
                ("可执行程序", "*.exe"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.exec_path_var.set(file_path)
            
    def browse_record_dir(self):
        """浏览选择监控目录"""
        dir_path = filedialog.askdirectory(title="选择监控目录")
        if dir_path:
            self.record_dir_var.set(dir_path)
            
    def start_monitoring(self):
        """开始监控"""
        exec_path = self.exec_path_var.get().strip()
        record_dir = self.record_dir_var.get().strip()
        
        # 验证输入
        if not exec_path or not os.path.exists(exec_path):
            messagebox.showerror("错误", "请选择有效的可执行文件!")
            return
            
        if not record_dir or not os.path.exists(record_dir) or not os.path.isdir(record_dir):
            messagebox.showerror("错误", "请选择有效的监控目录!")
            return
            
        # 更新配置
        self.config["exec_path"] = exec_path
        self.config["record_dir"] = record_dir
        
        # 重置检测状态
        self.reset_check_status()
        
        # 更新界面状态
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.status_var.set("正在启动监控程序...")
        self.check_status_var.set("检测状态: 初始化")
        
        # 重置状态
        self.restart_count = 0
        self.last_file_update_time = time.time()
        self.last_check_time = time.time()
        self.monitoring = True
        self.cleanup_running = True
        
        # 启动监控线程
        monitoring_thread = threading.Thread(target=self.monitoring_thread, daemon=True)
        monitoring_thread.start()
        
        self.log_message("开始监控任务...")
        self.log_message(f"监控程序: {exec_path}")
        self.log_message(f"监控目录: {record_dir}")
        
        # 显示启用的功能
        enabled_features = [name for name, enabled in self.features.items() if enabled]
        self.log_message(f"启用功能: {', '.join(enabled_features) if enabled_features else '无'}")
        
        # 添加检测机制说明到日志（如果启用）
        if self.features["first_check"] or self.features["second_check"]:
            first_delay = self.config.get('first_check_delay', 10)
            second_delay = self.config.get('second_check_delay', 20)
            self.log_message("=" * 50)
            self.log_message("检测机制:")
            if self.features["first_check"]:
                self.log_message(f"  第1次检测: 空闲{first_delay}秒时检查进程状态")
            if self.features["second_check"]:
                self.log_message(f"  第2次检测: 空闲{second_delay}秒时强制重启进程")
            self.log_message("=" * 50)
        
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        self.cleanup_running = False
        self.status_var.set("正在停止监控程序...")
        self.check_status_var.set("检测状态: 已停止")
        
        # 停止进程
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            self.process = None
            
        # 更新界面状态
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_var.set("监控已停止")
        self.log_message("监控程序已停止")
        
    def monitoring_thread(self):
        """监控主逻辑线程"""
        exec_path = self.config["exec_path"]
        record_dir = self.config["record_dir"]
        
        try:
            # 启动清理线程（如果启用）
            if self.features["auto_cleanup"]:
                cleanup_thread = threading.Thread(target=self.cleanup_thread, args=(record_dir,), daemon=True)
                cleanup_thread.start()
                self.log_message("自动清理线程已启动")
            
            # 启动可执行文件（如果启用进程监控）
            if self.features["process_monitor"]:
                if not self.start_exec_file(exec_path):
                    self.monitoring = False
                    return
            else:
                self.log_message("进程监控已禁用，跳过启动程序")
                
            # 主监控循环
            while self.monitoring:
                try:
                    # 检查并重启可执行文件（如果启用进程监控）
                    if self.features["process_monitor"]:
                        self.restart_exec_if_needed(exec_path)
                    
                    # 检查文件活动和执行检测机制（如果启用文件监控）
                    if self.features["file_activity"]:
                        self.check_file_activity_and_process(record_dir)
                    else:
                        # 如果文件监控禁用，但仍需要更新状态显示
                        self.update_status_display()
                    
                except Exception as e:
                    self.log_message(f"监控线程异常: {e}")
                time.sleep(1)
                
        except Exception as e:
            self.log_message(f"监控线程异常: {e}")
        finally:
            self.monitoring = False
            
    def start_exec_file(self, exec_path):
        """启动可执行文件"""
        try:
            # 杀死可能存在的相同进程
            self.kill_existing_processes(exec_path)
            
            # 根据文件类型决定启动方式
            if exec_path.lower().endswith('.bat') or exec_path.lower().endswith('.cmd'):
                # Windows批处理文件
                self.process = subprocess.Popen(
                    [exec_path],
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            elif exec_path.lower().endswith('.sh'):
                # Linux Shell脚本
                self.process = subprocess.Popen(
                    ['bash', exec_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            else:
                # 其他可执行文件
                self.process = subprocess.Popen(
                    [exec_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
            self.restart_count += 1
            self.log_message(f"监控程序已启动，PID: {self.process.pid} (第{self.restart_count}次启动)")
            self.status_queue.put(f"运行中 (PID: {self.process.pid})")
            
            # 重置检测时间
            self.reset_check_status()
            
            return True
        except Exception as e:
            self.log_message(f"启动失败: {e}")
            self.status_queue.put("启动失败")
            return False
            
    def kill_existing_processes(self, exec_path):
        """杀死可能存在的相同进程"""
        try:
            exec_filename = os.path.basename(exec_path)
            killed_count = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # 检查进程命令行是否包含可执行文件名
                    if proc.info['cmdline']:
                        cmdline_str = ' '.join(proc.info['cmdline'])
                        if exec_filename in cmdline_str:
                            proc.terminate()
                            try:
                                proc.wait(timeout=3)
                            except:
                                proc.kill()
                            killed_count += 1
                    # 检查进程名是否匹配
                    elif proc.info['name'] and exec_filename.lower() in proc.info['name'].lower():
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except:
                            proc.kill()
                        killed_count += 1
                except:
                    pass
                    
            if killed_count > 0:
                self.log_message(f"已终止 {killed_count} 个重复进程")
                
        except Exception as e:
            self.log_message(f"检查重复进程失败: {e}")
            
    def restart_exec_if_needed(self, exec_path):
        """检查并重启可执行文件"""
        if self.process is None or self.process.poll() is not None:
            if self.process:
                exit_code = self.process.poll()
                self.log_message(f"监控程序已退出，退出码: {exit_code}")
                
            self.log_message("检测到监控程序关闭，正在重新启动...")
            self.status_queue.put("重启中...")
            time.sleep(2)
            return self.start_exec_file(exec_path)
        return True
        
    def check_file_activity_and_process(self, record_dir):
        """检查文件活动并执行检测机制"""
        try:
            current_time = time.time()
            latest_mtime = 0
            latest_file = None
            file_extensions = self.config.get("file_extensions", [".ts", ".mp4", ".flv", ".mkv", ".avi"])
            
            # 查找最新文件
            for root, dirs, files in os.walk(record_dir):
                for file in files:
                    if any(file.lower().endswith(ext.lower()) for ext in file_extensions):
                        filepath = os.path.join(root, file)
                        try:
                            mtime = os.path.getmtime(filepath)
                            if mtime > latest_mtime:
                                latest_mtime = mtime
                                latest_file = filepath
                        except:
                            continue
            
            # 更新最后文件更新时间
            if latest_mtime > self.last_file_update_time and latest_mtime > 0:
                self.last_file_update_time = latest_mtime
                self.log_message(f"检测到新文件更新: {os.path.basename(latest_file)}")
                self.log_message(f"更新时间: {datetime.fromtimestamp(latest_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 有文件更新时重置检测时间
                self.reset_check_status()
            
            # 更新统计信息
            self.update_status_display()
            
            # 执行检测机制（根据功能开关）
            self.execute_check_mechanism(int(current_time - self.last_file_update_time))
                
        except Exception as e:
            self.log_message(f"文件活动检查异常: {e}")
            
    def update_status_display(self):
        """更新状态显示"""
        current_time = time.time()
        idle_time = int(current_time - self.last_file_update_time)
        self.idle_time_var.set(f"空闲时间: {idle_time}秒")
        self.last_update_var.set(f"最后更新: {datetime.fromtimestamp(self.last_file_update_time).strftime('%H:%M:%S')}")
        self.restart_count_var.set(f"重启次数: {self.restart_count}")
            
    def execute_check_mechanism(self, idle_time):
        """执行检测机制 - 根据功能开关"""
        try:
            current_time = time.time()
            
            # 如果两个检测都禁用，直接返回
            if not self.features["first_check"] and not self.features["second_check"]:
                return
                
            # 如果已经执行过第二次检测，不再重复检测
            if self.second_check_time is not None:
                return
            
            first_delay = max(1, self.config.get("first_check_delay", 10))
            second_delay = max(first_delay + 5, self.config.get("second_check_delay", 20))
            
            # 第一次检测（如果启用）
            if (self.features["first_check"] and 
                idle_time >= first_delay and 
                self.first_check_time is None):
                self.first_check_time = current_time
                self.check_status_var.set(f"检测状态: 第1次检测({first_delay}s)")
                self.log_message(f"第1次检测: 空闲{first_delay}秒，检查进程状态")
                
                # 检查进程状态（如果启用进程监控）
                if self.features["process_monitor"]:
                    if self.process and self.process.poll() is None:
                        self.log_message("进程正常运行，等待第二次检测")
                    else:
                        self.log_message("检测到进程关闭，立即重启")
                        self.restart_process(current_time)
                        return
                else:
                    self.log_message("进程监控已禁用，跳过进程检查")
            
            # 第二次检测（如果启用）
            if (self.features["second_check"] and 
                idle_time >= second_delay and 
                self.first_check_time is not None and 
                self.second_check_time is None):
                self.second_check_time = current_time
                self.check_status_var.set(f"检测状态: 第2次检测({second_delay}s)")
                self.log_message(f"第2次检测: 空闲{second_delay}秒，强制重启进程")
                self.restart_process(current_time)
                
        except Exception as e:
            self.log_message(f"检测机制异常: {e}")

    def restart_process(self, current_time):
        """重启进程的统一方法"""
        try:
            # 如果启用进程监控才终止进程
            if self.features["process_monitor"] and self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except:
                    try:
                        self.process.kill()
                    except:
                        pass
                self.process = None
                self.log_message("原进程已终止")
            
            # 重置时间
            self.last_file_update_time = current_time
            self.reset_check_status()
            self.check_status_var.set("检测状态: 重启中")
            
            time.sleep(2)
            
            # 如果启用进程监控才重启
            if self.features["process_monitor"]:
                self.start_exec_file(self.config["exec_path"])
            
        except Exception as e:
            self.log_message(f"重启进程失败: {e}")

    def reset_check_status(self):
        """重置检测状态"""
        self.first_check_time = None
        self.second_check_time = None
        self.check_status_var.set("检测状态: 重置")
        
    def cleanup_thread(self, directory):
        """清理线程"""
        try:
            hours = self.config.get("cleanup_hours", 20)
            self.log_message(f"开始自动清理任务... (清理{hours}小时前的文件)")
            
            while self.cleanup_running:
                self.cleanup_files(directory, hours)
                time.sleep(10)  # 每10秒检查一次
                
        except Exception as e:
            self.log_message(f"清理线程异常: {e}")
            
    def cleanup_files(self, directory, hours):
        """清理过期文件"""
        try:
            cutoff = time.time() - (hours * 3600)
            count = 0
            
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if file.lower().endswith('.ts'):
                        filepath = os.path.join(root, file)
                        try:
                            if os.path.getmtime(filepath) < cutoff:
                                os.remove(filepath)
                                count += 1
                                self.log_message(f"清理: {filepath}")
                        except Exception as e:
                            self.log_message(f"清理失败: {filepath} - {e}")
            
            if count > 0:
                self.log_message(f"本轮清理 {count} 个文件")
                
        except Exception as e:
            self.log_message(f"清理出错: {e}")
            
    def open_config_dialog(self):
        """打开配置对话框"""
        config_window = tk.Toplevel(self.root)
        config_window.title("配置参数")
        config_window.geometry("450x400")
        config_window.resizable(False, False)
        
        # 居中显示
        config_window.transient(self.root)
        config_window.grab_set()
        
        # 创建配置界面
        main_frame = ttk.Frame(config_window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 清理时间
        ttk.Label(main_frame, text="清理文件时间(小时):").grid(row=0, column=0, sticky=tk.W, pady=5)
        cleanup_hours_var = tk.StringVar(value=str(self.config.get("cleanup_hours", 20)))
        ttk.Entry(main_frame, textvariable=cleanup_hours_var, width=10).grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 第一次检测延迟
        ttk.Label(main_frame, text="第一次检测延迟(秒):").grid(row=1, column=0, sticky=tk.W, pady=5)
        first_check_var = tk.StringVar(value=str(self.config.get("first_check_delay", 10)))
        ttk.Entry(main_frame, textvariable=first_check_var, width=10).grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 第二次检测延迟
        ttk.Label(main_frame, text="第二次检测延迟(秒):").grid(row=2, column=0, sticky=tk.W, pady=5)
        second_check_var = tk.StringVar(value=str(self.config.get("second_check_delay", 20)))
        ttk.Entry(main_frame, textvariable=second_check_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 状态检查间隔
        ttk.Label(main_frame, text="状态检查间隔(秒):").grid(row=3, column=0, sticky=tk.W, pady=5)
        check_interval_var = tk.StringVar(value=str(self.config.get("check_interval", 30)))
        ttk.Entry(main_frame, textvariable=check_interval_var, width=10).grid(row=3, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 文件扩展名
        ttk.Label(main_frame, text="监控文件扩展名:").grid(row=4, column=0, sticky=tk.W, pady=5)
        extensions_var = tk.StringVar(value=",".join(self.config.get("file_extensions", [".ts", ".mp4", ".flv", ".mkv", ".avi"])))
        ttk.Entry(main_frame, textvariable=extensions_var, width=30).grid(row=4, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 说明文本
        info_text = tk.Text(main_frame, height=6, width=50, wrap=tk.WORD)
        info_text.grid(row=5, column=0, columnspan=2, pady=10)
        info_text.insert(tk.END, "配置说明：\n"
                        "1. 支持多种可执行文件：.exe, .bat, .cmd, .sh等\n"
                        "2. 检测机制可通过功能开关控制\n"
                        "3. 第二次检测时间应大于第一次检测时间\n"
                        "4. 文件监控扩展名可自定义")
        info_text.config(state=tk.DISABLED)
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        def save_config():
            try:
                # 验证数值
                first_delay = int(first_check_var.get())
                second_delay = int(second_check_var.get())
                
                # 确保第二次检测时间大于第一次
                if second_delay <= first_delay:
                    messagebox.showwarning("警告", "第二次检测时间应大于第一次检测时间，已自动调整")
                    second_delay = first_delay + 5
                
                self.config["cleanup_hours"] = int(cleanup_hours_var.get())
                self.config["first_check_delay"] = first_delay
                self.config["second_check_delay"] = second_delay
                self.config["check_interval"] = int(check_interval_var.get())
                extensions = [ext.strip() for ext in extensions_var.get().split(",")]
                extensions = [ext if ext.startswith('.') else '.' + ext for ext in extensions]
                self.config["file_extensions"] = extensions
                self.log_message("配置参数已更新")
                config_window.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的数字!")
                
        def cancel_config():
            config_window.destroy()
            
        ttk.Button(button_frame, text="保存", command=save_config).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=cancel_config).pack(side=tk.LEFT)
        
    def open_feature_dialog(self):
        """打开功能开关对话框"""
        feature_window = tk.Toplevel(self.root)
        feature_window.title("功能开关")
        feature_window.geometry("300x250")
        feature_window.resizable(False, False)
        
        # 居中显示
        feature_window.transient(self.root)
        feature_window.grab_set()
        
        # 创建功能开关界面
        main_frame = ttk.Frame(feature_window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 功能开关变量
        feature_vars = {}
        feature_info = [
            ("进程监控", "process_monitor", "监控可执行文件进程状态"),
            ("文件监控", "file_activity", "监控目录文件活动"),
            ("自动清理", "auto_cleanup", "自动清理过期文件"),
            ("首次检测", "first_check", "第一次空闲检测"),
            ("二次检测", "second_check", "第二次强制检测")
        ]
        
        # 创建复选框
        for i, (display_name, key, description) in enumerate(feature_info):
            var = tk.BooleanVar(value=self.features.get(key, True))
            feature_vars[key] = var
            cb = ttk.Checkbutton(main_frame, text=f"{display_name}", variable=var)
            cb.grid(row=i, column=0, sticky=tk.W, pady=5)
            ttk.Label(main_frame, text=description, font=("Arial", 8)).grid(row=i, column=1, sticky=tk.W, padx=(10, 0))
        
        # 按钮
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=len(feature_info), column=0, columnspan=2, pady=20)
        
        def save_features():
            # 保存功能开关状态
            for key, var in feature_vars.items():
                self.features[key] = var.get()
            
            # 更新界面显示
            for key, var in self.feature_status_vars.items():
                status = "启用" if self.features[key] else "禁用"
                var.set(status)
                # 更新颜色
                for widget in feature_frame.winfo_children():
                    if isinstance(widget, ttk.Label) and widget.cget("textvariable") == str(var):
                        widget.configure(foreground="green" if self.features[key] else "red")
            
            self.log_message("功能开关已更新")
            feature_window.destroy()
            
        def cancel_features():
            feature_window.destroy()
            
        ttk.Button(button_frame, text="保存", command=save_features).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=cancel_features).pack(side=tk.LEFT)
        
        # 说明文本
        info_label = ttk.Label(main_frame, text="注意：禁用某些功能可能影响监控效果", 
                              font=("Arial", 9), foreground="red")
        info_label.grid(row=len(feature_info)+1, column=0, columnspan=2, pady=(10, 0))
        
    def save_current_config(self):
        """保存当前配置"""
        self.config["exec_path"] = self.exec_path_var.get()
        self.config["record_dir"] = self.record_dir_var.get()
        self.save_config(self.config)
        self.log_message("配置已保存")
        
    def save_config(self, config_data):
        """保存配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_message(f"保存配置失败: {e}")
            
    def load_config(self):
        """从文件加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认配置
                merged_config = self.default_config.copy()
                merged_config.update(config)
                return merged_config
        except Exception as e:
            self.log_message(f"加载配置失败: {e}")
        return self.default_config.copy()
        
    def log_message(self, message):
        """添加日志消息到队列"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"[{timestamp}] {message}"
        self.log_queue.put(formatted_message)
        
        # 如果是重要消息，在状态栏也显示
        if any(keyword in message.lower() for keyword in ['错误', '失败', '重启', '检测']):
            display_message = message[:50] + "..." if len(message) > 50 else message
            self.status_var.set(display_message)
        
    def update_log_display(self):
        """更新日志显示"""
        while True:
            try:
                message = self.log_queue.get(timeout=0.1)
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
                self.log_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                break
                
    def update_status(self):
        """定期更新状态"""
        try:
            # 处理状态队列
            while not self.status_queue.empty():
                status = self.status_queue.get_nowait()
                self.status_var.set(status)
        except queue.Empty:
            pass
        except Exception as e:
            pass
            
        # 继续定期更新
        self.root.after(1000, self.update_status)

def main():
    # 检查依赖
    try:
        import psutil
    except ImportError:
        print("请安装psutil库: pip install psutil")
        return
        
    root = tk.Tk()
    app = OneKeyRecorderGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()