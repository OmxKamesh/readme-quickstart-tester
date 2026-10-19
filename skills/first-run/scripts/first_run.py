"""First Run: conservative, local quickstart evidence. Python 3.10+, stdlib only."""
import argparse
import hashlib
import html
import json
import os
import platform
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(value):
    if not isinstance(value, str):
        raise ValueError('path must be text')
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or '\\' in value or ':' in value:
        raise ValueError('paths must be relative POSIX paths without parent traversal')
    return p


def validate(c):
    if not isinstance(c, dict):
        raise ValueError('contract must be an object')
    if c.get('version') != 1 or not isinstance(c.get('steps'), list) or not c['steps']:
        raise ValueError('version 1 and nonempty steps required')
    ids = set()
    if c.get('phase', 'baseline') not in ('baseline', 'repair'):
        raise ValueError('phase must be baseline or repair')
    for s in c['steps']:
        if not isinstance(s, dict):
            raise ValueError('each step must be an object')
        if not isinstance(s.get('id'), str) or not s['id'] or s['id'] in ids:
            raise ValueError('unique string step ids required')
        ids.add(s['id'])
        if not isinstance(s.get('argv'), list) or not s['argv'] or not all(isinstance(a, str) and a and '\x00' not in a for a in s['argv']):
            raise ValueError('argv must be a nonempty string array')
        relative(s.get('cwd', '.'))
        src = s['source']
        if not isinstance(src, dict):
            raise ValueError('source must be an object')
        relative(src['path'])
        if type(src['line']) is not int or src['line'] < 1 or not isinstance(src['text'], str) or not src['text']:
            raise ValueError('source requires a positive line and exact text')
        if type(s.get('timeout', 15)) is not int or not 1 <= s.get('timeout', 15) <= 120:
            raise ValueError('timeout must be 1..120 seconds')
        if not isinstance(s.get('assert_stdout'), str) or not s['assert_stdout']:
            raise ValueError('nonempty assert_stdout required; exit zero alone is insufficient')
        if not isinstance(s.get('requirements', []), list) or not all(isinstance(x, str) for x in s.get('requirements', [])):
            raise ValueError('requirements must be a string array')
    return c


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def export(repo, root):
    """Copy HEAD blobs without checkout hooks, filters, symlinks or submodules."""
    actual_root = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    if actual_root != Path(repo).resolve():
        raise ValueError('repo must be the Git working tree root')
    commit = git(repo, 'rev-parse', '--verify', 'HEAD').decode().strip()
    for entry in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not entry:
            continue
        meta, raw = entry.split(b'\t', 1)
        mode, kind, oid = meta.decode().split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise ValueError('symlinks and submodules require manual isolated replay')
        target = root / relative(raw.decode('utf-8'))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(repo, 'cat-file', 'blob', oid))
        if mode == '100755':
            target.chmod(0o755)
    return commit


