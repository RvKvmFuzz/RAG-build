# 📊 AI Summary for KVM-RISCV Bug Learn Dataset

该脚本用于从 `learn-kvm-riscv-maillist` 知识库中提取学习文档，并按照 `BUG_TYPE` 分类，自动调用 LLM 总结高质量的修复经验与开发指南，最终生成汇总文档并上传到新的知识库。

---

## ✨ 功能概述

本工具实现了一个完整的自动化流程：

1. 📥 从源知识库获取所有学习文档
2. 🧩 解析文档结构（BUG_TYPE / PATCH / EXPERIENCE 等）
3. 📂 按 BUG_TYPE 分组
4. 🤖 调用 LLM 汇总经验，生成高级别技术指导
5. 💾 本地保存总结结果
6. ☁️ 上传总结文档到目标知识库并触发解析

---

## 🧠 总结内容包括

每个 BUG_TYPE 会生成三类核心指导：

* 如何修复这类 BUG（通用修复模式）
* PATCH 编写指南
* Commit Message 编写指南

---

## 📦 目录结构

```bash
.
├── ai_summary_from_learns.py
├── llm_api.key
└── output/
    └── summary-*.txt
```

---

## ⚙️ 环境依赖

* Python 3.8+
* 网络访问（RAGFlow API + LLM API）

---

## 🔐 环境变量配置

请先设置以下环境变量：

```bash
export RAGFLOW_API_URL="your_ragflow_url"
export RAGFLOW_API_KEY="your_ragflow_api_key"
```

---

## 🔑 LLM API Key

将你的 LLM API Key 存放在：

```bash
llm_api.key
```

文件内容示例：

```
your_llm_api_key
```

---

## 🚀 使用方法

### 基本用法

```bash
python3 ai_summary_from_learns.py <source_dataset_id>
```

---

### 指定目标知识库

```bash
python3 ai_summary_from_learns.py <source_dataset_id> \
    --target-dataset-id <target_id>
```

---

### 自动创建目标知识库

```bash
python3 ai_summary_from_learns.py <source_dataset_id> \
    --create-target
```

---

## 📌 参数说明

| 参数                    | 说明                        |
| ----------------------- | --------------------------- |
| `source_dataset_id`   | 源知识库 ID（learn 数据集） |
| `--target-dataset-id` | 目标知识库 ID               |
| `--create-target`     | 如果不存在则创建目标知识库  |

---

## 🧾 输入文档格式要求

每个 learn 文档需符合如下结构：

```
BUG_TYPE:
xxx

BUG_TRIGGER:
xxx

PATCH_FIX:
xxx

LEARNED_EXPERIENCES:
- 经验1
- 经验2

MAIL_ID:
xxx
```

---

## 📤 输出结果

### 本地文件

路径：

```
/root/.openclaw/workspace/summary-kvm-riscv-output/
```

文件格式：

```
summary_<BUG_TYPE>.txt
```

内容示例：

```
BUG_TYPE:
xxx

LEARN_IDS:
id1
id2

SUMMARY:
如何修复这类 BUG
- ...

PATCH 编写指南
- ...

Commit Message 编写指南
- ...
```

---

### 知识库内容

每个 BUG_TYPE 对应一个文档：

* 可检索
* 已自动 chunk + embedding
* 支持 RAG 查询

---

## 🔄 工作流程

```text
源知识库 (learn docs)
        ↓
解析 + 分组
        ↓
调用 LLM 总结
        ↓
生成 summary 文件
        ↓
上传目标知识库
        ↓
触发解析 (chunking)
```

---

## ⚠️ 注意事项

* 单个 BUG_TYPE 的经验数量过多时，仅取前 50 条参与总结
* LLM 调用超时设置为 300 秒
* 文档获取失败会自动跳过
* 上传失败不会中断整体流程

---

## 🛠 可扩展方向

* 支持增量更新（只处理新文档）
* 支持多模型对比总结
* 增加 summary 质量评估
* 自动生成知识图谱
* 前端可视化 BUG 类型分布

---

## 🧩 适用场景

* Kernel 开发经验沉淀
* Bug 修复模式归纳
* Patch 规范总结
* RAG 知识库构建
* AI 辅助代码审查
