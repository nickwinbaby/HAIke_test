def parse_status(num_str):

    value = int(num_str)

    bin_str = bin(value)[2:]
    print("\n原始二进制:", bin_str)

    bin_32 = bin_str.zfill(32)
    print("补齐32位:", bin_32)

    bits = list(reversed(bin_32))

    def get_bits(start, end=None):
        if end is None:
            return int(bits[start])
        return int("".join(reversed(bits[start:end+1])), 2)

    print(f"bit0      : CAN断线状态 = {get_bits(0)} (1断线 0正常)")
    print(f"bit1      : CAN中断接收标识 = {get_bits(1)} (1-进入can中断函数,心跳包上报后清0)")
    print(f"bit2      : GPS定位标识 = {get_bits(2)} (1定位 0不定位)")
    print(f"bit3~5    : FOTA升级状态 = {get_bits(3,5)} (0:无升级任务 3:设备请求升级包 4:设备下载升级包完成 5:升级成功)")
    print(f"bit6      : CAN波特率匹配成功状态 = {get_bits(6)} (0:匹配失败 1:匹配成功)")
    print(f"bit7~9    : CAN波特率匹配类型 = {get_bits(7,9)} (0:无匹配 1:50K 2:250k 3:500k 4:125k 5:1000k)")
    print(f"bit10~15  : 保留 = {get_bits(10,15)} (保留位，暂不使用)")
    print(f"bit16~23  : 唤醒类型 = {get_bits(16,23)} (1-sensor唤醒 0x10(16):can唤醒)")
    print(f"bit24~31  : 重启类型 = {get_bits(24,31)} (0-normal 1-watchdog 2-upgrade 4-pinReset 0xFF-init)")
    print()


if __name__ == "__main__":

    while True:
        num = input("请输入十进制状态值 (输入q退出): ")

        if num.lower() == "q":
            break

        if not num.isdigit():
            print("请输入十进制数字！\n")
            continue

        parse_status(num)