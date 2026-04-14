#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 总结脚本：按 BUG_TYPE 汇总 learn-kvm-riscv-maillist

Usage:
    python3 ai_summary_from_learns.py <source_dataset_id> [--target-dataset-id <id>] [--create-target]
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path
from collections import defaultdict

# RAGFlow 配置
RAGFLOW_API_URL = os.environ.get('RAGFLOW_API_URL', 'url')
RAGFLOW_API_KEY = os.environ.get('RAGFLOW_API_KEY', 'key')

# LLM 配置
LLM_API_URL = 'url'
LLM_API_KEY_FILE = Path(__file__).parent.parent / 'llm_api.key'
LLM_MODEL = 'model'

# 输出目录
OUTPUT_DIR = Path('/root/.openclaw/workspace/summary-kvm-riscv-output')


def read_api_key(path: str) -> str:
    key = Path(path).read_text().strip()
    if not key:
        raise RuntimeError("API key file is empty")
    return key


def make_request(method: str, path: str, data: dict = None) -> dict:
    url = f"{RAGFLOW_API_URL.rstrip('/')}{path}"
    headers = {'Authorization': f'Bearer {RAGFLOW_API_KEY}'}
    
    if data is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(data).encode('utf-8')
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read().decode('utf-8'))
        if isinstance(result, dict) and result.get('code') == 0:
            return result.get('data', {})
        return result


def list_documents(dataset_id: str) -> list:
    url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets/{dataset_id}/documents?page=1&page_size=1000'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {RAGFLOW_API_KEY}'})
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
        if isinstance(result, dict) and 'data' in result:
            data = result['data']
            if isinstance(data, dict) and 'docs' in data:
                return data['docs']
        return []


def get_document_content(dataset_id: str, document_id: str) -> str:
    url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets/{dataset_id}/documents/{document_id}'
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {RAGFLOW_API_KEY}'})
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode('utf-8')
    except Exception as e:
        print(f"  获取文档内容失败：{e}")
        return ""


