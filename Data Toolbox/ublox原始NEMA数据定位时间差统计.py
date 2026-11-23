import tkinter as tk
from tkinter import filedialog

def parse_time(t):
    """031022.00 -> 秒"""
    if not t or '.' not in t:
        return None
    hhmmss = t.split('.')[0]
    h = int(hhmmss[0:2])
    m = int(hhmmss[2:4])
    s = int(hhmmss[4:6])
    return h * 3600 + m * 60 + s

def is_gngga(line):
    return "$GNGGA" in line

def get_fields(line):
    return line.strip().split(',')

def main():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title="选择TXT文件")

    if not file_path:
        print("未选择文件")
        return

    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    nofix_count = 0          # 未定位计数（=秒）
    in_event = False
    start_time = None
    results = []

    for line in lines:
        if not is_gngga(line):
            continue

        fields = get_fields(line)
        if len(fields) < 7:
            continue

        fix = fields[6]

        # =========================
        # 未定位
        # =========================
        if fix == '0':
            nofix_count += 1

            if nofix_count >= 3 and not in_event:
                in_event = True
                start_nofix = nofix_count  # 记录未定位开始点

        # =========================
        # 已定位
        # =========================
        else:
            if not in_event:
                # 没进入事件，清零
                nofix_count = 0
                continue

            time_str = fields[1]
            t_sec = parse_time(time_str)

            if t_sec is None:
                continue

            # 已定位时间作为结束
            end_time = t_sec

            # 只在进入事件后才计算
            results.append({
                "nofix_sec": nofix_count,
                "fix_end_time": end_time,
                "total": None  # 后面补
            })

            in_event = False
            nofix_count = 0

    # =========================
    # 输出（重点修正 total）
    # =========================
    print("\n===== 统计结果 =====")

    for i, r in enumerate(results):
        # 未定位秒 + 定位时间（这里默认从事件开始点计时）
        # 如果你要“精确总时长”，需要再补 start_time 版本（可升级）
        total = r["nofix_sec"]

        print(f"段 {i+1}: 未定位 {r['nofix_sec']} 秒")

if __name__ == "__main__":
    main()