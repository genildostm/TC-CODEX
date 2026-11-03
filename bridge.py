#!/usr/bin/env python3
"""Local Android bridge to the authenticated Codex CLI in Termux."""
import json
import os
import secrets
import shutil
import subprocess
import threading
import tempfile
import time
from uuid import uuid4
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = '127.0.0.1'
PORT = int(os.environ.get('TC_CODEX_BRIDGE_PORT', os.environ.get('CHAT_FACIL_BRIDGE_PORT', '8766')))
HOME = Path.home().resolve()
TOKEN_DIR = HOME / '.config' / 'tc-codex'
TOKEN_FILE = TOKEN_DIR / 'bridge-token'
LEGACY_TOKEN_FILE = HOME / '.config' / 'chat-facil' / 'bridge-token'
TOKEN_DIR.mkdir(parents=True, exist_ok=True)
if TOKEN_FILE.exists():
    PAIR_CODE = TOKEN_FILE.read_text(encoding='utf-8').strip()
elif LEGACY_TOKEN_FILE.exists():
    PAIR_CODE = LEGACY_TOKEN_FILE.read_text(encoding='utf-8').strip()
    TOKEN_FILE.write_text(PAIR_CODE, encoding='utf-8')
    TOKEN_FILE.chmod(0o600)
else:
    PAIR_CODE = secrets.token_urlsafe(24)
    TOKEN_FILE.write_text(PAIR_CODE, encoding='utf-8')
    TOKEN_FILE.chmod(0o600)
SHARED = Path('/storage/emulated/0')
DEFAULT_WORKSPACE = HOME / 'TC-Codex' / 'workspace'
DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT = HOME / 'storage' / 'downloads'
SESSIONS = {}
SESSIONS_LOCK = threading.Lock()
SESSION_LOCKS = {}
UPLOAD_ROOT = HOME / '.cache' / 'tc-codex' / 'uploads'
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
UPLOADS = {}
UPLOADS_LOCK = threading.Lock()
for stale_upload in UPLOAD_ROOT.iterdir():
    try:
        if time.time() - stale_upload.stat().st_mtime > 86400: shutil.rmtree(stale_upload, ignore_errors=True)
    except OSError: pass
MAX_APK_BYTES = 250 * 1024 * 1024
MAX_IMAGE_BYTES = 24 * 1024 * 1024
ALLOWED_UPLOADS = {'.apk', '.png', '.jpg', '.jpeg', '.webp', '.gif'}
PROTECTED_PATH = HOME / 'TC-Codex'
PROTECTED_NAMES = {'Android', 'DCIM', 'Pictures', 'Movies', 'Music', 'Alarms', 'Ringtones', 'Notifications'}


def allowed_workspace(value):
    raw = str(value or '').strip()
    if not raw:
        raise ValueError('Informe a pasta do projeto nas configurações do app.')
    path = Path(raw).expanduser().resolve(strict=True)
    shared = SHARED.resolve() if SHARED.exists() else SHARED
    if not path.is_dir():
        raise ValueError('A pasta escolhida não existe ou não é uma pasta.')
    if path in (HOME, shared, Path('/')):
        raise ValueError('Escolha uma pasta de projeto específica, não a raiz inteira.')
    if not (path.is_relative_to(HOME) or path.is_relative_to(shared)):
        raise ValueError('Por segurança, escolha uma pasta dentro da Home do Termux ou Downloads/armazenamento compartilhado.')
    return path


def allowed_output(value):
    raw = str(value or '').strip() or str(DEFAULT_OUTPUT)
    path = Path(raw).expanduser().resolve(strict=True)
    shared = SHARED.resolve() if SHARED.exists() else SHARED
    if not path.is_dir() or path in (HOME, shared, Path('/')):
        raise ValueError('A pasta de saída precisa existir e não pode ser a raiz inteira.')
    if not (path.is_relative_to(HOME) or path.is_relative_to(shared)):
        raise ValueError('Escolha uma pasta de saída na Home do Termux ou no armazenamento compartilhado.')
    if path == PROTECTED_PATH or PROTECTED_PATH in path.parents or any(part.startswith('.') for part in path.parts):
        raise ValueError('Essa pasta é protegida; escolha Downloads ou outra pasta comum.')
    return path


def allowed_location(value):
    raw = str(value or '').strip()
    path = Path(raw or str(HOME)).expanduser().resolve(strict=True)
    shared = SHARED.resolve() if SHARED.exists() else SHARED
    if not path.is_dir() or not (path == HOME or path.is_relative_to(HOME) or path == shared or path.is_relative_to(shared)):
        raise ValueError('Acesse somente pastas da Home do Termux ou do armazenamento compartilhado.')
    return path


