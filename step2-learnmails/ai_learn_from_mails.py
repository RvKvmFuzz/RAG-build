#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 学习脚本：从 kvm-riscv maillist 生成结构化知识

Usage:
    python3 ai_learn_from_mails.py <source_dataset_id> [--limit <n>]
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# RAGFlow 配置
RAGFLOW_API_URL = os.environ.get('RAGFLOW_API_URL', 'url')
RAGFLOW_API_KEY = os.environ.get('RAGFLOW_API_KEY', 'key')

# LLM 配置
LLM_API_URL = 'url'
LLM_API_KEY_FILE = Path(__file__).parent.parent / 'llm_api.key'  # 上一级目录
LLM_MODEL = 'model'

# BUG 类型分类
BUG_TYPES = [
    # 内存安全类
    'null_pointer_deref', 'use_after_free', 'memory_leak', 'out_of_bounds', 'invalid_memory_access',
    # 整数运算类
    'integer_overflow', 'integer_underflow', 'type_conversion', 'division_by_zero',
    # 并发竞争类
    'race_condition', 'missing_lock', 'deadlock', 'atomic_violation',
    # 逻辑错误类
    'incorrect_validation', 'off_by_one', 'wrong_condition', 'missing_check',
    # 资源管理类
    'resource_leak', 'double_free', 'uninitialized_var', 'wrong_cleanup_order',
    # API/接口类
    'wrong_api_usage', 'missing_error_check', 'incorrect_return_value', 'ABI_breaking',
    # 架构特定类
    'register_misuse', 'instruction_encoding', 'exception_handling', 'memory_ordering',
    # 文档/规范类
    'spec_violation', 'comment_mismatch', 'missing_documentation',
]

# ============================================================================
# Prompt 模板
# ============================================================================

LEARNING_PROMPT = """你是一个 Linux Kernel KVM-RISCV 领域的专家。你的任务是从邮件列表归档中提取 BUG 修复的关键信息，生成结构化的学习文档。

## 输入
你将收到一个邮件 thread 的内容，这个 thread 记录了为了修复某个 KVM-RISCV BUG，contributor 和 reviewer/maintainer 之间的交流和沟通。

## 任务
从邮件内容中提取以下 5 个关键信息：

### 1. BUG_TYPE (BUG 类型)
从以下分类中选择最匹配的一个：
{bug_types}

### 2. BUG_TRIGGER (BUG 如何触发)
用**一句话**描述 BUG 是如何触发的。包括：
- 什么操作/调用触发了 BUG
- 什么输入条件导致了问题
- 最终表现是什么 (如 Oops, crash, panic 等)

### 3. PATCH_FIX (PATCH 如何修复)
用**一句话**描述 PATCH 是如何修复这个 BUG 的。包括：
- 修改了哪个函数/代码
- 具体做了什么改动
- 如何解决了问题

### 4. LEARNED_EXPERIENCES (学习到的经验)
从邮件沟通历史中提取经验，**一条一条列出**，可以包括：
- 代码编写规范要求
- commit message 编写规范要求
- maintainer/reviewer 看重的内容
- 这类 BUG 需要额外关注哪些内容
- 如何修复这类 BUG
- reviewer 的反馈和建议
- 维护者流程

每条经验用 `[标签] 内容` 的格式，如：
- [验证逻辑] 当验证涉及加法运算时，必须先单独检查每个操作数，防止整数溢出绕过验证
- [fuzzing 发现] 这个 BUG 是通过 fuzzing 发现的，说明 fuzzing 对发现边界条件 BUG 非常有效
- [commit message 规范] commit message 必须包含详细的 crash call trace 和根本原因分析
- [reviewer 关注点] reviewer 会确认 BUG 触发场景是否清晰、修复是否最小化、是否有副作用

### 5. MAIL_ID (源文档 ID)
源邮件文档在 kvm-riscv-maillist 知识库中的 ID (格式如：f234a56c37a111f191df666b12656a28)

## 输出格式
**严格**按照以下格式输出，不要有任何额外的解释、前言或后语：

```
BUG_TYPE:
<选择的 BUG 类型>

BUG_TRIGGER:
<一句话描述>

PATCH_FIX:
<一句话描述>

LEARNED_EXPERIENCES:
- [标签] 经验内容 1
- [标签] 经验内容 2
- [标签] 经验内容 3
...

MAIL_ID:
<源文档 ID>
```

## 注意事项
1. BUG_TYPE 必须从预定义列表中选择
2. BUG_TRIGGER 和 PATCH_FIX 必须简洁，各用一句话
3. LEARNED_EXPERIENCES 至少列出 3 条经验
4. MAIL_ID 是源文档在知识库中的 ID，不是邮件的 Message-ID
5. 如果某些信息在邮件中找不到，用 `[待补充]` 标记

## 邮件内容
{mail_content}
"""

