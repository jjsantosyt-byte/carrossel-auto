# Carrossel automático: Instagram + TikTok

Gera e publica sozinho 3 carrosséis por dia: **hook no 1º slide**, dicas nos do meio,
e **chamada para comprar o ebook no último**.

## Como funciona

1. `gerar.py` escreve o roteiro (do `conteudo/banco.yaml` ou pela IA do Claude), escolhe fundos
   (suas fotos em `fundos/`, Pexels ou degradê) e desenha os slides 1080x1350 em `saida/`.
2. `publicar.py` pega o próximo carrossel da fila e publica pelas **APIs oficiais**
   (Instagram API e TikTok Content Posting API).
3. `.github/workflows/carrossel.yml` roda tudo de graça no GitHub Actions:
   06:00 gera os 3 do dia; 08:00, 12:30 e 19:00 publica um.

Teste local: `pip install -r requirements.txt`, depois `python gerar.py --qtd 3`
e `python publicar.py --proximo --teste`.

## O que você precisa configurar (uma vez)

### 1. Produtos e marca
Edite `config.yaml`: em `produtos` coloque nome, tema, preço e **link de afiliado** de cada produto
(Hotmart, Kiwify, Eduzz), além do @perfil e das cores. Cada carrossel divulga o próximo produto
da lista. No `banco.yaml`, um roteiro com `produto: "Nome"` só sai para aquele produto.

**Link na bio:** o `gerar.py` cria `links/index.html`, uma página com um botão por produto.
Com o GitHub Pages ligado ela fica em `https://seuusuario.github.io/carrossel-auto/links/`;
ponha esse endereço na bio do Instagram e do TikTok. (Linktree também serve.)

### 2. Conteúdo
- **Sem custo:** escreva roteiros em `conteudo/banco.yaml` (já tem 3 exemplos).
- **Automático com IA:** mude `fonte_conteudo: "ia"` e crie uma chave em console.anthropic.com
  (segredo `ANTHROPIC_API_KEY`). Custo: centavos por carrossel.

### 3. Fundos
Coloque fotos em `fundos/` (Canva, Unsplash, Pexels) **ou** use `fonte_fundo: "pexels"`
com uma chave grátis de pexels.com/api (segredo `PEXELS_API_KEY`).

### 4. GitHub (onde o robô roda)
- Crie um repositório **público** com estes arquivos.
- Settings > Pages > publicar a partir da branch `main` (raiz). Isso gera a URL pública das imagens.
- Settings > Secrets and variables > Actions: variável `URL_PUBLICA`
  (ex.: `https://seuusuario.github.io/carrossel-auto`) e os segredos abaixo.

### 5. Instagram
- A conta precisa ser **Profissional** (Criador de conteúdo ou Empresa). É grátis, nas configurações do app.
- Em developers.facebook.com crie um app do tipo Business, adicione o produto
  **Instagram API com login do Instagram** e gere o token com a permissão
  `instagram_business_content_publish`.
- Segredos: `IG_USER_ID` e `IG_ACCESS_TOKEN` (o token dura 60 dias; renove antes de vencer).
- Para postar só na sua conta não precisa de aprovação da Meta.

### 6. TikTok
- Em developers.tiktok.com crie um app, adicione **Login Kit** e **Content Posting API**
  (escopo `video.publish`), e verifique o domínio/URL do GitHub Pages.
- Faça o login uma vez para obter o refresh token.
- Segredos: `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN`.
- **Atenção:** até o TikTok aprovar (auditar) seu app, os posts saem como **privados**.
  Você precisa pedir a auditoria no painel para postar público.

## Plano B sem programação
Ferramentas como Metricool, Buffer ou mLabs agendam carrosséis nos dois apps.
Você pode gerar os slides com `gerar.py` e só subir lá.
