import os
import re
import json
import argparse
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional

from dotenv import load_dotenv
from googleapiclient.errors import HttpError

from gmail_service import build_service, ensure_label, query_messages, get_message, send_reply, add_labels, modify_message
from utils.email_parser import extract_headers, extract_plain_and_html
from utils.rules_engine import load_rules, match_rule, render_template

def load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"replied_threads": []}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_state(path: str, state: dict):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def build_query_for_date() -> str:
    # 查询昨天 00:00 至 明天 00:00（不含）的未读且无用户标签邮件，即覆盖昨天与今天
    tz = os.getenv("TIMEZONE", "Asia/Singapore")
    today = datetime.now(ZoneInfo(tz)).date()
    start = (today - timedelta(days=1)).strftime('%Y/%m/%d')  # 昨天
    end = (today + timedelta(days=1)).strftime('%Y/%m/%d')    # 明天（before 为开区间）
    return f"after:{start} before:{end} is:unread has:nouserlabels"

def parse_sender(headers: dict) -> tuple[str,str]:
    # returns (name, email)
    from email.utils import parseaddr
    name, email = parseaddr(headers.get('From', ''))
    return (name or '').strip(), (email or '').strip()

def thread_has_label(service, thread_id: str, label_id: str) -> bool:
    # 检查会话内是否有任一消息已带指定标签
    try:
        thr = service.users().threads().get(userId='me', id=thread_id, format='minimal').execute()
    except Exception:
        return False
    for msg in thr.get('messages', []):
        if label_id in msg.get('labelIds', []):
            return True
    return False

