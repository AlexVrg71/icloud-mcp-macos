#!/usr/bin/env python3
"""Source-release hygiene gate; prints only file/line/rule, never matched secrets.
This is not a complete secret detector or a security audit. Review all staged files.
"""
import argparse
import re
from pathlib import Path
import subprocess

SKIP = {'.git', '.venv', 'venv', '.build', 'build', 'dist', '__pycache__', '.pytest_cache'}
BANNED_SUFFIX = {'.log','.sqlite','.sqlite3','.db','.pem','.key','.p12','.pfx','.vcf','.ics','.eml','.mbox','.zip'}
RULES = {
    'absolute-personal-home': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+'),
    'private-network-host': re.compile(r'\b[a-z0-9-]+\.tail[a-z0-9]+\.ts\.net\b', re.I),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'provider-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})\b'),
    'aws-access-id': re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
}
EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b')
SAFE_EMAIL_DOMAINS = {'example.invalid','example.com','example.org','example.net','icloud.com'}


def candidates(root):
    if (root/'.git').is_dir():
        raw=subprocess.check_output(['git','-C',str(root),'ls-files','-z','--cached','--others','--exclude-standard'])
        return sorted({root/p for p in raw.decode().split('\0') if p})
    return sorted(p for p in root.rglob('*') if p.is_file() and not any(part in SKIP or part.endswith('.egg-info') for part in p.relative_to(root).parts))


def scan(root):
    findings=[];files=candidates(root)
    for path in files:
        rel=path.relative_to(root)
        if path.is_symlink():
            findings.append((str(rel),0,'symlink'));continue
        if (path.suffix.lower() in BANNED_SUFFIX or path.name in {'config.json','oauth_state.json','lists.json','overrides.json'}
            or path.name=='.env' or (path.name.startswith('.env.') and path.name!='.env.example')
            or any(p in {'data','logs','backups'} for p in rel.parts)):
            findings.append((str(rel),0,'private-runtime-file'))
        if path.suffix in {'.png','.ico'}:
            continue  # upstream licensed connector icons; inspect provenance separately
        try:text=path.read_text()
        except (UnicodeDecodeError,OSError):
            findings.append((str(rel),0,'unexpected-binary'));continue
        for line_no,line in enumerate(text.splitlines(),1):
            for name,pattern in RULES.items():
                if pattern.search(line):findings.append((str(rel),line_no,name))
            for match in EMAIL.finditer(line):
                domain=match.group(1).lower()
                if domain not in SAFE_EMAIL_DOMAINS and not domain.endswith('.invalid'):
                    findings.append((str(rel),line_no,'review-email-address'))
                elif domain=='icloud.com' and match.group(0).lower()!='you@icloud.com':
                    findings.append((str(rel),line_no,'review-icloud-address'))
    return files,findings


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',nargs='?',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    files,findings=scan(args.root.resolve())
    for path,line,rule in findings:print(f'{path}:{line}: {rule}')
    print(f'{len(files)} source files checked; {len(findings)} finding(s). Manual review is still required.')
    raise SystemExit(bool(findings))

if __name__=='__main__':main()
