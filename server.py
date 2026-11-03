#!/usr/bin/env python3
"""Servidor local para o Chat Fácil."""
import json, os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parent
HOST='127.0.0.1'
PORT=int(os.environ.get('CHAT_FACIL_PORT','8765'))
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_POST(self):
        if self.path!='/api/chat': self.send_error(404); return
        key=os.environ.get('OPENAI_API_KEY','').strip()
        if not key: self.send_json(503,{'error':'Configure OPENAI_API_KEY no Termux antes de iniciar o app.'}); return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<2 or length>100000: raise ValueError('A mensagem está vazia ou é grande demais.')
            messages=json.loads(self.rfile.read(length)).get('messages')
            if not isinstance(messages,list) or not messages or len(messages)>40: raise ValueError('Envie uma conversa válida com até 40 mensagens.')
            clean=[]
            for m in messages:
                role=m.get('role') if isinstance(m,dict) else None
                content=m.get('content') if isinstance(m,dict) else None
                if role not in ('user','assistant') or not isinstance(content,str): raise ValueError('Formato de mensagem inválido.')
                clean.append({'role':role,'content':content[:12000]})
            data=json.dumps({'model':os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),'input':clean,'instructions':'Responda em português brasileiro, com clareza e de forma útil.','store':False}).encode()
            req=Request('https://api.openai.com/v1/responses',data=data,headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},method='POST')
            with urlopen(req,timeout=90) as res: result=json.loads(res.read())
            self.send_json(200,{'answer':result.get('output_text','').strip() or 'Não recebi uma resposta em texto. Tente novamente.'})
        except ValueError as e: self.send_json(400,{'error':str(e)})
        except HTTPError as e:
            try: message=json.loads(e.read()).get('error',{}).get('message','')
            except Exception: message=''
            self.send_json(e.code,{'error':message or 'A API recusou a solicitação. Confira sua chave e os créditos da API.'})
        except (URLError,TimeoutError): self.send_json(502,{'error':'Não foi possível conectar à API. Confira sua internet e tente novamente.'})
        except Exception: self.send_json(500,{'error':'Ocorreu um erro inesperado ao processar a mensagem.'})
    def send_json(self,status,value):
        raw=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def log_message(self,fmt,*args): print('[chat-facil] '+fmt%args)
if __name__=='__main__':
    print(f'Chat Fácil disponível em http://{HOST}:{PORT}')
    print('Pare com Ctrl+C. A chave da API fica apenas nesta sessão do Termux.')
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
