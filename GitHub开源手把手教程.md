# GitHub 开源手把手教程（零基础版）

> 目标：把「局部图片定位工具」从你电脑上的几个文件，变成 `https://github.com/你的用户名/image-locator` 这样一个任何人都能访问、能下载 exe 的开源项目。
> 全程只需要：**装一个 Git、在网页点几下、在命令行敲 5 行命令**。

---

## 第 0 步：先理解三件事（1 分钟）

| 名词 | 是什么 | 类比 |
| --- | --- | --- |
| 本地仓库 | 你电脑上那个文件夹，被 `git init` 变成"受版本管理"的文件夹 | 你的草稿本 |
| 远程仓库 | GitHub 网站上的那个项目页面 | 云盘上的公开副本 |
| push | 把本地的新提交上传到远程 | 把草稿本同步到云盘 |

开源 = 远程仓库设成 **Public（公开）**，别人能看代码、能下载、能提建议（Pull Request）。
你的图片 `huaiyanggudao.jpg`、打包好的 176MB 文件夹、63MB 的 zip **都不进代码仓库**，zip 只在"Release"里挂附件。

---

## 第 1 步：准备工作

### 1.1 注册 / 登录 GitHub

打开 https://github.com → 右上角 **Sign up** 注册（已有账号直接 **Sign in**）。
注册后**务必去邮箱点验证链接**，未验证的账号不能创建 Release。

### 1.2 安装 Git for Windows

1. 打开 https://git-scm.com/download/win ，下载 **64-bit Git for Windows Setup**；
2. 一路 **Next**（默认选项就够用，不用改任何勾选）；
3. 装完在开始菜单搜 **Git Bash** 并打开，输入：

```bash
git --version
```

能看到 `git version 2.x.x` 就成功。

> 后面所有命令都可以在 **Git Bash** 里执行（推荐，命令和教程完全一致）。用 Windows 自带的 cmd / PowerShell 也可以，只是路径写法略有差别。

### 1.3 告诉 Git 你是谁（只需一次）

在 Git Bash 里执行，把名字和邮箱换成你 GitHub 的：

```bash
git config --global user.name "你的名字或GitHub用户名"
git config --global user.email "你注册GitHub用的邮箱"
git config --global core.quotepath false
```

第三条是让中文文件名在 `git status` 里正常显示（否则会变成 `\344\270\255` 这种乱码）。

---

## 第 2 步：整理本地仓库文件

1. 把 `github_repo_files.zip` 解压，得到 `image-locator` 文件夹；
2. 进入该文件夹，你应该看到这些（这 10 个才是要上传的）：

```
image-locator/
├── README.md            ← 项目首页
├── LICENSE              ← MIT 许可证
├── PUBLISHING.md        ← 发布清单（可选，也可删）
├── requirements.txt     ← 依赖
├── build_exe.bat        ← 一键打包脚本
├── run.bat              ← 源码启动脚本
├── image_locator.py     ← 主程序
├── app.ico              ← 图标
├── .gitignore           ← 忽略规则（以点开头，可能被系统隐藏）
└── docs/                ← 放截图
```

3. **改掉占位符**：用记事本打开 `LICENSE`，把 `<Your Name>` 改成你的名字；打开 `README.md`，把 `<your-name>` 和 `<你的名字>` 换成你的 GitHub 用户名；
4. **（可选）放截图**：按 `docs/README.md` 里的说明放三张截图，然后把 README「界面预览」的占位文字换成 `![主界面](docs/screenshot-main.png)` 这种写法。没有截图也能先发，之后随时补。

> `.gitignore` 里已经写好了：`huaiyanggudao.jpg`、`*.zip`、`局部图片定位工具/`、`dist*/`、`*.log` 都不会被上传。**不要**手动把它们塞进去。

---

## 第 3 步：在本地建立仓库并提交

打开 Git Bash，`cd` 到 `image-locator` 文件夹（小技巧：在资源管理器地址栏输入 `cmd` 回车，或把文件夹拖进 Git Bash 窗口自动补全路径）：

```bash
cd /c/Users/你的用户名/Downloads/image-locator
git init
```