# ============================================================================
# RAGFlow API 函数
# ============================================================================

def make_request(method: str, path: str, data: Optional[dict] = None, files: bool = False) -> Any:
    """发送 HTTP 请求到 RAGFlow API"""
    url = f"{RAGFLOW_API_URL.rstrip('/')}{path}"
    
    headers = {
        'Authorization': f'Bearer {RAGFLOW_API_KEY}',
    }
    
    if files:
        # multipart/form-data 由调用者构造
        pass
    elif data is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read()
            if not body:
                return {}
            result = json.loads(body.decode('utf-8'))
            # RAGFlow API 返回 {'code': 0, 'data': ...}
            if isinstance(result, dict):
                if result.get('code') == 0:
                    return result.get('data', {})
                return result  # 返回原始响应以便调用者处理错误
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"HTTP Error {e.code}: {body[:200]}")
        raise
    except Exception as e:
        print(f"Request failed: {e}")
        raise


def create_dataset(name: str, description: str = '') -> str:
    """创建知识库"""
    result = make_request('POST', '/api/v1/datasets', {
        'name': name,
        'description': description,
    })
    if not isinstance(result, dict):
        raise RuntimeError(f"Unexpected response: {result}")
    return result.get('id', '')


def list_documents(dataset_id: str, page: int = 1, page_size: int = 100) -> list:
    """列出知识库中的文档"""
    # 直接调用 API
    url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets/{dataset_id}/documents?page={page}&page_size={page_size}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {RAGFLOW_API_KEY}'})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            # Structure: {'code': 0, 'data': {'docs': [...], 'total': N}}
            if isinstance(result, dict) and 'data' in result:
                data = result['data']
                if isinstance(data, dict) and 'docs' in data:
                    return data['docs']
            return []
    except Exception as e:
        print(f"List documents failed: {e}")
        return []


def get_document_content(dataset_id: str, document_id: str) -> str:
    """获取文档的完整内容"""
    # 直接调用 API 获取文档内容
    url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets/{dataset_id}/documents/{document_id}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {RAGFLOW_API_KEY}'})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content = resp.read().decode('utf-8')
            return content
    except Exception as e:
        print(f"Get document content failed: {e}")
        return ""


def upload_document(dataset_id: str, file_path: str) -> str:
    """上传文档到知识库"""
    import uuid
    
    boundary = '----OpenClawBoundary' + uuid.uuid4().hex
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    filename = os.path.basename(file_path)
    
    body = bytearray()
    body.extend(f'--{boundary}\r\n'.encode())
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode())
    body.extend('Content-Type: text/plain\r\n\r\n'.encode())
    body.extend(content)
    body.extend(b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())
    
    headers = {
        'Authorization': f'Bearer {RAGFLOW_API_KEY}',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
    }
    
    url = f'{RAGFLOW_API_URL.rstrip()}/api/v1/datasets/{dataset_id}/documents'
    req = urllib.request.Request(url, data=bytes(body), headers=headers, method='POST')
    
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read().decode('utf-8'))
        if isinstance(result, dict) and result.get('code') == 0:
            return result['data'][0]['id']
        raise RuntimeError(f"Upload failed: {result}")


def trigger_parsing(dataset_id: str, document_id: str):
    """触发文档解析"""
    make_request('POST', f'/api/v1/datasets/{dataset_id}/chunks', {
        'document_ids': [document_id],
    })


# ============================================================================
# LLM 调用函数
# ============================================================================

def read_api_key(path: str) -> str:
    """从文件读取 API key"""
    key = Path(path).read_text().strip()
    if not key:
        raise RuntimeError("API key file is empty")
    return key


