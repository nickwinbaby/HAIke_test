# Git 使用参考

这个文档记录当前项目使用 Git 和 GitHub 的基本操作，方便以后查阅。

## 当前项目信息

本地项目目录：

```powershell
C:\Users\G1006871\Desktop\BIANYI
```

GitHub 仓库：

```text
https://github.com/nickwinbaby/HAIke_test
```

远程 Git 地址：

```text
https://github.com/nickwinbaby/HAIke_test.git
```

当前主分支：

```text
main
```

## Git 常用概念

### 本地仓库

本地仓库就是你电脑上的项目文件夹。执行过下面命令后，当前文件夹就变成 Git 仓库：

```powershell
git init
```

执行后会生成一个隐藏的 `.git` 文件夹，里面保存 Git 的版本记录。

### 远程仓库

远程仓库就是 GitHub 上的仓库。当前项目的远程仓库叫 `origin`。

查看远程仓库地址：

```powershell
git remote -v
```

修改远程仓库地址：

```powershell
git remote set-url origin https://github.com/nickwinbaby/HAIke_test.git
```

### 分支

分支可以理解为一条代码线。当前项目使用主分支 `main`。

查看当前分支：

```powershell
git branch
```

把当前分支改名为 `main`：

```powershell
git branch -M main
```

## 第一次上传代码的流程

第一次把本地项目上传到 GitHub，通常执行：

```powershell
git add .
git commit -m "init project"
git branch -M main
git push -u origin main
```

每条命令的意思：

```powershell
git add .
```

把当前目录下所有需要提交的文件加入待提交区。

```powershell
git commit -m "init project"
```

生成一次版本记录，`init project` 是这次提交的说明。

```powershell
git branch -M main
```

把当前分支改名为 `main`。

```powershell
git push -u origin main
```

把本地 `main` 分支上传到 GitHub，并建立本地和远程分支的关联。

## 以后日常怎么用

以后每次改完代码，通常只需要三步：

```powershell
git add .
git commit -m "说明这次改了什么"
git push
```

例如：

```powershell
git add .
git commit -m "fix gps parser"
git push
```

## 查看当前状态

查看哪些文件被修改、哪些文件还没提交：

```powershell
git status
```

简洁查看：

```powershell
git status --short --branch
```

查看最近一次提交：

```powershell
git log --oneline -1
```

查看提交历史：

```powershell
git log --oneline
```

## 在其他目录拉取仓库代码

如果要在电脑上的另一个目录下载 GitHub 仓库代码，使用 `git clone`。

例如想把仓库下载到 `D:\code` 目录：

```powershell
cd D:\code
git clone https://github.com/nickwinbaby/HAIke_test.git
```

执行后会生成一个新文件夹：

```text
D:\code\HAIke_test
```

进入项目：

```powershell
cd HAIke_test
```

如果想指定下载后的文件夹名称：

```powershell
git clone https://github.com/nickwinbaby/HAIke_test.git my_project
```

这样会生成：

```text
D:\code\my_project
```

如果想直接克隆到当前空文件夹：

```powershell
git clone https://github.com/nickwinbaby/HAIke_test.git .
```

注意：使用 `git clone ... .` 时，当前文件夹必须是空的。

## 已经克隆过，怎么更新代码

如果某个目录已经是这个仓库了，后面想拉取 GitHub 上的最新代码，不要再 `git clone`，而是进入项目目录后执行：

```powershell
git pull
```

例如：

```powershell
cd D:\code\HAIke_test
git pull
```

`git clone` 是第一次下载仓库用的。

`git pull` 是已经下载过仓库后，用来更新最新代码的。

## .gitignore 是什么

`.gitignore` 用来告诉 Git 哪些文件不要上传到 GitHub。

当前项目会忽略这些常见内容：

```gitignore
__pycache__/
build/
dist/
.idea/
.vscode/
*.zip
*.log
```

这些一般是缓存、打包输出、编辑器配置、日志或压缩包，不适合提交到代码仓库。

注意：`.gitignore` 不会删除本地文件，只是不让 Git 上传它们。

## 常见报错处理

### 1. Could not connect to server

示例：

```text
Failed to connect to github.com:443
Could not connect to server
```

意思是电脑连不上 GitHub。可以尝试：

```powershell
git push
```

如果还是失败，检查浏览器能不能打开：

```text
https://github.com
```

如果使用代理软件，需要先打开代理。

如果 Git 配置了错误代理，可以取消代理：

```powershell
git config --global --unset http.proxy
git config --global --unset https.proxy
```

### 2. fetch first

示例：

```text
! [rejected] main -> main (fetch first)
```

意思是 GitHub 仓库里已经有本地没有的内容，需要先拉取远程内容再推送：

```powershell
git pull origin main --allow-unrelated-histories --no-edit
git push
```

如果是新建空仓库，一般不会遇到这个问题。

### 3. 需要登录 GitHub

推送时看到：

```text
info: please complete authentication in your browser...
```

说明需要在浏览器里登录 GitHub。选择：

```text
Sign in with your browser
```

登录并授权后，回到 PowerShell 等待命令完成。

## 不要随便用的命令

下面这些命令会修改历史或覆盖内容，新手不要随便用：

```powershell
git push -f
git reset --hard
```

如果 Git 提示需要用这些命令，先确认清楚再执行。

## 推荐记住的最小命令集

日常最常用：

```powershell
git status
git add .
git commit -m "说明"
git push
```

查看远程仓库：

```powershell
git remote -v
```

查看历史：

```powershell
git log --oneline
```
