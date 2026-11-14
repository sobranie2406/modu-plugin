# 默读插件

供默读安装的独立插件包，要求默读 1.3.10 或更新版本。

| 插件 | 用途 | 权限 |
| --- | --- | --- |
| 私密书籍 | 打开私密书籍、锁定私密书籍 | 脚本执行、私密书籍管理 |
| 文字整理 | 整理所选文字的空格和换行 | 脚本执行、划词动作 |

插件不随默读安装。下载 `.moduplugin` 后，在「设置 → 实验性功能 → 管理插件」中安装并启用。
默读仅接受经过项目审核、文件校验一致的插件版本。启用后才显示插件入口，停用后移除入口。

## 下载

- [私密书籍 1.0.0](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/com.modu.private-books-1.0.0.moduplugin)
- [文字整理 1.0.0](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/com.modu.text-tools-1.0.0.moduplugin)
- [SHA-256 校验](https://raw.githubusercontent.com/sobranie2406/plug-in/main/dist/SHA256SUMS)

## 打包

需要 Python 3，无需额外依赖：

```sh
python3 scripts/pack.py
python3 -m unittest discover -s tests
```

安装包与 `SHA256SUMS` 输出到 `dist/`。文件顺序、时间戳和权限固定，同一环境可重复生成相同的包。

## 脚本接口

每个 `scriptAction` 指定包内的 `.js` 文件，文件内容作为异步函数体执行，可使用 `await` 和 `return`。

- `input.selection`：所选文字。
- `input.context`：仅在动作声明 `scope: "context"` 时提供上下文。
- `input.settings`：本插件声明的普通设置，不含密钥。
- `input.book`：授权的书籍信息，不含文件路径。

宿主只开放已声明并经用户授权的接口。插件不直接访问文件、数据库、账号密钥或阅读器页面。

现有提示词包仍沿用 `aiSkill`、`selectionAction` 格式；脚本使用 `scriptAction`，不改变旧包。
