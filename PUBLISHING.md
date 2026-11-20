# 开源发布清单（给自己的备忘）

## 1. 仓库命名与简介

建议仓库名（slug 用小写英文加连字符，和 exe 中文名分开）：

- `image-locator`（最通用，推荐）
- `map-image-locator`
- `map-region-finder`

GitHub 仓库 About 一句话简介（可直接粘贴）：

> 截图取局部，自动在原图中定位并输出基准坐标的 Windows 小工具 / Locate a cropped region inside a large map or poster image, with configurable coordinates.

Topics 建议：`opencv` `template-matching` `tkinter` `image-processing` `windows` `desktop-app` `python`

## 2. 首次提交

```bash
cd <本目录>
git init
git add README.md LICENSE .gitignore requirements.txt build_exe.bat image_locator.py run.bat app.ico
git commit -m "feat: 局部图片定位工具首个开源版本"
git branch -M main
git remote add origin https://github.com/<your-name>/<repo>.git
git push -u origin main
```

**不要提交**：`huaiyanggudao.jpg`、`_internal/`、`局部图片定位工具_Win64.zip`、`dist*/`、`*.spec`、`*.log`（`.gitignore` 已覆盖）。

## 3. README 里待替换的内容

- `LICENSE` 与 README 末尾的 `<你的名字>` → 换成你的名字或 GitHub ID；
- README 顶部徽章里的仓库名（如需徽章指向 stars/issues）；
- 「界面预览」的占位说明 → 换成 `docs/screenshot-main.png` 等真实截图；
- 若仓库名不是 `image-locator`，同步改「快速开始」里的 clone 地址。

## 4. 截图建议（3 张足够）

| 文件 | 内容 | 要点 |
| --- | --- | --- |
| `docs/screenshot-main.png` | 主界面 | 原图带 3 个候选框 + 右侧结果列表（坐标可见） |
| `docs/screenshot-snip.png` | 框选浮层 | 显示暗化 + 选区 + 双击提示 |
| `docs/screenshot-result.png` | 标注图局部 | 标签如 `#1 0.648 (120, 135)` |

截图里避免出现他人隐私信息、真实地名敏感内容；用你自己的示例图或合成图。

## 5. 发布 Release（分发 exe）

1. Tag：`git tag v1.0.0 && git push origin v1.0.0`；
2. Releases → Draft a new release → 选 tag，标题 `v1.0.0 — 首个可分发版本`；
3. 附件：`局部图片定位工具_Win64.zip`（63 MB，GitHub 单文件上限 100 MB，可以直传）；
4. Release 说明写清：解压后**整目录使用**、需自备 `huaiyanggudao.jpg`、SmartScreen 提示、日志文件位置；
5. 不要用 Git LFS 存 zip，Release 附件更合适。

## 6. 后续可选补充

- `CHANGELOG.md`：按版本记录（Keep a Changelog 风格）；
- `.github/ISSUE_TEMPLATE/bug_report.md`：让反馈者带上系统版本、图片尺寸、精度设置、`image_locator_error.log`；
- `CONTRIBUTING.md`：从 README 的「参与贡献」小节拆分出去；
- GitHub Actions：`windows-latest` 上跑 `py_compile` + 打包，产出 artifact；
- `docs/` 放一张 `demo.gif`（框选 → 匹配 → 出坐标，10 秒内），比截图更有说服力。

## 7. 许可证选择说明

- 当前放的是 **MIT**：最宽松，别人可商用、可闭源二次开发，只需保留版权声明；
- 若希望贡献者显式授予专利许可、要求标注修改，换成 **Apache-2.0**；
- 依赖许可：opencv-python（Apache-2.0）、numpy（BSD-3）、Pillow（MIT-CMU），与本项目 MIT 兼容，无需额外声明；
- 若将来引入 GPL 组件，需整体改为 GPL 兼容许可，注意提前评估。
