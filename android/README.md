# TC Codex para Termux

O APK conversa com o Codex CLI autenticado no próprio Termux por uma ponte local. Ele não usa chave da API OpenAI.

## Usar o app

1. No Termux, confirme a autenticação com `codex login status`.
2. Inicie a ponte: `python ~/TC-Codex/bridge.py`.
3. Copie o código de pareamento mostrado no Termux.
4. No APK, toque em **Conectar Termux**, informe o código e escolha a pasta do projeto.
5. Mantenha o Termux aberto enquanto usa o app. Encerre a ponte com Ctrl+C.

O servidor escuta somente em `127.0.0.1`. O código de pareamento fica em `~/.config/tc-codex/bridge-token`; remova esse arquivo para gerar outro. O Codex trabalha na pasta de projeto escolhida, dentro do sandbox `workspace-write`. APKs, relatórios e arquivos finais são salvos em Downloads por padrão.

## APK e assinatura

O APK pronto para instalação está em [`../TC-Codex.apk`](../TC-Codex.apk). Identificador interno do Android é mantido para compatibilidade com instalações existentes; versão mínima: Android 6.0 (API 23). Para verificar a assinatura no Termux:

```sh
apksigner verify --verbose --print-certs TC-Codex.apk
zipalign -c -v 4 TC-Codex.apk
```

A impressão SHA-256 do certificado desta versão é `7efeb754bd0e4a64081be07b25e901002dee736ad5b0a29b2f24cfcfcfd76121`. Guarde a chave privada correspondente em local seguro e nunca a envie ao GitHub. O Android só aceita uma atualização sobre a instalação existente se ela for assinada pela mesma chave. A chave privada correspondente não está incluída neste repositório.

## Compilação

O fonte Android está em `src/`, `assets/` e `res/`. A compilação requer ferramentas e arquivos do ambiente Termux (`aapt`, `javac`, `dx`, `zipalign`, `apksigner`, `keytool`, `android.jar` e recursos do framework Android). O script `../workspace/build-android.sh` é apenas um build placeholder separado; não recria este APK TC Codex.