def call_llm(prompt: str) -> str:
    """调用 LLM 生成响应 (使用 OpenAI 兼容 API)"""
    import urllib.request
    import json
    
    # 读取 API key
    api_key = read_api_key(str(LLM_API_KEY_FILE))
    
    data = {
        'model': LLM_MODEL,
        'messages': [
            {'role': 'system', 'content': '你是一个 Linux Kernel KVM-RISCV 领域的专家，负责从邮件列表归档中提取 BUG 修复的关键信息。'},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.2,
    }
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    
    req = urllib.request.Request(
        LLM_API_URL,
        data=json.dumps(data).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    
    with urllib.request.urlopen(req, timeout=300) as response:
        result = json.loads(response.read().decode('utf-8'))
        return result['choices'][0]['message']['content']


# ============================================================================
# 学习文档生成
# ============================================================================

def extract_learning_info(mail_content: str, document_id: str) -> str:
    """使用 LLM 从邮件内容中提取学习信息"""
    prompt = LEARNING_PROMPT.format(
        bug_types=', '.join(BUG_TYPES),
        mail_content=mail_content[:15000]  # 限制长度
    )
    
    print(f"  调用 LLM...")
    response = call_llm(prompt)
    
    # 后处理：确保包含 MAIL_ID
    if 'MAIL_ID:' not in response:
        response += f"\n\nMAIL_ID:\n{document_id}"
    elif document_id not in response:
        # 替换可能错误的 MAIL_ID
        lines = response.split('\n')
        new_lines = []
        in_mail_id = False
        for line in lines:
            if line.strip() == 'MAIL_ID:':
                in_mail_id = True
                new_lines.append(line)
            elif in_mail_id and line.strip():
                new_lines.append(document_id)
                in_mail_id = False
            else:
                new_lines.append(line)
        response = '\n'.join(new_lines)
    
    return response


def parse_llm_response(response: str) -> dict:
    """解析 LLM 响应，验证格式"""
    result = {
        'bug_type': '',
        'bug_trigger': '',
        'patch_fix': '',
        'experiences': [],
        'mail_id': '',
        'raw': response,
    }
    
    sections = response.split('\n\n')
    current_section = None
    
    for section in sections:
        lines = section.strip().split('\n')
        if not lines:
            continue
        
        header = lines[0].strip().rstrip(':')
        content = '\n'.join(lines[1:]).strip()
        
        if header == 'BUG_TYPE':
            result['bug_type'] = content
        elif header == 'BUG_TRIGGER':
            result['bug_trigger'] = content
        elif header == 'PATCH_FIX':
            result['patch_fix'] = content
        elif header == 'LEARNED_EXPERIENCES':
            result['experiences'] = [line.strip() for line in lines[1:] if line.strip().startswith('-')]
        elif header == 'MAIL_ID':
            result['mail_id'] = content
    
    return result


# ============================================================================
# 主流程
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='AI 驱动的学习脚本：从 kvm-riscv maillist 中学习')
    parser.add_argument('source_dataset_id', help='源知识库 ID (kvm-riscv maillist)')
    parser.add_argument('--limit', type=int, default=2, help='处理文档数量限制 (默认：2 个用于测试)')
    parser.add_argument('--start', type=int, default=0, help='起始索引')
    parser.add_argument('--create-dataset', action='store_true', help='创建新知识库')
    args = parser.parse_args()
    
    source_dataset_id = args.source_dataset_id
    limit = args.limit
    start_index = args.start
    
    print("="*70)
    print("AI 学习脚本：从 kvm-riscv maillist 中学习")
    print("="*70)
    print(f"源知识库：{source_dataset_id}")
    print(f"处理数量：{limit} 个文档")
    print(f"起始索引：{start_index}")
    print()
    
    # Step 1: 创建或获取目标知识库
    # 使用已存在的知识库 ID
    target_dataset_id = 'b23c5d7637b311f1a718666b12656a28'
    target_dataset_name = 'learn-kvm-riscv-maillist'
    print(f"[Step 1] 使用知识库 '{target_dataset_name}' (ID: {target_dataset_id})")
    
    if False and args.create_dataset:  # 禁用自动创建，使用硬编码 ID
        print(f"[Step 1] 创建新知识库 '{target_dataset_name}'...")
        try:
            target_dataset_id = create_dataset(
                target_dataset_name,
                '从 kvm-riscv 邮件列表中学习到的结构化 BUG 修复知识'
            )
            print(f"✅ 知识库创建成功，ID: {target_dataset_id}")
        except Exception as e:
            print(f"❌ 创建失败：{e}")
            print("尝试使用已存在的知识库...")
            target_dataset_id = None
    
    if not target_dataset_id:
        # 尝试查找已存在的知识库
        print(f"[Step 1] 查找已存在的知识库 '{target_dataset_name}'...")
        try:
            # 直接调用 API
            url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets'
            req = urllib.request.Request(url, headers={'Authorization': f'Bearer {RAGFLOW_API_KEY}'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                if isinstance(result, dict) and 'data' in result:
                    datasets = result['data'] if isinstance(result['data'], list) else []
                else:
                    datasets = []
            
            for ds in datasets:
                if not isinstance(ds, dict):
                    continue
                ds_name = ds.get('name', '')
                # 支持模糊匹配
                if ds_name.startswith(target_dataset_name):
                    target_dataset_id = ds.get('id')
                    print(f"✅ 找到已存在的知识库 '{ds_name}', ID: {target_dataset_id}")
                    break
        except Exception as e:
            print(f"查找失败：{e}")
        
        if not target_dataset_id:
            print("❌ 未找到知识库，请使用 --create-dataset 创建")
            sys.exit(1)
    
    # Step 2: 获取源知识库文档列表
    print(f"\n[Step 2] 获取源知识库文档列表...")
    print(f"  Calling list_documents({source_dataset_id})...")
    docs = list_documents(source_dataset_id, page=1, page_size=1000)
    print(f"  Returned {len(docs)} documents")
    print(f"找到 {len(docs)} 个文档")
    
    if start_index >= len(docs):
        print(f"起始索引 {start_index} 超出范围")
        sys.exit(1)
    
    docs_to_process = docs[start_index:start_index + limit]
    print(f"将处理 {len(docs_to_process)} 个文档 (索引 {start_index} 到 {start_index + limit - 1})")
    
    # Step 3: 逐个处理文档
    output_dir = Path('/root/.openclaw/workspace/learn-kvm-riscv-output')
    output_dir.mkdir(exist_ok=True)
    
    processed_count = 0
    error_count = 0
    
    for i, doc in enumerate(docs_to_process):
        doc_id = doc['id']
        doc_name = doc['name']
        
        print(f"\n{'='*70}")
        print(f"[文档 {i+1}/{len(docs_to_process)}] {doc_name[:60]}...")
        print(f"  ID: {doc_id}")
        
        try:
            # 获取文档内容
            print(f"  获取文档内容...")
            mail_content = get_document_content(source_dataset_id, doc_id)
            if not mail_content:
                print(f"  ⚠️  没有获取到内容，跳过")
                error_count += 1
                continue
            
            print(f"  内容长度：{len(mail_content)} 字符")
            
            # 调用 LLM 提取信息
            learning_content = extract_learning_info(mail_content, doc_id)
            
            # 解析并验证
            parsed = parse_llm_response(learning_content)
            print(f"  提取结果:")
            print(f"    BUG_TYPE: {parsed['bug_type'][:50] if parsed['bug_type'] else 'N/A'}...")
            print(f"    MAIL_ID: {parsed['mail_id']}")
            print(f"    经验条数：{len(parsed['experiences'])}")
            
            # 保存学习文档
            output_file = output_dir / f"learn_{doc_name}"
            output_file.write_text(learning_content)
            print(f"  已保存：{output_file}")
            
            # 上传到目标知识库
            print(f"  上传到目标知识库...")
            new_doc_id = upload_document(target_dataset_id, str(output_file))
            print(f"  ✅ 上传成功，新文档 ID: {new_doc_id}")
            
            # 触发解析
            print(f"  触发解析...")
            trigger_parsing(target_dataset_id, new_doc_id)
            print(f"  ✅ 解析任务已提交")
            
            processed_count += 1
            
        except Exception as e:
            print(f"  ❌ 处理失败：{e}")
            error_count += 1
            import traceback
            traceback.print_exc()
    
    # 总结
    print(f"\n{'='*70}")
    print(f"处理完成!")
    print(f"  成功：{processed_count} 个")
    print(f"  失败：{error_count} 个")
    print(f"  输出目录：{output_dir}")
    print(f"  目标知识库：{target_dataset_id}")
    print("="*70)


if __name__ == '__main__':
    main()