def is_protected(path):
    try:
        relative = path.relative_to(HOME)
    except ValueError:
        try:
            relative = path.relative_to(SHARED.resolve() if SHARED.exists() else SHARED)
        except ValueError:
            return True
    return path == PROTECTED_PATH or PROTECTED_PATH in path.parents or any(part.startswith('.') or part in PROTECTED_NAMES for part in relative.parts)


def list_directory(path):
    entries = []
    try:
        children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        raise ValueError('O Termux não tem permissão para abrir esta pasta.')
    for child in children[:400]:
        if child.name.startswith('.') or child.is_symlink():
            continue
        try:
            is_dir = child.is_dir()
            if not is_dir and not child.is_file():
                continue
            entries.append({'name': child.name, 'path': str(child), 'directory': is_dir,
                            'size': 0 if is_dir else child.stat().st_size,
                            'can_delete': not is_protected(child.resolve()) and child.resolve() not in (HOME, SHARED)})
        except OSError:
            continue
    return entries


def delete_path(value, confirmed_name):
    target = Path(str(value or '')).expanduser()
    if target.is_symlink():
        raise ValueError('Não apago links simbólicos pelo app.')
    target = target.resolve(strict=True)
    parent = allowed_location(str(target.parent))
    shared = SHARED.resolve() if SHARED.exists() else SHARED
    if target in (HOME, shared, Path('/')) or target.name != str(confirmed_name or ''):
        raise ValueError('A confirmação não corresponde ao nome do item.')
    if is_protected(target) or target.name in PROTECTED_NAMES:
        raise ValueError('Este item é protegido pelo app ou pelo Android.')
    if not (target.is_relative_to(HOME) or target.is_relative_to(shared)):
        raise ValueError('O item está fora das pastas permitidas.')
    if not target.exists():
        raise ValueError('O item já não existe.')
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return str(parent)


