# Contributing

1. 从 `main` 创建功能分支。
2. 修改代码并运行 `python -m unittest discover -s tests -v`。
3. 提交 Pull Request。
4. 等待 CI 的 Linux/Windows 测试与 Windows EXE smoke test 全部通过。
5. 合并到 `main`。
6. 创建 `vX.Y.Z` tag；Release workflow 会自动构建 Windows GUI EXE 并发布 GitHub Release。