def replay(repo, contract, execute=False):
    validate(contract)
    result = {'version': 1, 'phase': contract.get('phase', 'baseline'),
              'environment': {'os': platform.system(), 'architecture': platform.machine(),
                              'helper_python': platform.python_version()},
              'contract_sha256': digest(json.dumps(contract, sort_keys=True).encode()),
              'status': 'blocked', 'steps': [], 'limitations': [
                  'Tracked HEAD export is not a security sandbox.',
                  'Local replay excludes clone transport, network services and dependency installation.',
                  'Output is hashed, not retained; inspect sensitive diagnostics privately.']}
    with tempfile.TemporaryDirectory(prefix='first-run-') as directory:
        root = Path(directory) / 'repo'
        root.mkdir()
        result['commit'] = export(repo, root)
        for s in contract['steps']:
            step_cwd = root / s.get('cwd', '.')
            executable_name = s['argv'][0]
            if '/' in executable_name or '\\' in executable_name:
                candidate = Path(executable_name)
                if not candidate.is_absolute():
                    candidate = step_cwd / candidate
                executable = str(candidate.resolve()) if candidate.is_file() else None
            else:
                executable = shutil.which(executable_name)
            evidence = {'id': s['id'], 'source': s['source'], 'argv': s['argv'],
                        'cwd': s.get('cwd', '.'), 'status': 'blocked', 'exit_code': None}
            result['steps'].append(evidence)
            source = root / relative(s['source']['path'])
            lines = source.read_text(encoding='utf-8').splitlines() if source.is_file() else []
            start = s['source']['line'] - 1
            expected = s['source']['text'].splitlines()
            reason = None
            if lines[start:start + len(expected)] != expected:
                reason = 'source citation no longer matches tracked documentation'
            elif s.get('requirements'):
                reason = 'unmet prerequisite or external requirement: ' + ', '.join(s['requirements'])
            elif not (root / s.get('cwd', '.')).is_dir():
                reason = 'documented working directory does not exist'
            elif not execute:
                reason = 'static-only: host approval / isolation review required'
            elif not executable:
                reason = 'executable prerequisite unavailable: ' + s['argv'][0]
            if reason:
                evidence['reason'] = reason
                break
            # No inherited tokens, HOME settings or runtime injection variables.
            # This is hygiene, NOT containment. Only run reviewed trusted code here.
            env = {k: v for k, v in os.environ.items() if k.upper() in ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT')}
            home = Path(directory) / 'home'
            home.mkdir(exist_ok=True)
            env.update(HOME=str(home), USERPROFILE=str(home), TMP=str(home), TEMP=str(home), TMPDIR=str(home))
            try:
                command = [executable, *s['argv'][1:]]
                p = subprocess.run(command, cwd=step_cwd, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=s.get('timeout', 15), shell=False)
                evidence.update(exit_code=p.returncode, stdout_sha256=digest(p.stdout), stderr_sha256=digest(p.stderr),
                                assertion_passed=s['assert_stdout'] in p.stdout.decode('utf-8', errors='replace'))
                evidence['status'] = 'verified' if p.returncode == 0 and evidence['assertion_passed'] else 'failed'
                if evidence['status'] == 'failed':
                    evidence['reason'] = 'command exit or success assertion failed'
            except subprocess.TimeoutExpired:
                evidence.update(status='failed', reason='timeout; process descendants may need host cleanup')
            except OSError as exc:
                evidence.update(status='blocked', reason='process could not start', os_error=exc.errno)
            if evidence['status'] != 'verified':
                break
        result['status'] = result['steps'][-1]['status']
    return result


def render(result):
    def safe(value):
        text = html.escape(str(value), quote=True)
        for char in '\\`[]()!|*_#~':
            text = text.replace(char, '&#' + str(ord(char)) + ';')
        return text.replace('\r', ' ').replace('\n', ' ')

    lines = ['# First Run — ' + result['status'].upper(), '',
             'Phase: ' + result['phase'], 'Commit: ' + result['commit'], '',
             '| Step | Source | Result | Exit |', '|---|---|---|---|']
    for s in result['steps']:
        src = s['source']
        lines.append('| ' + ' | '.join(safe(v) for v in
                     (s['id'], f"{src['path']}:{src['line']}", s['status'], s['exit_code'])) + ' |')
        if s.get('reason'):
            lines.extend(['', safe(s['reason']), ''])
    lines.extend(['', '## Limits', *['- ' + x for x in result['limitations']]])
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('repo', type=Path)
    p.add_argument('contract', type=Path)
    p.add_argument('--out', type=Path, required=True, help='new output directory outside target repo')
    p.add_argument('--execute-reviewed', action='store_true', help='use only after host approval; NOT permission or isolation')
    a = p.parse_args()
    if a.out.resolve().is_relative_to(a.repo.resolve()):
        p.error('output must be outside target repo')
    if a.out.exists():
        p.error('output must be new; preserve earlier evidence')
    try:
        result = replay(a.repo, json.loads(a.contract.read_text(encoding='utf-8')), a.execute_reviewed)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        p.error(str(exc))
    a.out.mkdir(parents=True)
    (a.out / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (a.out / 'report.md').write_text(render(result), encoding='utf-8')
    print(result['status'])
    return {'verified': 0, 'failed': 1, 'blocked': 2}[result['status']]


if __name__ == '__main__':
    raise SystemExit(main())
