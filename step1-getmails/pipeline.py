#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KVM-RISCV 邮件列表处理管道

流程:
1. 自动提取月份并下载
2. 合并为完整文件
3. 解析邮件并找 thread 根
4. 生成 thread mbox 文件
5. 按 base_subject 合并同一 patch 的不同版本
"""

import gzip
import json
import mailbox
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

BASE_DIR = Path("/root/.openclaw/workspace/kvm-riscv-mails")
RAW_DIR = BASE_DIR / "raw"
WORK_DIR = BASE_DIR / "work"
FACTS_DIR = BASE_DIR / "facts"
LOGS_DIR = BASE_DIR / "logs"

for d in [RAW_DIR, WORK_DIR, FACTS_DIR, LOGS_DIR]:
    d.mkdir(exist_ok=True, parents=True)

log_file = LOGS_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def log(msg, level="INFO"):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def log_step(step_num, step_name):
    log("=" * 70, "STEP")
    log(f"Step {step_num}: {step_name}", "STEP")
    log("=" * 70, "STEP")

def step1_download_months():
    """Step 1: 自动提取月份并下载"""
    log_step(1, "自动提取月份并下载 (month-files)")
    
    url = "https://lists.infradead.org/pipermail/kvm-riscv/"
    log("获取月份列表...", "INFO")
    
    try:
        result = subprocess.run(['curl', '-s', url], capture_output=True, text=True, timeout=30)
        html = result.stdout
        
        months = set()
        pattern = r'href="(\d{4}-[A-Z][a-z]+)\.txt\.gz"'
        for match in re.finditer(pattern, html):
            months.add(match.group(1))
        
        log(f"找到 {len(months)} 个月份", "INFO")
        
    except Exception as e:
        log(f"获取月份列表失败：{e}", "ERROR")
        months = set()
        for year in range(2020, 2027):
            for month in ['January', 'February', 'March', 'April', 'May', 'June', 
                         'July', 'August', 'September', 'October', 'November', 'December']:
                months.add(f"{year}-{month}")
        log(f"使用降级月份列表：{len(months)} 个", "WARN")
    
    downloaded = []
    failed = []
    
    for month in sorted(months):
        url = f"https://lists.infradead.org/pipermail/kvm-riscv/{month}.txt.gz"
        output = RAW_DIR / f"{month}.txt.gz"
        
        try:
            result = subprocess.run(['curl', '-s', '-o', str(output), url], capture_output=True, timeout=30)
            
            if result.returncode == 0 and output.exists() and output.stat().st_size > 1000:
                try:
                    with gzip.open(output, 'rb') as f:
                        f.read(100)
                    downloaded.append(month)
                    log(f"  ✓ {month}", "OK")
                except:
                    output.unlink()
                    failed.append(month)
                    log(f"  ✗ {month}: 无效文件", "ERROR")
            else:
                if output.exists():
                    output.unlink()
                failed.append(month)
                log(f"  ✗ {month}: 下载失败", "ERROR")
        except Exception as e:
            failed.append(month)
            log(f"  ✗ {month}: {e}", "ERROR")
    
    result = {
        'downloaded': downloaded,
        'failed': failed,
        'total_downloaded': len(downloaded),
        'total_failed': len(failed),
    }
    
    with open(WORK_DIR / "step1_download_result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    log(f"\n下载完成：{len(downloaded)} 成功，{len(failed)} 失败", "SUMMARY")
    return result

def step2_merge_to_whole():
    """Step 2: 合并为完整文件"""
    log_step(2, "合并为完整文件 (whole-file)")
    
    merged_count = 0
    output_file = WORK_DIR / "whole.mbox"
    
    with open(output_file, 'wb') as out_f:
        for mbox_file in sorted(RAW_DIR.glob("*.txt.gz")):
            month = mbox_file.stem.replace('.txt', '')
            log(f"合并 {month}...", "INFO")
            
            try:
                with tempfile.NamedTemporaryFile(suffix='.mbox', delete=False) as tmp:
                    tmp_path = tmp.name
                    with gzip.open(mbox_file, 'rb') as gz:
                        shutil.copyfileobj(gz, tmp)
                
                with open(tmp_path, 'rb') as tmp_f:
                    content = tmp_f.read()
                    out_f.write(content)
                
                mbox = mailbox.mbox(tmp_path)
                month_count = len(mbox)
                merged_count += month_count
                os.unlink(tmp_path)
                
                log(f"  ✓ {month}: {month_count} 封邮件", "OK")
            except Exception as e:
                log(f"  ✗ {month}: {e}", "ERROR")
    
    file_size = output_file.stat().st_size
    result = {
        'output_file': str(output_file),
        'file_size_bytes': file_size,
        'file_size_mb': round(file_size / (1024 * 1024), 2),
        'total_emails': merged_count,
    }
    
    with open(WORK_DIR / "step2_merge_result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    log(f"\n合并完成：{merged_count} 封邮件，{result['file_size_mb']} MB", "SUMMARY")
    return result

def get_email_body(msg):
    """获取邮件正文"""
    try:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode('utf-8', errors='replace')
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode('utf-8', errors='replace')
    except:
        pass
    return ""

def extract_fixes_commits(body):
    """提取 Fixes: commit hashes"""
    fixes = []
    for line in body.split('\n'):
        line = line.strip()
        if line.startswith('Fixes: '):
            match = re.match(r'Fixes:\s*([a-f0-9]+)', line, re.IGNORECASE)
            if match:
                fixes.append(match.group(1))
    return fixes

def find_thread_root(msg, all_msg_ids):
    """找到邮件所在 thread 的根邮件"""
    references = msg.get('References', '')
    ref_ids = re.findall(r'<[^>]+>', references)
    
    if ref_ids:
        root_id = ref_ids[0]
        if root_id in all_msg_ids:
            return root_id
        for ref_id in ref_ids:
            if ref_id in all_msg_ids:
                return ref_id
    
    in_reply_to = msg.get('In-Reply-To', '')
    if in_reply_to:
        return in_reply_to
    
    return msg.get('Message-ID', '')

def step3_extract_and_find_roots():
    """Step 3: 解析邮件并找 thread 根"""
    log_step(3, "解析邮件并找 thread 根")
    
    mbox_file = WORK_DIR / "whole.mbox"
    
    log("第一次遍历：收集所有 Message-ID...", "INFO")
    all_msg_ids = {}
    
    mbox = mailbox.mbox(str(mbox_file))
    for i, msg in enumerate(mbox):
        msg_id = msg.get('Message-ID', '')
        if msg_id:
            all_msg_ids[msg_id] = (i, msg)
    
    log(f"共 {len(all_msg_ids)} 封邮件", "INFO")
    
    log("第二次遍历：提取带 Fixes 的邮件并找根...", "INFO")
    
    fix_mails = []
    root_to_fixes = defaultdict(list)
    
    mbox = mailbox.mbox(str(mbox_file))
    for i, msg in enumerate(mbox):
        body = get_email_body(msg)
        fixes_commits = extract_fixes_commits(body)
        
        if fixes_commits:
            root_id = find_thread_root(msg, set(all_msg_ids.keys()))
            
            fix_mail = {
                'index': i,
                'from': msg.get('From', ''),
                'date': msg.get('Date', ''),
                'subject': msg.get('Subject', ''),
                'message_id': msg.get('Message-ID', ''),
                'root_message_id': root_id,
                'in_reply_to': msg.get('In-Reply-To', ''),
                'references': re.findall(r'<[^>]+>', msg.get('References', '')),
                'fixes_commits': fixes_commits,
            }
            fix_mails.append(fix_mail)
            root_to_fixes[root_id].append(len(fix_mails) - 1)
            
            if len(fix_mails) % 50 == 0:
                log(f"  已找到 {len(fix_mails)} 个带 Fixes 的邮件...", "PROGRESS")
    
    log(f"共 {len(fix_mails)} 个带 Fixes 的邮件", "INFO")
    log(f"共 {len(root_to_fixes)} 个不同的 thread 根", "INFO")
    
    result = {
        'total_mails': len(all_msg_ids),
        'fix_mails': len(fix_mails),
        'unique_roots': len(root_to_fixes),
    }
    
    with open(WORK_DIR / "fix-mails-with-roots.json", 'w', encoding='utf-8') as f:
        json.dump({
            'fix_mails': fix_mails,
            'root_to_fixes': dict(root_to_fixes),
        }, f, indent=2, ensure_ascii=False)
    
    with open(WORK_DIR / "step3_extract_result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    log(f"\n提取完成：{len(fix_mails)} 个带 Fixes 的邮件，{len(root_to_fixes)} 个 thread 根", "SUMMARY")
    return result, fix_mails, root_to_fixes, all_msg_ids

def step4_download_threads(fix_mails, root_to_fixes, all_msg_ids):
    """Step 4: 为每个 thread 生成 mbox 文件"""
    log_step(4, "生成 thread mbox 文件")
    
    mbox_file = WORK_DIR / "whole.mbox"
    mbox = mailbox.mbox(str(mbox_file))
    
    msg_id_to_msg = {}
    for msg in mbox:
        msg_id = msg.get('Message-ID', '')
        if msg_id:
            msg_id_to_msg[msg_id] = msg
    
    log("生成 thread mbox...", "INFO")
    thread_stats = []
    
    for root_id, fix_indices in root_to_fixes.items():
        thread_emails = []
        processed_ids = set()
        
        def collect(msg_id):
            if msg_id in processed_ids or not msg_id:
                return
            processed_ids.add(msg_id)
            
            if msg_id in msg_id_to_msg:
                thread_emails.append(msg_id_to_msg[msg_id])
                
                for other_id, other_msg in msg_id_to_msg.items():
                    in_reply_to = other_msg.get('In-Reply-To', '')
                    references = other_msg.get('References', '')
                    ref_ids = re.findall(r'<[^>]+>', references)
                    
                    if in_reply_to == msg_id or msg_id in ref_ids:
                        collect(other_id)
        
        collect(root_id)
        thread_emails.sort(key=lambda m: m.get('Date', ''))
        
        if thread_emails:
            first_fix = fix_mails[fix_indices[0]]
            base_subject = re.sub(r'^(Re|RE|Fw|FW):\s*', '', first_fix['subject'], flags=re.IGNORECASE)
            base_subject = re.sub(r'^\[(PATCH|RFC|GIT)[^\]]*\]\s*', '', base_subject, flags=re.IGNORECASE)
            base_subject = re.sub(r'^\[\d+/\d+\]\s*', '', base_subject).strip()
            
            safe_subject = re.sub(r'[^\w\s-]', '', base_subject)[:50]
            safe_subject = re.sub(r'\s+', '-', safe_subject).strip('-')
            if not safe_subject:
                safe_subject = f"thread-{root_id[:12]}"
            
            fixes_commits = first_fix['fixes_commits']
            fixes_key = fixes_commits[0] if fixes_commits else 'unknown'
            
            filename = f"{fixes_key[:12]}_{safe_subject}.mbox"
            filepath = FACTS_DIR / filename
            
            with open(filepath, 'wb') as f:
                for msg in thread_emails:
                    f.write(msg.as_bytes())
                    f.write(b'\n')
            
            thread_stats.append({
                'root_id': root_id,
                'filename': filename,
                'email_count': len(thread_emails),
                'fix_count': len(fix_indices),
                'fixes_commits': fixes_commits,
                'base_subject': base_subject,
            })
        
        if len(thread_stats) % 50 == 0:
            log(f"  已生成 {len(thread_stats)} 个 thread mbox...", "PROGRESS")
    
    with open(WORK_DIR / "thread-stats.json", 'w', encoding='utf-8') as f:
        json.dump(thread_stats, f, indent=2, ensure_ascii=False)
    
    result = {
        'total_threads': len(thread_stats),
        'output_dir': str(FACTS_DIR),
    }
    
    with open(WORK_DIR / "step4_download_result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    log(f"\n生成完成：{len(thread_stats)} 个 thread mbox", "SUMMARY")
    return result, thread_stats

def step5_merge_same_fix(thread_stats):
    """Step 5: 按 base_subject 合并同一 patch 的不同版本"""
    log_step(5, "合并同一 patch 的不同版本")
    
    # 只按 base_subject 分组（不管 fixes_commit）
    fix_groups = defaultdict(list)
    
    for thread in thread_stats:
        key = thread['base_subject']
        fix_groups[key].append(thread)
    
    log(f"共 {len(fix_groups)} 个不同的 patch", "INFO")
    
    merged_count = 0
    for key, threads in fix_groups.items():
        if len(threads) > 1:
            merged_count += 1
            log(f"  合并：{key[:50]}... ({len(threads)} 个 thread)", "INFO")
    
    merge_stats = []
    for base_subject, threads in fix_groups.items():
        all_fixes = set()
        for t in threads:
            all_fixes.update(t['fixes_commits'])
        
        merge_stats.append({
            'base_subject': base_subject,
            'fixes_commits': list(all_fixes),
            'thread_count': len(threads),
            'filenames': [t['filename'] for t in threads],
            'total_emails': sum(t['email_count'] for t in threads),
        })
    
    merge_stats.sort(key=lambda x: x['thread_count'], reverse=True)
    
    with open(WORK_DIR / "merge-stats.json", 'w', encoding='utf-8') as f:
        json.dump(merge_stats, f, indent=2, ensure_ascii=False)
    
    result = {
        'total_facts': len(fix_groups),
        'merged_facts': merged_count,
        'single_thread_facts': len(fix_groups) - merged_count,
    }
    
    with open(WORK_DIR / "step5_merge_result.json", 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    log(f"\n合并完成：{len(fix_groups)} 个 patch，{merged_count} 个需要合并", "SUMMARY")
    return result, merge_stats

def main():
    log("=" * 70)
    log("KVM-RISCV 邮件列表处理管道")
    log("=" * 70)
    log(f"开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"工作目录：{BASE_DIR}")
    
    step1_download_months()
    step2_merge_to_whole()
    result3, fix_mails, root_to_fixes, all_msg_ids = step3_extract_and_find_roots()
    result4, thread_stats = step4_download_threads(fix_mails, root_to_fixes, all_msg_ids)
    result5, merge_stats = step5_merge_same_fix(thread_stats)
    
    log("\n" + "=" * 70)
    log("处理完成！")
    log("=" * 70)
    log(f"结束时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
