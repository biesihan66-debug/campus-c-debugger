# 贡献指南

感谢你愿意改进 Campus C Debugger。

## 提交问题

- Bug 请使用 Bug 报告模板，并附上最小可复现 C 代码
- 功能建议请说明使用场景和预期行为
- 请勿在公开 Issue 中提交私人代码、密码、令牌或其他敏感信息

## 本地开发

1. 安装 Python 3.10 或更高版本。
2. 克隆仓库。
3. 运行 `python app.py`。
4. 修改后执行：

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py
```

## 自动修复规则要求

新增规则应当：

- 结果确定，不依赖猜测用户意图
- 只处理局部、机械性的错误
- 有正向和反向测试，避免误改正确代码
- 在无法确定时只报告，不自动修改

## Pull Request

- 一个 PR 只处理一个主题
- 清楚说明改动原因、行为变化和测试结果
- 界面修改请附日间与夜间模式截图
- 不要提交 `dist/`、`build/`、EXE、日志或本地配置文件
