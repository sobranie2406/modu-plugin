# 默读插件

供默读安装的独立插件包。

| 插件 | 用途 | 权限 | 默读版本 |
| --- | --- | --- | --- |
| 私密书籍 | 打开私密书籍、锁定私密书籍 | 脚本执行、私密书籍管理 | 1.3.10+ |
| 文字整理 | 整理所选文字的空格和换行 | 脚本执行、划词动作 | 1.3.10+ |
| 示例提示词包 | 两个提示词模板与一个划词动作 | AI 提示词、划词动作 | 1.3.1+ |

插件不随默读安装。下载 `.moduplugin` 后，在「设置 → 实验性功能 → 管理插件」中安装并启用。
插件页面会自动加载已审核目录，提供下载安装、权限预览和确认。
默读仅接受经过项目审核、文件校验一致的插件版本。启用后才显示插件入口，停用后移除入口。

## 审核与上架

只有已签名的 [catalog.json](catalog.json) 中状态为 `reviewed` 的版本才已上架。提交源码不等于上架。
清单逐版本记录源码目录、最低默读版本、安装包及全部文件的 SHA-256，并注明审核记录。
本批记录为 Codex 执行的技术审核，不代表用户人工审核。打包脚本只生成并校验已上架版本。
默读使用内置公钥验证清单签名，再核对安装包和全部文件指纹。
插件使用的接口与权限受当前默读支持时，可独立安装或升级，无需同时更新默读。
审核源清单为 [catalog.source.json](catalog.source.json)，`catalog.json` 是签名后的发布文件。

## 下载

- [私密书籍 1.0.0](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/com.modu.private-books-1.0.0.moduplugin)
- [文字整理 1.0.0](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/com.modu.text-tools-1.0.0.moduplugin)
- [示例提示词包 1.1.0](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/com.example.prompt-pack-1.1.0.moduplugin)
- [SHA-256 校验](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/SHA256SUMS)

## 打包

需要 Python 3，无需额外依赖：

```sh
python3 scripts/pack.py
python3 -m unittest discover -s tests
```

审核后更新 `catalog.source.json` 的版本和校验值，再签名发布：

```sh
python3 scripts/sign_catalog.py --private-key /protected/path/catalog-key.pem
```

签名私钥只保存在维护者本机，不上传仓库。源码、安装包、审核源清单和签名清单一并提交。

安装包与 `SHA256SUMS` 输出到 `dist/`。文件顺序、时间戳和权限固定，同一环境可重复生成相同的包。

## 脚本接口

每个 `scriptAction` 指定包内的 `.js` 文件，文件内容作为异步函数体执行，可使用 `await` 和 `return`。

- `input.selection`：所选文字。
- `input.context`：仅在动作声明 `scope: "context"` 时提供上下文。
- `input.settings`：本插件声明的普通设置，不含密钥。
- `input.book`：授权的书籍信息，不含文件路径。

宿主只开放已声明并经用户授权的接口。插件不直接访问文件、数据库、账号密钥或阅读器页面。

现有提示词包仍沿用 `aiSkill`、`selectionAction` 格式；脚本使用 `scriptAction`，不改变旧包。
