# Wasmer Edge 部署

把 LoL Radar Engine 部署到 [Wasmer Edge](https://wasmer.io/edge)，**完全免费的静态托管**，全球 CDN 边缘节点。

🌐 在线地址：<https://lol-radar-engine.wasmer.app/>

---

## 部署方式 A：仪表盘自动部署（推荐 / 看图示就是这条）

1. 登录 https://wasmer.io/dashboard
2. New App → Import from GitHub → 选 `RouZuoMong2003/lol-radar-engine`，分支 `main`
3. Configure Project 页面（你截图那个）按以下设置：

   | 字段 | 值 |
   |------|-----|
   | Owner | `rouzuomong2003` |
   | Project link | `lol-radar-engine` |
   | **Project preset** | **改成 `Static Website`**（**不要选 python**） |
   | Build Settings | **Build command 留空**，**Publish dir 填 `web`** |
   | Environment variables | 不需要 |
   | Enable Database | **关闭** |

4. Deploy → 等 1-2 分钟 → https://lol-radar-engine.wasmer.app/ 上线

> ⚠️ **为什么不选 `python`？**
> 仪表盘的 python preset 默认会跑 `pip install -r requirements.txt` + 起 WSGI，
> 我们的项目把所有数据都预生成进 `web/data/*.json` 了，前端会自动检测并走静态模式，
> 用 Python preset 反而会因 WeasyPrint 系统依赖编译失败。
> **静态托管秒级冷启动 + 零依赖，是最优解。**

---

## 部署方式 B：CLI（开发者）

```bash
# 1) 安装 wasmer-cli
curl https://get.wasmer.io -sSfL | sh

# 2) 登录
wasmer login

# 3) 在项目根目录直接部署
cd lol-radar-engine
wasmer deploy
```

`wasmer.toml` 与 `app.yaml` 已经在仓库里，CLI 会自动识别。

---

## 配置文件

| 文件 | 作用 |
|------|------|
| `wasmer.toml` | 声明 Wasmer 包 + 把 `web/` 挂到 `/public` + 用 static-web-server |
| `app.yaml` | Wasmer Edge App 元数据 |
| `wasmer/config.toml` | static-web-server 配置（缓存策略 / 安全头 / 压缩） |

---

## 自动化：push to deploy

Wasmer Edge 自带 GitHub 集成，**每次 push 到 main 都会自动重新部署**，无需 GitHub Actions。

如果仍想用 GitHub Actions 触发：

```yaml
- name: Deploy to Wasmer
  run: |
    curl https://get.wasmer.io -sSfL | sh
    export PATH="$HOME/.wasmer/bin:$PATH"
    wasmer deploy --token "${{ secrets.WASMER_TOKEN }}" --non-interactive
```

`WASMER_TOKEN` 在 https://wasmer.io/settings/access-tokens 申请。

---

## 排错

- **部署成功但页面 404**：检查 `Publish dir` 是不是 `web`，不是 `.`
- **JSON 加载失败 / CORS**：static-web-server 默认同源访问没问题；如果跨域加载，
  在 `wasmer/config.toml` 的 `[[advanced.headers]]` 里加 `"Access-Control-Allow-Origin" = "*"`
- **`?v=` 版本戳没生效**：Wasmer Edge 节点缓存约几分钟刷新一次，等等即可