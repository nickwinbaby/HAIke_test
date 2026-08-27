# Jenkins 多节点硬件电脑配置说明

本文档记录“一个 Jenkins 服务器管理多台硬件测试电脑”的配置方式。

适用场景：

```text
一套 Jenkins
多台硬件电脑
每台硬件电脑各接一套程控电源 / CAN 盒 / 继电器
Jenkins 统一调度测试项目
```

## 1. 推荐架构

```text
Jenkins Controller / Jenkins 主服务器
    |
    |-- Built-In Node / 当前 Jenkins 所在电脑
    |      |-- 程控电源
    |      |-- CAN 盒
    |      |-- USB 继电器
    |
    |-- HW_PC_2 / 第二台硬件电脑 Agent
           |-- 程控电源
           |-- CAN 盒
           |-- USB 继电器
```

说明：

- Jenkins Controller 负责网页、任务配置、用户管理、报告保存。
- 硬件电脑作为 Jenkins Agent 接入。
- 真正控制硬件的 Robot 测试，会在对应 Agent 电脑上执行。
- 每台硬件电脑建议只允许同时跑一个任务。

## 2. 第二台硬件电脑准备

第二台硬件电脑需要先准备这些环境：

```text
1. 能访问 Jenkins 地址，例如 http://10.85.20.251:8080/
2. 安装 Java
3. 安装 Python，例如 D:\Python310\python.exe
4. 安装 Robot Framework
5. 安装 CAN 盒驱动
6. 安装程控电源驱动
7. 安装 USB 继电器驱动
8. 放置 BIANYI 工程代码
```

建议统一代码目录，例如：

```text
D:\auto_test\BIANYI
```

建议统一 Jenkins Agent 工作目录：

```text
D:\jenkins_agent
```

## 3. Jenkins 新增节点

在 Jenkins 网页上操作：

1. 进入：

```text
Manage Jenkins / 系统管理
```

2. 点击：

```text
节点和云管理
```

3. 点击：

```text
New Node / 新建节点
```

4. 节点名称填写：

```text
HW_PC_2
```

5. 类型选择：

```text
Permanent Agent / 固定代理节点
```

6. 点击：

```text
Create / 创建
```

## 4. 配置 HW_PC_2 节点

进入 `HW_PC_2` 配置页面后，重点配置这些项。

### 4.1 Number of executors

```text
Number of executors
```

填写：

```text
1
```

含义：

```text
这台硬件电脑同一时间只允许跑 1 个 Jenkins 构建任务。
```

原因：

```text
一台硬件电脑通常只接一套程控电源、CAN 盒、继电器。
如果同时跑多个项目，可能会抢硬件、抢串口、抢 CAN 设备。
```

### 4.2 Remote root directory

```text
Remote root directory
```

填写第二台电脑上的 Jenkins 工作目录：

```text
D:\jenkins_agent
```

这个目录需要在第二台电脑上真实存在。

### 4.3 Labels

```text
Labels
```

建议填写：

```text
hw_pc_2 can_power_relay
```

说明：

- `hw_pc_2`：代表第二台硬件电脑。
- `can_power_relay`：代表这台电脑具备 CAN、电源、继电器硬件能力。

后期 Jenkins 项目可以通过 label 指定运行在哪台硬件电脑上。

### 4.4 Usage

```text
Usage
```

建议选择：

```text
Only build jobs with label expressions matching this node
```

中文可能是：

```text
只构建标签表达式匹配此节点的项目
```

含义：

```text
只有明确指定 hw_pc_2 的项目，才会跑到这台硬件电脑。
```

这样可以避免 Jenkins 随机把其他项目派到这台硬件电脑上。

### 4.5 Launch method

```text
Launch method
```

选择类似：

```text
Launch agent by connecting it to the controller
```

中文可能是：

```text
通过连接控制器来启动代理
```

如果页面里有：

```text
Use WebSocket
```

建议勾选。

## 5. 第二台电脑启动 Agent

保存节点后，进入 `HW_PC_2` 节点页面，Jenkins 会生成一段启动命令，类似：

```bat
java -jar agent.jar -url http://10.85.20.251:8080/ -secret xxxxx -name "HW_PC_2" -webSocket -workDir "D:\jenkins_agent"
```

如果第二台电脑还没有 `agent.jar`，可以在第二台电脑浏览器打开：

```text
http://10.85.20.251:8080/jnlpJars/agent.jar
```

下载到：

```text
D:\jenkins_agent\agent.jar
```

然后在第二台电脑 CMD 中执行：

