# TC Codex

Aplicativo Android para conversar com o Codex CLI autenticado no Termux. O app usa uma ponte HTTP local no próprio aparelho; não precisa de chave da API OpenAI. O repositório também contém uma interface web experimental que usa a API separadamente.

## Instalar o app Android

1. No Android, baixe o [TC-Codex.apk](https://github.com/genildostm/TC-CODEX/raw/refs/heads/main/TC-Codex.apk) ou abra `TC-Codex.apk` na lista de arquivos do repositório e toque em **Download raw**.
2. Abra o APK baixado. Se o Android pedir, permita a instalação de apps pela origem que abriu o arquivo (por exemplo, navegador ou app Arquivos).
3. Volte ao instalador e toque em **Instalar**. Depois, abra **TC Codex**.

O app requer Android 6.0 (API 23) ou superior. A instalação é manual; o app não está na Play Store.

## Preparar o Termux e instalar o Codex

Instale o [Termux](https://termux.dev/) no mesmo aparelho e abra-o. Estes passos usam a adaptação comunitária [codex-termux](https://github.com/DioNanos/codex-termux), distribuída como [`@mmmbuto/codex-cli-termux`](https://www.npmjs.com/package/@mmmbuto/codex-cli-termux), mantida fora da OpenAI. A documentação oficial do [Codex CLI](https://developers.openai.com/codex/cli) não documenta um instalador para Android/Termux.

No Termux, rode:

```sh
pkg update && pkg upgrade -y
pkg install nodejs-lts python git -y
termux-setup-storage
npm install -g @mmmbuto/codex-cli-termux@latest
codex --version
codex login
```

Quando `termux-setup-storage` pedir, autorize o acesso aos arquivos compartilhados. Siga as instruções do Codex para autenticar uma conta compatível. Para usar o Codex diretamente no terminal, crie uma pasta e inicie-o:

```sh
mkdir -p ~/meu-app
cd ~/meu-app
codex
```

## Conectar o app ao Termux

O app Android precisa da ponte deste repositório. No Termux, clone o projeto (pule esta etapa se a pasta `~/TC-Codex` já existir):

```sh
git clone https://github.com/genildostm/TC-CODEX.git ~/TC-Codex
```

Inicie a ponte e mantenha o Termux aberto enquanto usa o app:

```sh
python ~/TC-Codex/bridge.py
```

Na primeira inicialização, copie o código de pareamento exibido no Termux. No TC Codex, toque em **Conectar Termux**, informe o código e escolha a pasta do projeto, por exemplo `~/meu-app` ou `~/storage/downloads/meu-projeto`.

O servidor escuta somente em `127.0.0.1` na porta `8766` por padrão. O código de pareamento fica em `~/.config/tc-codex/bridge-token`, com acesso privado ao usuário do Termux; remova esse arquivo para gerar outro código. Para encerrar a ponte, use Ctrl+C no Termux.

## Recursos

- Conversas com o Codex CLI usando a sessão autenticada do Termux.
- Histórico local de conversas, anexos de imagens e APKs.
- Navegação por arquivos e apps instalados, com confirmação do Android para desinstalações.
- APKs, relatórios e arquivos finais são salvos em `~/storage/downloads` por padrão. No menu **Arquivos**, você pode escolher outra pasta existente.

O Codex trabalha na pasta de projeto escolhida, usando o sandbox `workspace-write` e as aprovações do CLI. A pasta selecionada precisa estar na Home do Termux ou no armazenamento compartilhado. Para anexos, o limite é 24 MB por imagem e 250 MB por APK, com até cinco anexos por mensagem. APKs são copiados temporariamente para análise.

## Estrutura

- `bridge.py`: ponte local para o Codex CLI no Termux.
- `android/`: código Java, interface web embarcada, manifesto e recursos do app Android.
- `TC-Codex.apk`: APK pronto para instalação.
- `server.py`, `app.js`, `index.html` e arquivos relacionados: interface web experimental baseada na API OpenAI.

## Interface web experimental

Esta versão é separada do app Android e requer uma chave da API OpenAI com acesso e cobrança configurados. Execute-a somente localmente:

```sh
cd ~/TC-Codex
export OPENAI_API_KEY='sua-chave-aqui'
python server.py
```

Abra `http://127.0.0.1:8765`. A chave permanece na variável de ambiente da sessão do Termux; não a coloque no código nem a envie ao GitHub. A porta pode ser alterada com `TC_CODEX_PORT`.

## Código-fonte e compilação

O fonte Android está em `android/src`, `android/assets` e `android/res`. O manifesto declara Android 6.0 como versão mínima. A compilação depende de ferramentas e arquivos do ambiente Termux (`aapt`, `javac`, `dx`, `zipalign`, `apksigner`, `keytool`, `android.jar` e recursos do framework Android).

O script `workspace/build-android.sh` compila um aplicativo placeholder separado; ele não reproduz o APK TC Codex deste repositório. Os arquivos intermediários e keystores locais ficam ignorados pelo Git. Não publique seu keystore: sem ele, não é possível assinar uma atualização com a mesma identidade do APK já instalado.

## Segurança e privacidade

Não inclua tokens, chaves de API, dados de conversas ou keystores nos commits. O app comunica-se com a ponte por HTTP local e a ponte só escuta no loopback. A ponte inicia o Codex CLI com a pasta selecionada como diretório de trabalho; revise alterações sugeridas pelo Codex antes de usá-las.

## Licença

Nenhuma licença foi definida ainda. Sem uma licença, outras pessoas não recebem automaticamente permissão para redistribuir ou modificar este projeto. Adicione um arquivo `LICENSE` antes de aceitar contribuições ou declarar uma licença pública.