def run_codex(workspace, session_id, prompt, image_paths=None, output_dir=None):
    codex = shutil.which('codex')
    if not codex:
        raise RuntimeError('Codex CLI não está instalado ou não está no PATH do Termux.')
    with SESSIONS_LOCK:
        saved = SESSIONS.get(session_id)
        lock = SESSION_LOCKS.setdefault(session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise RuntimeError('Já existe uma tarefa em andamento nesta conversa.')
    try:
        # exec resume accepts the session id and prompt after the subcommand;
        # common exec options must be parsed before the resume subcommand.
        command = [codex, 'exec', '--cd', str(workspace), '--approve-for-me', '--json', '--skip-git-repo-check']
        if output_dir and output_dir != workspace and not output_dir.is_relative_to(workspace):
            command += ['--add-dir', str(output_dir)]
        if saved and saved['workspace'] == str(workspace):
            command += ['resume']
            for image in image_paths or []: command += ['--image', str(image)]
            command += [saved['thread_id'], prompt]
        else:
            for image in image_paths or []: command += ['--image', str(image)]
            command += [prompt]
        proc = subprocess.run(command, cwd=str(workspace), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              timeout=1200, check=False)
        thread_id = saved['thread_id'] if saved and saved['workspace'] == str(workspace) else None
        answer = ''
        errors = []
        for line in proc.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get('type') == 'thread.started':
                thread_id = event.get('thread_id', thread_id)
            item = event.get('item', {})
            if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                answer = item.get('text', answer)
            if event.get('type') == 'error':
                errors.append(event.get('message', ''))
        if proc.returncode != 0:
            detail = '\n'.join(errors).strip() or proc.stderr.strip() or f'Codex terminou com código {proc.returncode}.'
            raise RuntimeError(detail[-3000:])
        if not thread_id:
            raise RuntimeError('Codex não retornou o identificador da conversa. Confira o Codex CLI no Termux.')
        with SESSIONS_LOCK:
            SESSIONS[session_id] = {'thread_id': thread_id, 'workspace': str(workspace)}
        return answer.strip() or 'A tarefa terminou, mas o Codex não retornou texto. Confira os arquivos na pasta do projeto.'
    except subprocess.TimeoutExpired:
        raise RuntimeError('A tarefa passou de 20 minutos e foi encerrada. Você pode pedir uma versão menor.')
    finally:
        lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'TCCodexBridge/1.0'
    def _authorized(self):
        return secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + PAIR_CODE)
    def _json(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', 'null')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()
        self.wfile.write(raw)
    def do_OPTIONS(self): self._json(204, {})
    def do_PUT(self): self.do_upload()
    def do_DELETE(self):
        route = urlparse(self.path).path
        prefix = '/api/upload/'
        if not route.startswith(prefix): self._json(404, {'error': 'Rota não encontrada.'}); return
        if not self._authorized(): self._json(401, {'error': 'Código de pareamento inválido.'}); return
        upload_id = route[len(prefix):]
        with UPLOADS_LOCK: item = UPLOADS.pop(upload_id, None)
        if not item: self._json(200, {'deleted': True}); return
        shutil.rmtree(Path(item['path']).parent, ignore_errors=True)
        self._json(200, {'deleted': True})
    def do_upload(self):
        if urlparse(self.path).path != '/api/upload': self._json(404, {'error': 'Rota não encontrada.'}); return
        if not self._authorized(): self._json(401, {'error': 'Código de pareamento inválido.'}); return
        upload_dir = None
        try:
            query = parse_qs(urlparse(self.path).query)
            workspace = allowed_workspace(query.get('workspace', [''])[0])
            session_id = query.get('session_id', [''])[0]
            name = Path(query.get('name', [''])[0]).name
            suffix = Path(name).suffix.lower()
            if not name or name in ('.', '..') or suffix not in ALLOWED_UPLOADS: raise ValueError('Envie uma imagem PNG/JPG/WEBP/GIF ou um APK.')
            if not session_id or len(session_id) > 80: raise ValueError('Conversa inválida.')
            length = int(self.headers.get('Content-Length', '0'))
            limit = MAX_APK_BYTES if suffix == '.apk' else MAX_IMAGE_BYTES
            if length < 1 or length > limit: raise ValueError('O arquivo está vazio ou ultrapassa o limite para este tipo de anexo.')
            now = time.time()
            with UPLOADS_LOCK:
                expired = [key for key, value in UPLOADS.items() if now - value.get('created_at', now) > 86400]
                expired_items = [UPLOADS.pop(key) for key in expired]
            for expired_item in expired_items: shutil.rmtree(Path(expired_item['path']).parent, ignore_errors=True)
            upload_id = uuid4().hex
            upload_dir = UPLOAD_ROOT / upload_id
            upload_dir.mkdir(parents=True, exist_ok=False)
            destination = upload_dir / name
            remaining = length
            with destination.open('wb') as stream:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk: raise ValueError('O envio do arquivo foi interrompido.')
                    stream.write(chunk)
                    remaining -= len(chunk)
            record = {'id': upload_id, 'session_id': session_id, 'workspace': str(workspace), 'path': str(destination), 'name': name, 'suffix': suffix, 'size': length, 'created_at': now}
            with UPLOADS_LOCK: UPLOADS[upload_id] = record
            self._json(200, {'id': upload_id, 'name': name, 'kind': 'image' if suffix != '.apk' else 'apk', 'size': length, 'session_id': session_id})
        except (ValueError, OSError) as error:
            if upload_dir: shutil.rmtree(upload_dir, ignore_errors=True)
            self._json(400, {'error': str(error)})
    def do_GET(self):
        route = urlparse(self.path)
        if not self._authorized(): self._json(401, {'error': 'Código de pareamento inválido.'}); return
        if route.path == '/api/files':
            try:
                requested = parse_qs(route.query).get('path', [str(HOME)])[0]
                folder = allowed_location(requested)
                self._json(200, {'path': str(folder), 'parent': str(folder.parent) if folder not in (HOME, SHARED.resolve() if SHARED.exists() else SHARED) else None, 'entries': list_directory(folder)})
            except (ValueError, OSError) as error: self._json(400, {'error': str(error)})
            return
        if route.path != '/api/status': self._json(404, {'error': 'Rota não encontrada.'}); return
        codex = shutil.which('codex')
        try:
            auth = subprocess.run([codex, 'login', 'status'], capture_output=True, text=True, timeout=12) if codex else None
            logged_in = bool(auth and auth.returncode == 0)
            self._json(200, {'connected': logged_in, 'codex': bool(codex), 'workspace': str(DEFAULT_WORKSPACE), 'output_dir': str(DEFAULT_OUTPUT), 'message': 'Codex conectado' if logged_in else 'Faça login no Codex CLI pelo Termux.'})
        except Exception:
            self._json(200, {'connected': False, 'codex': bool(codex), 'workspace': str(DEFAULT_WORKSPACE), 'output_dir': str(DEFAULT_OUTPUT), 'message': 'Não consegui consultar o Codex CLI.'})
    def do_POST(self):
        route = urlparse(self.path).path
        if route not in ('/api/chat', '/api/files/delete'): self._json(404, {'error': 'Rota não encontrada.'}); return
        if not self._authorized(): self._json(401, {'error': 'Código de pareamento inválido.'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length < 2 or length > 32000: raise ValueError('A solicitação está vazia ou grande demais.')
            data = json.loads(self.rfile.read(length))
            if route == '/api/files/delete':
                parent = delete_path(data.get('path'), data.get('confirmed_name'))
                self._json(200, {'deleted': True, 'parent': parent})
                return
            prompt = data.get('message')
            session_id = data.get('session_id')
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000: raise ValueError('Escreva uma mensagem com até 12.000 caracteres.')
            if not isinstance(session_id, str) or not (8 <= len(session_id) <= 80): raise ValueError('Identificador de conversa inválido.')
            workspace = allowed_workspace(data.get('workspace'))
            output_dir = allowed_output(data.get('output_dir'))
            attachment_ids = data.get('attachments', [])
            if not isinstance(attachment_ids, list) or len(attachment_ids) > 5: raise ValueError('Envie até cinco anexos por mensagem.')
            with UPLOADS_LOCK:
                attached = [UPLOADS.get(item) for item in attachment_ids]
            if any(not item or item['session_id'] != session_id or item['workspace'] != str(workspace) for item in attached):
                raise ValueError('Um anexo expirou ou pertence a outra conversa/pasta. Anexe-o novamente.')
            staged = Path(tempfile.mkdtemp(prefix='.tc-codex-attach-', dir=str(workspace))) if attached else None
            image_paths = []
            descriptions = []
            try:
                for index, item in enumerate(attached):
                    staged_path = staged / (str(index + 1) + '-' + item['name'])
                    shutil.copyfile(item['path'], staged_path)
                    descriptions.append(str(staged_path))
                    if item['suffix'] != '.apk': image_paths.append(staged_path)
                instruction = ('Atue como assistente de engenharia no projeto aberto em ' + str(workspace) + '. '
                    'Você pode inspecionar arquivos e executar ferramentas locais disponíveis para análise de código, APK e builds Android. '
                    'Trabalhe somente dentro da pasta do projeto, use a sandbox e não acesse nem revele segredos. '
                    'Não afirme que um build, teste, instalação ou análise terminou sem confirmar o resultado. '
                    'Responda em português brasileiro. Pedido do usuário:\n\n' + prompt.strip())
                instruction += '\n\nPasta padrão para salvar arquivos finais, APKs, imagens exportadas e relatórios: ' + str(output_dir) + '. Grave os arquivos finais novos nessa pasta. Mantenha alterações de código necessárias ao projeto dentro da pasta de trabalho e não copie arquivos do usuário sem necessidade.'
                if descriptions: instruction += '\n\nArquivos anexados para esta tarefa (temporários):\n' + '\n'.join(descriptions) + '\nAnalise esses arquivos conforme o pedido. Use os anexos como entrada e não os altere nem remova. Salve arquivos finais gerados na pasta de saída configurada; mantenha alterações de código necessárias dentro da pasta do projeto.'
                answer = run_codex(workspace, session_id, instruction, image_paths, output_dir)
                self._json(200, {'answer': answer})
            finally:
                if staged: shutil.rmtree(staged, ignore_errors=True)
                for item in attached:
                    if item:
                        with UPLOADS_LOCK: UPLOADS.pop(item['id'], None)
                        shutil.rmtree(Path(item['path']).parent, ignore_errors=True)
        except (ValueError, RuntimeError) as error: self._json(400, {'error': str(error)})
        except subprocess.TimeoutExpired: self._json(504, {'error': 'Codex demorou demais. Tente novamente.'})
        except Exception as error: self._json(500, {'error': str(error) or 'Erro inesperado no serviço local.'})
    def log_message(self, fmt, *args): print('[TC-Codex] ' + fmt % args)

if __name__ == '__main__':
    if not shutil.which('codex'):
        print('Aviso: Codex CLI não foi encontrado no PATH do Termux.')
    print(f'Bridge local em http://{HOST}:{PORT}')
    print(f'Código para parear o app: {PAIR_CODE}')
    print('Só aceite conexões do seu app. Pare com Ctrl+C.')
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
