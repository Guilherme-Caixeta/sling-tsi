# Sling TSi (PWA)

Porte de [`Leitor de Checklist.py`](../Leitor%20de%20Checklist.py) e
[`sling_tsi_wb.py`](../sling_tsi_wb.py) para o navegador. HTML, CSS e
JavaScript puros — sem Python, sem Flutter, sem compilação. Instala como
aplicativo no iPad e funciona sem rede.

```
web/
├── index.html              esqueleto da página
├── style.css               a paleta do planejador (#0d1117 / #161b22 / #e63329)
├── app.js                  navegação, telas do checklist e voz
├── wb.js                   peso & balanceamento: cálculo, envelope, folha A4
├── wb_screen.js            peso & balanceamento: a tela e os diálogos
├── manifest.webmanifest    nome, ícones e modo tela cheia
├── sw.js                   service worker: abre offline
├── data/
│   ├── Checklists-PB.json  cópia do arquivo da raiz do projeto
│   └── perfis_wb.json      perfis de fábrica (semente do localStorage)
├── assets/                 logotipo e ícones
└── tools/
    └── make_icons.py       gera os ícones a partir de Logo.png
```

## Testar no computador e no iPad

```bash
python web/tools/serve.py
```

Ele mostra dois endereços: um para o computador e outro para o iPad na mesma
rede Wi-Fi. Esse servidor manda `Cache-Control: no-store`, então cada
recarregamento pega o arquivo do disco — o `python -m http.server` não faz
isso, e o Safari acaba mostrando a versão antiga depois de uma alteração.

Precisa ser por HTTP: `file://` bloqueia o `fetch` do JSON e o service worker.

## Publicar

É um site estático — qualquer hospedagem serve (GitHub Pages, Netlify,
Cloudflare Pages, um diretório em qualquer servidor). Só duas exigências:

* **HTTPS** — sem isso o navegador não instala o PWA nem libera o microfone,
  e os comandos de voz ficam indisponíveis (a exceção é `localhost`). Servir
  por `http://` na rede local serve para conferir o layout, não para usar a
  escuta de comandos.
* servir a pasta `web/` inteira, preservando os caminhos relativos.

No iPad: abra o endereço no Safari e use **Compartilhar → Adicionar à Tela de
Início**. O app passa a abrir em tela cheia, com ícone próprio, e continua
funcionando sem rede depois da primeira carga.

## Voz

| Recurso | Como funciona | Onde |
| --- | --- | --- |
| Leitura em voz alta | `speechSynthesis` com voz pt-BR do sistema | Safari, Chrome, Edge, Firefox |
| Comandos de voz | `SpeechRecognition` (`webkitSpeechRecognition`) | **só em HTTPS** (ou `localhost`); onde não der, o botão **Ouvir** explica o motivo |

O reconhecimento devolve texto livre, então cada comando aceita as variações
que o pt-BR costuma transcrever: "xeque"/"cheque" contam como **check**,
"pula"/"próximo" como **pular**, "repete"/"de novo" como **repetir**.

Enquanto o aplicativo fala, o microfone é fechado e reaberto no fim da frase —
sem isso o reconhecedor ouviria a própria leitura e dispararia comandos
sozinho.

A velocidade da voz (−10 a +10, como no leitor do Windows) fica no
`localStorage`.

## Funcionar sem rede

O service worker guarda o aplicativo inteiro — página, estilos, scripts, o
`Checklists-PB.json` e os ícones — na primeira visita, e depois serve tudo do
cache. **Só que ele exige HTTPS**: por `http://` o navegador nem registra o
service worker, então o modo offline só existe depois de publicar.

O que continua valendo sem rede:

| Recurso | Sem rede |
| --- | --- |
| Checklists e leitura guiada | funciona |
| Peso & Balanceamento, perfis, folha A4 | funciona (tudo é calculado no aparelho) |
| Leitura em voz alta | funciona (vozes instaladas no aparelho) |
| **Comandos de voz** | **não funciona** — o reconhecimento do Safari e do Chrome é feito nos servidores deles |
| RedeMet e AISweb | não funciona (são sites externos); o app avisa em vez de abrir uma página em branco |

Duas defesas para o uso em voo:

* **Progresso do checklist** fica no `localStorage`. Se o iOS encerrar o app em
  segundo plano, os itens marcados voltam ao reabrir — sempre com um aviso
  visível na tela ("Itens marcados às 14:32 foram retomados") e um botão
  **Recomeçar**, e só dentro de 4 horas. Nunca em silêncio: um checklist
  marcado ontem não pode reaparecer como se fosse do voo de hoje.
* **Aviso de "sem rede"** aparece no rodapé quando o aparelho perde a conexão.

Instale o app na tela de início: o Safari limpa os dados de sites comuns não
visitados por alguns dias, mas não os de um app instalado.

## Peso & Balanceamento

As contas são as mesmas de `sling_tsi_wb.py` — comparei os dois lado a lado em
seis cenários (vazio, família, excesso de peso, só piloto, tanque seco no pouso
e braços editados) e os resultados batem até a terceira casa decimal, incluindo
os avisos de excesso e de CG fora dos limites.

* **Perfis** ficam no `localStorage`; na primeira visita são carregados de
  `data/perfis_wb.json`. Salvar, renomear e excluir funcionam como no
  aplicativo original.
* **Imprimir (A4 P&B)** monta a mesma folha do Tkinter e abre em outra aba,
  que já chama a impressão do navegador — é preciso permitir pop-ups. A folha
  sai a **92%** (`body { zoom: .92 }` no `PRINT_CSS`), o que garante uma
  página só mesmo com um perfil carregado e com o cabeçalho e o rodapé que o
  navegador acrescenta.
* O envelope é desenhado em SVG, no tamanho original de 630×400, e encolhe
  junto com a tela no celular.

## Atualizar o conteúdo

O `Checklists-PB.json` daqui é uma cópia. Depois de mudar o arquivo da raiz do
projeto:

```bash
cp Checklists-PB.json web/data/
```

E **suba o número da versão em dois lugares** — senão os aparelhos continuam
abrindo a cópia antiga:

| Onde | O que muda | Para quê |
| --- | --- | --- |
| `sw.js` | `const CACHE = 'sling-tsi-v6'` | refaz o cache offline do PWA instalado |
| `index.html` | `?v=6` nos `<script>` e no `<link>` | faz o navegador buscar o arquivo novo em vez do que ele guardou |

O `?v=` é o que resolve o caso mais comum: o app publicado continuar rodando
um JavaScript antigo mesmo depois de recarregar a página.

Para refazer os ícones depois de mudar o `Logo.png`:

```bash
python web/tools/make_icons.py
```

## Sobre os dados de fábrica

`data/Checklists-PB.json` e `data/perfis_wb.json` são cópias dos arquivos da
raiz do projeto. Depois de alterar os originais, copie-os para cá e suba a
versão do cache no `sw.js`. Os perfis que o piloto salvar no aparelho ficam no
`localStorage` e não são afetados pela cópia de fábrica.
