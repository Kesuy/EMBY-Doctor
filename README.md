# EMBY Doctor

**EMBY Doctor** 是一个面向 Emby 的 Windows 桌面维护与批处理工具，用于对指定媒体库执行常见的元数据清理与检查操作。

当前桌面版集成四组维护能力：

1. **删除指定媒体库涉及演员的 Primary 头像**
2. **扫描指定媒体库中没有 Actor 信息的影片**
3. **重复人物与质检：重复 Person、头像缺失、Provider ID 冲突**
4. **删除指定媒体库所有影片的 Director 信息**

> 删除/迁移类操作都必须先扫描预览，再由用户二次确认后执行。

## UI 设计

桌面界面采用左侧功能导航 + 顶部页面标题 + 卡片式工作区。通用 Emby 连接信息包括：

- Emby 地址
- API Key
- HTTPS 证书校验
- HTTP 超时
- 测试连接 / 保存设置

演员头像、无演员影片、导演信息三个媒体库工具拥有各自独立的扫描范围，可分别选择 **全部媒体库** 或 **指定媒体库**；指定模式使用媒体库名称多选，内部仍保存稳定的媒体库 ID。

“重复人物与质检”是服务器级人物治理页面，包含 **重复人物 / 头像质量 / 资料冲突** 三个子页。

## 设置保存位置

Windows EXE 运行时，所有设置保存在 **EXE 同目录**：

```text
EMBY-Doctor.exe
settings.json
backups/
reports/
```

- `settings.json`：Emby 通用连接信息、三个功能各自的媒体库 ID 等设置。
- `backups/`：删除导演前生成的完整影片元数据 JSON 备份。
- `reports/`：三个功能导出的 CSV。输出结果保留完整文件路径，并额外提供不含文件名的“影片所在目录”。

`settings.json` 中的 API Key 为明文保存，仅供本机使用，请勿上传、提交或分享该文件。

## 主要功能

### 1. 删除演员头像

先扫描指定媒体库中存在 Primary 头像的演员，在输出列表确认后再执行删除。

需要特别注意：Emby 的 Person/演员对象是全局共享的。如果某演员同时存在于其他媒体库，删除该 Person 的 Primary 图片后，其他媒体库中的同一演员头像也会消失。

### 2. 扫描无演员影片

扫描指定媒体库中的 Movie；可选同时扫描 Video。判定逻辑为影片 `People` 中不存在 `Type=Actor` 的人物。

结果直接显示在 UI 表格中，并可导出 UTF-8 BOM CSV，方便 Excel 打开。列表和 CSV 同时包含完整“文件路径”和不含文件名的“影片所在目录”。

### 3. 重复人物与质检

该页面参考人物管理工具的对比式工作流，提供三个子页：

- **重复人物**：按共享 Provider ID、标准化姓名和资料完整度生成高置信候选；左侧展示候选，右侧并排比较 Person ID、关联影片、资料完整度、头像和 Provider IDs。
- **头像质量**：列出缺少 Primary 头像的人物，并显示关联影片数量和 Provider ID 数量。
- **资料冲突**：列出重复候选中同一 Provider 出现不同 ID 的冲突，便于在迁移前人工确认。

重复人物采用“迁移关联”方式处理：用户确认保留方向后，工具读取右侧人物关联影片的完整元数据，将对应 People 引用替换到左侧 Person，再更新回 Emby。**工具不会自动删除右侧 Person 实体**，迁移结束后建议重新扫描确认关系。

### 4. 删除导演信息

先列出包含 `Type=Director` 的影片。执行删除时：

1. 获取影片完整元数据；
2. 在 EXE 同目录的 `backups/` 下保存 JSON 备份；
3. 仅移除 `Director`；
4. 保留 Actor、Writer、Producer 等其他人物信息；
5. 更新回 Emby。

如果影片旁的 NFO 仍包含 `<director>`，以后刷新元数据时导演信息可能再次被导入。

## 开发运行

要求 Python 3.10+。

启动桌面 UI：

```bash
python emby_gui.py
```

CLI 仍保留：

```bash
python emby_batch.py --help
```

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 打包

Windows EXE 使用 PyInstaller：

```powershell
python -m pip install pyinstaller
# 先使用 ImageMagick 从 assets/emby.svg 生成标准多尺寸 Windows ICO：
magick -background none assets/emby.svg -define icon:auto-resize=256,128,64,48,40,32,24,20,16 assets/emby.ico
pyinstaller --clean --noconfirm --onefile --windowed `
  --icon assets/emby.ico `
  --add-data "assets/emby.png;assets" `
  --name EMBY-Doctor `
  emby_gui.py
```

项目的 GitHub Actions 会在 PR / main 上自动运行测试并构建 `EMBY-Doctor-Windows` EXE artifact；推送 `v*` tag 时自动生成 GitHub Release。

## License

MIT