def extract_rating_from_text(text: str) -> Optional[int]:
    # 提取评分数字，支持多种格式：RATING:1 / RATING：1 / rating = 1 / rating 1
    if not text:
        return None
    patterns = [
        r"\brating\s*[:：=]\s*([0-9])",
        r"\brating\s+([0-9])",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            try:
                value = int(m.group(1))
                return value
            except Exception:
                continue
    return None

def main():
    parser = argparse.ArgumentParser(description="Gmail Auto Reply Tool")
    parser.add_argument("--init-auth", action="store_true", help="Run OAuth flow only")
    parser.add_argument("--run", action="store_true", help="Run auto-reply once")
    parser.add_argument("--dry-run", action="store_true", help="Do not send emails")
    parser.add_argument("--date", type=str, help="Override date (YYYY-MM-DD)")
    args = parser.parse_args()

    load_dotenv()
    tz = os.getenv("TIMEZONE", "Asia/Singapore")
    include_labels = [l.strip() for l in os.getenv("INCLUDE_LABELS", "INBOX").split(",") if l.strip()]
    skip_senders = [s.strip().lower() for s in os.getenv("SKIP_SENDERS", "").split(",") if s.strip()]
    dry_run = args.dry_run or os.getenv("DRY_RUN", "false").lower() == "true"

    try:
        # 使用项目根目录下的 credentials.json 与 token.json（与本文件相对路径），避免因工作目录不同而找不到文件
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        credentials_path = os.path.join(project_root, "credentials.json")
        token_path = os.path.join(project_root, "token.json")
        service = build_service(credentials_path=credentials_path, token_path=token_path)
    except Exception as e:
        print("[ERROR] 构建 Gmail 服务失败：", e)
        return

    if args.init_auth and not args.run:
        print("OAuth 授权完成。")
        return

    # compute date in timezone
    if args.date:
        the_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        the_date = datetime.now(ZoneInfo(tz)).date()

    # load rules and state（提前加载，便于在查询中过滤已有业务标签的会话）
    rules = load_rules(os.path.join(os.path.dirname(__file__), "..", "data", "rules.json"))
    state_path = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")
    state = load_state(state_path)

    # 规则中的标签
    apply_label_name = rules.get("apply_label") or "莫名扣款"

    # 构建查询，并排除已打上业务标签的会话（如：莫名扣款）
    q = build_query_for_date() + f" -label:\"{apply_label_name}\""
    print(f"[INFO] 查询日期: {the_date}  查询语句: {q}  包含标签: {include_labels}")
    apply_label_id = ensure_label(service, apply_label_name)


    try:
        msgs = query_messages(service, q=q, include_labels=include_labels)
    except HttpError as e:
        print("[ERROR] 查询邮件失败：", e)
        return
    unique_threads = {m.get('threadId') for m in msgs if m.get('threadId')}
    print(f"[INFO] 匹配到 {len(msgs)} 封消息，{len(unique_threads)} 个未读邮件")


    for m in msgs:
        msg = get_message(service, m['id'])
        headers = extract_headers(msg['payload'])
        subject = headers.get('Subject', '(无主题)')
        thread_id = msg.get('threadId')
        # 若线程内已存在业务标签，跳过（保险：即便查询里已排除标签，这里再二次兜底）
        if thread_id and thread_has_label(service, thread_id, apply_label_id):
            print(f"[SKIP] 线程 {thread_id} 已含标签 {apply_label_name}，跳过。")
            continue
        if thread_id in state.get("replied_threads", []):
            print(f"[SKIP] 线程 {thread_id} 已自动回复过，跳过。")
            continue

        sender_name, sender_email = parse_sender(headers)
        if any(skip in sender_email.lower() for skip in skip_senders):
            print(f"[SKIP] 发件人 {sender_email} 在跳过列表。")
            continue

        plain, html = extract_plain_and_html(msg['payload'])
        body_text = plain or (html or '')
        template_path, subject_prefix = match_rule(subject, body_text, rules)
        if not template_path:
            # 扩展匹配评分：RATING:1 / RATING＝1 / rating = 1 / rating 1 等
            rating = extract_rating_from_text(body_text or '')
            if rating is not None:
                if rating == 1:
                    rating_label_id = ensure_label(service, '商城負評')
                    one_star_label_id = ensure_label(service, '一星')
                    if dry_run:
                        print(f"[DRY-RUN] 发件人 {sender_email} 评分={rating}，将为消息 {m['id']} 标记已读并加标签 ['商城負評','一星']")
                    else:
                        modify_message(service, msg_id=m['id'], add_label_ids=[rating_label_id, one_star_label_id], remove_label_ids=['UNREAD'])
                        print(f"[OK] 发件人 {sender_email} 评分=1，已标记已读并加标签（商城負評，一星），消息ID: {m['id']}")
                    continue
                if rating >= 3:
                    if dry_run:
                        print(f"[DRY-RUN] 发件人 {sender_email} 评分={rating}，将仅标记消息 {m['id']} 为已读")
                    else:
                        modify_message(service, msg_id=m['id'], add_label_ids=[], remove_label_ids=['UNREAD'])
                        print(f"[OK] 发件人 {sender_email} 评分>=3，已标记为已读，消息ID: {m['id']}")
                    continue
            print(f"[SKIP] 未匹配到规则，跳过发送。 线程:{thread_id} 发件人 {sender_email} 主题:{subject}")
            continue

        # build context
        context = {
            "sender_name": sender_name,
            "sender_email": sender_email,
            "subject": subject,
        }
        reply_body = render_template(os.path.join(os.path.dirname(__file__), "..", template_path), context)
        reply_subject = f"{subject_prefix}Re: {subject}" if subject_prefix else f"Re: {subject}"

        in_reply_to = headers.get('Message-Id') or headers.get('Message-ID') or headers.get('MessageId')

        print(f"[INFO] 准备回复 线程:{thread_id} 发件人:{sender_email} 主题:{reply_subject}")
        if dry_run:
            print("----- DRY RUN -----")
            print(reply_body)
            print("-------------------")
        else:
            try:
                resp = send_reply(service, thread_id=thread_id, to_addr=sender_email,
                                  subject=reply_subject, body_text=reply_body,
                                  in_reply_to=in_reply_to)
                # 标记原始邮件为已读并打标签（AutoReplied 与 配置标签）
                modify_message(service, msg_id=m['id'], add_label_ids=[apply_label_id], remove_label_ids=['UNREAD'])
                # mark thread replied
                state["replied_threads"].append(thread_id)
                save_state(state_path, state)
                print(f"[OK] 已回复并打标签，消息ID: {resp.get('id')}")
            except HttpError as e:
                print(f"[ERROR] 发送失败: {e}")

if __name__ == "__main__":
    main()