def call_llm(prompt: str) -> str:
    api_key = read_api_key(str(LLM_API_KEY_FILE))
    
    data = {
        'model': LLM_MODEL,
        'messages': [
            {'role': 'system', 'content': '你是一个 Linux Kernel KVM-RISCV 领域的专家，负责总结 BUG 修复经验。'},
            {'role': 'user', 'content': prompt}
        ],
        'temperature': 0.3,
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


def parse_learn_doc(content: str) -> dict:
    result = {
        'bug_type': '',
        'bug_trigger': '',
        'patch_fix': '',
        'experiences': [],
        'mail_id': '',
    }
    
    sections = content.split('\n\n')
    current_section = None
    
    for section in sections:
        lines = section.strip().split('\n')
        if not lines:
            continue
        
        header = lines[0].strip().rstrip(':')
        content_text = '\n'.join(lines[1:]).strip()
        
        if header == 'BUG_TYPE':
            result['bug_type'] = content_text
        elif header == 'BUG_TRIGGER':
            result['bug_trigger'] = content_text
        elif header == 'PATCH_FIX':
            result['patch_fix'] = content_text
        elif header == 'LEARNED_EXPERIENCES':
            result['experiences'] = [line.strip() for line in lines[1:] if line.strip().startswith('-')]
        elif header == 'MAIL_ID':
            result['mail_id'] = content_text
    
    return result


def summarize_bug_type(bug_type: str, learn_docs: list) -> str:
    """使用 AI 总结某个 BUG_TYPE 的所有经验"""
    all_experiences = []
    for doc in learn_docs:
        parsed = parse_learn_doc(doc['content'])
        if parsed['experiences']:
            all_experiences.extend(parsed['experiences'])
    
    prompt = f"""你是一个 Linux Kernel KVM-RISCV 领域的专家。你的任务是总结某个 BUG 类型的所有修复经验，生成高级别的指导建议。

## BUG 类型
{bug_type}

## 收集到的经验 ({len(all_experiences)} 条)
{chr(10).join(all_experiences[:50])}

## 任务
请总结这些经验，只输出以下三部分内容：

1. 如何修复这类 BUG - 修复时的通用模式和最佳实践
2. PATCH 编写指南 - 提交补丁时需要注意的事项
3. Commit Message 编写指南 - 如何撰写清晰的 commit message

## 输出要求
- 使用条理清晰的列表格式
- 每条建议应该具体、可操作
- 避免重复，合并相似的建议
- 保持专业、技术性的写作风格
- 用中文输出
- 不要使用 markdown 粗体标记（**text**），直接使用纯文本

## 输出格式
直接输出三部分内容，使用以下格式（不要加粗体标记）：

如何修复这类 BUG
- 建议 1
- 建议 2
...

PATCH 编写指南
- 指南 1
- 指南 2
...

Commit Message 编写指南
- 指南 1
- 指南 2
...
"""
    
    print(f"  调用 LLM 总结 {bug_type}...")
    response = call_llm(prompt)
    return response


def upload_document(dataset_id: str, file_path: str) -> str:
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
    
    url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets/{dataset_id}/documents'
    req = urllib.request.Request(url, data=bytes(body), headers=headers, method='POST')
    
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.loads(response.read().decode('utf-8'))
        if isinstance(result, dict) and result.get('code') == 0:
            return result['data'][0]['id']
        raise RuntimeError(f"Upload failed: {result}")


def trigger_parsing(dataset_id: str, document_id: str):
    make_request('POST', f'/api/v1/datasets/{dataset_id}/chunks', {
        'document_ids': [document_id],
    })


def main():
    parser = argparse.ArgumentParser(description='AI 总结脚本：按 BUG_TYPE 汇总 learn-kvm-riscv-maillist')
    parser.add_argument('source_dataset_id', help='源知识库 ID (learn-kvm-riscv-maillist)')
    parser.add_argument('--target-dataset-id', default=None, help='目标知识库 ID (summary-kvm-riscv-maillist)')
    parser.add_argument('--create-target', action='store_true', help='创建目标知识库')
    args = parser.parse_args()
    
    source_dataset_id = args.source_dataset_id
    
    print("="*70)
    print("AI 总结脚本：按 BUG_TYPE 汇总学习文档")
    print("="*70)
    print(f"源知识库：{source_dataset_id}")
    print()
    
    # Step 1: 创建或获取目标知识库
    target_dataset_id = args.target_dataset_id
    target_dataset_name = 'summary-kvm-riscv-maillist'
    
    if not target_dataset_id:
        if args.create_target:
            print(f"[Step 1] 创建新知识库 '{target_dataset_name}'...")
            result = make_request('POST', '/api/v1/datasets', {
                'name': target_dataset_name,
                'description': 'KVM-RISCV BUG 类型高级别总结知识库'
            })
            target_dataset_id = result.get('id', '')
            print(f"✅ 知识库创建成功，ID: {target_dataset_id}")
        else:
            print(f"[Step 1] 查找已存在的知识库 '{target_dataset_name}'...")
            try:
                url = f'{RAGFLOW_API_URL.rstrip("/")}/api/v1/datasets'
                req = urllib.request.Request(url, headers={'Authorization': f'Bearer {RAGFLOW_API_KEY}'})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode())
                    datasets = result.get('data', []) if isinstance(result, dict) else []
                
                for ds in datasets:
                    if isinstance(ds, dict) and ds.get('name', '').startswith(target_dataset_name):
                        target_dataset_id = ds.get('id')
                        print(f"✅ 找到已存在的知识库 '{ds.get('name')}', ID: {target_dataset_id}")
                        break
            except Exception as e:
                print(f"查找失败：{e}")
            
            if not target_dataset_id:
                print("❌ 未找到知识库，请使用 --create-target 创建")
                sys.exit(1)
    
    # Step 2: 获取源知识库所有文档
    print(f"\n[Step 2] 获取源知识库文档列表...")
    docs = list_documents(source_dataset_id)
    print(f"找到 {len(docs)} 个学习文档")
    
    # Step 3: 按 BUG_TYPE 分组
    print(f"\n[Step 3] 按 BUG_TYPE 分组...")
    bug_type_groups = defaultdict(list)
    
    for i, doc in enumerate(docs):
        doc_id = doc['id']
        doc_name = doc['name']
        
        content = get_document_content(source_dataset_id, doc_id)
        if not content:
            continue
        
        parsed = parse_learn_doc(content)
        bug_type = parsed['bug_type']
        
        if bug_type:
            bug_type_groups[bug_type].append({
                'doc_id': doc_id,
                'doc_name': doc_name,
                'content': content,
                'parsed': parsed,
            })
    
    print(f"共发现 {len(bug_type_groups)} 种 BUG 类型")
    for bug_type, doc_list in sorted(bug_type_groups.items(), key=lambda x: -len(x[1])):
        print(f"  - {bug_type}: {len(doc_list)} 个文档")
    
    # Step 4: 对每个 BUG_TYPE 生成总结
    print(f"\n[Step 4] 生成 BUG_TYPE 总结...")
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    summary_docs = []
    
    for bug_type, doc_list in sorted(bug_type_groups.items(), key=lambda x: -len(x[1])):
        print(f"\n  处理 {bug_type} ({len(doc_list)} 个文档)...")
        
        summary_text = summarize_bug_type(bug_type, doc_list)
        
        learn_ids = [doc['doc_id'] for doc in doc_list]
        
        summary_content = f"""BUG_TYPE:
{bug_type}

LEARN_IDS:
{chr(10).join(learn_ids)}

SUMMARY:
{summary_text}
"""
        
        output_file = OUTPUT_DIR / f"summary_{bug_type}.txt"
        output_file.write_text(summary_content)
        print(f"    已保存：{output_file}")
        
        summary_docs.append({
            'bug_type': bug_type,
            'learn_ids': learn_ids,
            'content': summary_content,
            'file': output_file,
        })
    
    # Step 5: 上传到目标知识库
    print(f"\n[Step 5] 上传总结文档到目标知识库...")
    
    uploaded_count = 0
    for summary_doc in summary_docs:
        try:
            print(f"  上传 {summary_doc['bug_type']}...")
            new_doc_id = upload_document(target_dataset_id, str(summary_doc['file']))
            print(f"    ✅ 上传成功，ID: {new_doc_id}")
            
            trigger_parsing(target_dataset_id, new_doc_id)
            uploaded_count += 1
        except Exception as e:
            print(f"    ❌ 上传失败：{e}")
    
    print(f"\n{'='*70}")
    print(f"处理完成!")
    print(f"  BUG 类型数：{len(bug_type_groups)}")
    print(f"  上传成功：{uploaded_count}/{len(summary_docs)}")
    print(f"  输出目录：{OUTPUT_DIR}")
    print(f"  目标知识库：{target_dataset_id}")
    print("="*70)


if __name__ == '__main__':
    main()
