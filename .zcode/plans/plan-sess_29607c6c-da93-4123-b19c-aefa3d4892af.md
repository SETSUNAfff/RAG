修复 Docker Hub 不可达导致的构建失败:配置国内镜像加速器

## 步骤

1. **修改 daemon.json**:备份后编辑 `C:\Users\27653\.docker\daemon.json`,加入:
```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.1panel.live",
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"
  ]
}
```
(保留原有内容,只追加 `registry-mirrors` 字段;三个加速器均已实测可达,按顺序尝试。)

2. **重启 Docker Desktop 使配置生效**:结束 Docker Desktop 进程后重新启动它,轮询 `docker version` 直到 daemon 恢复(约 30–60 秒)。
   - 若我直接改文件重启未生效,备选方案:请你在 Docker Desktop → Settings → Docker Engine 面板里粘贴上面的 JSON,点 Apply & Restart(GUI 是权威入口)。

3. **验证**:执行 `docker info` 确认出现 `Registry Mirrors` 段;执行 `docker pull python:3.12-slim` 确认能成功拉取。

4. **重新构建**:在 `G:\素材\work5\RAG` 执行 `docker build -t rag .`,确认原报错消失、镜像构建成功。

## 回退方案
若加速器拉取仍失败:换用 `https://hub.rat.dev`;或如果你本机有 Clash/VPN 代理,改在 Docker Desktop → Settings → Resources → Proxies 中配置代理地址(如 http://127.0.0.1:7890)。