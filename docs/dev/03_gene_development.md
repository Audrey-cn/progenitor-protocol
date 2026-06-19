# 基因开发规范

> 所属分类: concepts
> 生成时间: 2026-05-11

## 一、零依赖原则

**仅允许 Python 标准库**，禁止以下第三方库：

- `requests`、`pandas`、`numpy`、`BeautifulSoup`
- 任何 pip/conda 安装的包

## 二、文件格式

### 2.1 YAML 元数据头

格式 A — 注释行：
```python
# life_id: PGN@L1-G{number}-{GENE-NAME}
# creator: {name}
# description: {简要描述}
```

格式 B — 块状 YAML：
```python
"""
life_id: "PGN@L1-G{number}-{GENE-NAME}"
creator:
  name: "{name}"
description: "{简要描述}"
"""
```

### 2.2 命名规范

```
PGN@{Level}-{GeneNumber}-{GENE-NAME}
```

- Level: L1(基础) / L2(中级) / L3(高级)
- GeneNumber: 序列号 (G1, G2...)
- GENE-NAME: 大写功能名，连字符分隔

## 三、安全禁止清单

```python
eval()       # ❌ 禁止
exec()       # ❌ 禁止
__import__() # ❌ 禁止
os.system()  # ❌ 禁止
subprocess.* # ❌ 禁止
```

## 四、大小限制

- 单文件：最大 1MB
- 每次 PR：最多 5 个基因
- 每个创造者每天：最多 20 个基因

## 五、注册流程

1. 创建基因文件（含 YAML 元数据头）
2. 计算 SHA-256 → 重命名文件
3. 复制到 `genes/` 目录
4. 提交 PR
5. Gatekeeper CI 自动校验 (L0-L5)
6. 索引自动更新

---

[返回维基首页](../HOME.md)
