# 安全策略

## 支持版本

当前仅维护最新 Release。

## 报告安全问题

请优先使用 GitHub 的 Private vulnerability reporting。若仓库尚未启用该功能，请只创建标题为 `[SECURITY CONTACT REQUEST]` 的 Issue，不要在公开内容中描述可利用细节、密钥或私人代码。

## 安全边界

Campus C Debugger 会调用用户配置的 GCC 编译代码，但不会运行生成的程序。项目不承诺能安全分析来源不明的编译器、插件或被替换的可执行文件。