看到 `Initialized empty Git repository in ...` 就对了。

```bash
git add .
git status
```

`git status` 会列出「Changes to be committed」——**逐条看一眼**，确认里面只有上面那 10 个文件，没有 jpg、没有 zip、没有 `_internal`。这一步就是"放进待提交清单"。

确认无误后提交：

```bash
git commit -m "feat: 局部图片定位工具首个开源版本"
```

输出类似 `10 files changed, 800 insertions(+)`，本地就存下第一个版本了。

```bash
git branch -M main
```

把主分支改名成 `main`（GitHub 默认叫这个，不改的话后面会多一步）。

---

## 第 4 步：在 GitHub 网页上创建空仓库

1. 登录后点右上角 **+** → **New repository**（或直接打开 https://github.com/new）；
2. **Repository name** 填：`image-locator`
3. **Description** 填：`截图取局部，自动在原图中定位并输出坐标的 Windows 小工具`
4. 选 **Public**（开源必须公开；Private 只有你自己和受邀的人能看）；
5. **下面三个勾选框全部不要勾**：
   - ❌ Add a README file
   - ❌ Add .gitignore
   - ❌ Choose a license
   
   原因：你本地已经有了，勾了会造成"远程已有一份提交、本地也有一份，两边冲突"，新手最容易卡在这里。
6. 点 **Create repository**。

创建完页面会显示一堆命令提示（`…or create a new repository on the command line`），**你不用照着抄**，用下面第 5 步的即可。

---

## 第 5 步：关联并推送（最关键的一步）

在同一个 Git Bash 窗口继续执行，把 `你的用户名` 和 `image-locator` 换成实际的：

```bash
git remote add origin https://github.com/你的用户名/image-locator.git
git push -u origin main
```

### 会弹出登录窗口（第一次一定遇到）

- **情况 A：弹出 "Sign in to GitHub.com" 网页/窗口** → 点 **Sign in with your browser**，浏览器里点 **Authorize**，授权完成即可，以后不再问。这是 Git for Windows 自带的 Git Credential Manager 在帮你，最省事。
- **情况 B：命令行要求输入 Username / Password** → **密码不能填你的 GitHub 登录密码**（2021 年起已禁用）。要填 **Personal Access Token**：
  1. 打开 https://github.com/settings/tokens → **Generate new token (classic)**；
  2. Note 随便写（如 `win-push`），Expiration 选 30 天；
  3. 勾选 **`repo`** 这一整个大项（必须）；
  4. 拉到底 **Generate token**，复制那串 `ghp_xxxx`（**只显示一次**，先粘到记事本）；
  5. 回到命令行：Username 填你的 GitHub 用户名，Password **粘贴 token**（输入时不显示字符，粘完直接回车）。

### 成功的标志

```
To https://github.com/你的用户名/image-locator.git
 * [new branch]      main -> main
branch 'main' set up to track 'origin/main'.
```

刷新仓库页面，能看到 README 渲染出来的中文介绍 = 开源成功。

---

## 第 6 步：把仓库"装修"一下（5 分钟，很重要）

在仓库首页点右上角 **⚙️（齿轮，在 About 右边）**：

1. **Description**：`截图取局部，自动在原图中定位并输出坐标的 Windows 小工具 | Template-matching based region locator`
2. **Topics** 依次添加：`opencv`、`template-matching`、`tkinter`、`image-processing`、`windows`、`desktop-app`、`python`（有人靠 Topics 搜到你的项目）
3. 勾上 **Releases**、**Packages** 不需要，**Website** 可留空；
4. 点 **Save changes**。

顺手确认 `LICENSE` 在文件列表里显示为 "MIT license"（说明 GitHub 认出来了）。

---

## 第 7 步：发 Release，把 exe 给普通用户

代码仓库里只有源码，普通用户不会装 Python，所以要单独挂打包好的 zip：

1. 仓库页面右侧点 **Releases** → **Create a new release**（或 `/releases/new`）；
2. **Choose a tag**：输入 `v1.0.0` → 点 **Create new tag: v1.0.0 on publish**；
3. **Release title**：`v1.0.0 首个可分发版本`；
4. **Describe this release** 贴上：