```bat
cd /d D:\jenkins_agent
java -jar agent.jar -url http://10.85.20.251:8080/ -secret 你的secret -name "HW_PC_2" -webSocket -workDir "D:\jenkins_agent"
```

如果连接成功，Jenkins 页面里的 `HW_PC_2` 会显示在线。

## 6. Jenkins 项目指定运行节点

进入需要跑在第二台硬件电脑的 Jenkins 项目。

1. 点击：

```text
Configure / 配置
```

2. 找到：

```text
Restrict where this project can be run
```

中文可能是：

```text
限制项目运行节点
```

3. 勾选它。

4. Label Expression 填：

```text
hw_pc_2
```

5. 保存。

这样该项目以后只会跑在第二台硬件电脑上。

## 7. 构建命令路径处理

当前很多 Jenkins 构建命令里可能写死了路径：

```bat
cd /d C:\Users\G1006871\Desktop\BIANYI
```

如果第二台电脑代码路径不同，例如：

```text
D:\auto_test\BIANYI
```

那么第二台电脑对应项目里需要改成：

```bat
cd /d D:\auto_test\BIANYI
```

示例：

```bat
@echo on
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if exist "%WORKSPACE%\robot_results" rmdir /s /q "%WORKSPACE%\robot_results"

cd /d D:\auto_test\BIANYI

D:\Python310\python.exe -m robot ^
-d "%WORKSPACE%\robot_results" ^
-v DRY_RUN:False ^
-v TIME_SCALE:1.0 ^
--test "Power Can Basic3 Fixed Values 11bit 500K" ^
auto_test_reboot\tests\power_can_basic3.robot

echo Robot report: %JOB_URL%ws/robot_results/report.html
echo Robot log: %JOB_URL%ws/robot_results/log.html
echo Robot output: %JOB_URL%ws/robot_results/output.xml

exit /b %ERRORLEVEL%
```

## 8. 推荐使用 BIANYI_HOME 环境变量

为了避免每台电脑路径不同导致 Jenkins 命令不好维护，建议给每个节点配置环境变量：

```text
BIANYI_HOME
```

第一台电脑可以设置为：

```text
BIANYI_HOME=C:\Users\G1006871\Desktop\BIANYI
```

第二台电脑可以设置为：

```text
BIANYI_HOME=D:\auto_test\BIANYI
```

然后 Jenkins 批处理统一写成：

```bat
cd /d "%BIANYI_HOME%"
```

这样同一套构建命令可以适配不同硬件电脑。

## 9. 节点环境变量配置位置

进入节点配置页面：

```text
Manage Jenkins
-> 节点和云管理
-> HW_PC_2
-> Configure
```

找到：

```text
Node Properties / 节点属性
```

勾选：

```text
Environment variables
```

新增：

```text
Name:  BIANYI_HOME
Value: D:\auto_test\BIANYI
```

保存。

## 10. 多节点运行注意事项

### 10.1 每台硬件电脑 executors 建议为 1

只要一台电脑只有一套硬件，就建议：

```text
Number of executors = 1
```

这样可以避免多个任务同时抢硬件。

### 10.2 项目必须指定 label

如果项目需要跑在指定硬件电脑上，就配置：

```text
Restrict where this project can be run
```

然后填写：

```text
hw_pc_1
```

或：

```text
hw_pc_2
```

### 10.3 代码和驱动需要同步

每台硬件电脑都要有：

```text
Python 环境
Robot Framework
CAN 驱动
电源驱动
继电器驱动
auto_test_reboot 代码
```

否则 Jenkins 能连上 Agent，但测试仍然会失败。

### 10.4 COM 口和 USB 设备可能不同

不同电脑上的设备端口可能不同，例如：

```text
COM65
COM12
COM8
```

如果代码是自动搜索 USB 设备，影响较小。

如果后续某些设备需要固定端口，需要把端口做成 Robot 变量或节点环境变量。

### 10.5 报告仍然回到 Jenkins

即使测试在第二台电脑执行，Robot 报告仍然会保存到 Jenkins 该项目的 workspace 下，并可在 Jenkins 页面查看。

常见报告路径：

```text
%WORKSPACE%\robot_results\report.html
%WORKSPACE%\robot_results\log.html
%WORKSPACE%\robot_results\output.xml
```

## 11. 最终推荐模式

```text
Jenkins 服务器统一管理
每台硬件电脑作为 Agent
每台硬件电脑 Number of executors = 1
每台硬件电脑设置独立 label
每个 Jenkins 项目通过 label 指定运行节点
测试报告统一回传到 Jenkins 页面
```

这是后期扩展多套硬件自动化测试环境时比较稳的方式。
