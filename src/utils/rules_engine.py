import json
import re
from typing import Dict, Any, Tuple, Optional, List
from jinja2 import Template

def load_rules(path: str) -> Dict[str, Any]:
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def normalize(text: str) -> str:
    return (text or '').lower()

def match_rule(subject: str, body: str, rules: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    subject_l = normalize(subject)
    body_l = normalize(body)
    text = subject_l + "\n" + body_l

    for rule in rules.get('rules', []):
        mode = rule.get('match_mode', 'any').lower()
        kws = [k.lower() for k in rule.get('keywords', [])]
        if not kws:
            continue
        if mode == 'all':
            ok = all(k in text for k in kws)
        else:
            ok = any(k in text for k in kws)
        if ok:
            return rule.get('template'), rule.get('subject_prefix', '')
    # 不匹配则返回 None，外层不发送
    return None, None

def render_template(template_path: str, context: Dict[str, Any]) -> str:
    with open(template_path, encoding='utf-8') as f:
        tpl = Template(f.read())
    return tpl.render(**context)