```markdown
## 下载
- `局部图片定位工具_Win64.zip`（Windows 10/11 64 位，无需安装 Python）
- 解压后**保持整个文件夹完整**，双击 `局部图片定位工具.exe`

## 注意
- 原图请重命名为 `huaiyanggudao.jpg` 放在 exe 同目录（仓库不提供任何示例地图）
- 首次运行若被 SmartScreen 拦截，点「更多信息 → 仍要运行」
- 按 `Ctrl+Alt+A` 截图，松开鼠标后在选区内**双击**送入
```

5. **Attach binaries**：把 `局部图片定位工具_Win64.zip`（63MB）拖进去，等进度条走完（GitHub 单文件上限 100MB，够用）；
6. 点 **Publish release**。

之后在 README 顶部可以加一句：`📦 [下载 Windows 版](https://github.com/你的用户名/image-locator/releases/latest)`。

---

## 第 8 步：以后改了代码怎么更新（日常只用这 4 条）

```bash
git status                 # 看哪些文件变了
git add .                  # 把改动加入清单（改了哪个文件就 add 哪个更稳）
git commit -m "fix: 修复坐标换算偏差"
git push                   # 推上去（第一次设过 -u，以后不用写 origin main）
```

想发新版本：改完代码 → 打包新 zip → 再建一次 Release，tag 用 `v1.0.1`。

---

## 常见报错对照表

| 报错 / 现象 | 原因 | 解决 |
| --- | --- | --- |
| `remote origin already exists` | 之前加过 remote | `git remote set-url origin https://github.com/你的用户名/image-locator.git` |
| `Authentication failed` / `Support for password authentication was removed` | 用了账号密码 | 改用 Personal Access Token（第 5 步情况 B），或删掉旧凭据后重推 |
| `Updates were rejected because the remote contains work that you do not have` | 建仓库时勾了 README/license | 新手最省事：`git pull --rebase origin main` 再 `git push`；或删掉远程仓库重建（不勾那三个框） |
| `error: src refspec main does not match any` | 还没有 commit，或分支名不是 main | 先 `git add . && git commit`，再 `git branch -M main` |
| `file is 100.00 MB; this exceeds GitHub's file size limit` | 把 zip / 打包目录提交了 | `git rm --cached 文件名`，然后再 `git commit`；大文件只放 Release |
| `fatal: not a git repository` | 当前不在仓库文件夹 | `cd` 到含 `.git` 的目录再执行 |
| push 一直卡住 / `Failed to connect` | 网络问题 | 重试一次；仍失败可配置代理 `git config --global http.proxy http://127.0.0.1:端口`（有梯子时） |
| 中文文件名显示成 `\344\270\255` | Git 默认转义 | `git config --global core.quotepath false` |
| 网页上看不到 `.gitignore` | 以点开头的文件默认隐藏 | 正常现象，用 `git ls-files` 或网页的 "View all files" 可确认 |

---

## 新手最容易踩的 5 个坑

1. **先建仓库又勾了 README**，导致 push 冲突——记住第 4 步"三个框全不勾"；
2. **`git add .` 之前不看 `git status`**，把 176MB 的 `局部图片定位工具/` 和 63MB zip 一起提交，之后很难清理；
3. **把 password 当密码**，一定用 token 或浏览器授权；
4. **公开仓库里放了别人的地图/图纸**，涉及版权，仓库只放代码和你自己的示例；
5. **删文件用 `git rm` 而不是直接删**：直接删掉本地文件后 `git add .` 也能生效，但 `git rm` 更明确，且不会漏。

---

## 一页速查（打印版）

```bash
git config --global user.name   "名字"
git config --global user.email  "邮箱"
git config --global core.quotepath false

cd 仓库文件夹
git init
git add .
git status            # 确认没有 zip / jpg / 大目录
git commit -m "feat: 首个开源版本"
git branch -M main
git remote add origin https://github.com/用户名/image-locator.git
git push -u origin main

# 日常更新
git add . && git commit -m "说明" && git push
```
