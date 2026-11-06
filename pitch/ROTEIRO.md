# Roteiro do pitch: 5 minutos

**Material:** [deck.html](deck.html) aberto no navegador em tela cheia (tecla `F`; setas ou clique para navegar) e o app em outra aba, já carregado em <http://127.0.0.1:8000> via `.\scripts\serve.ps1`.

**Regra de fala:** dizer sempre "indício", "divergência" e "prioridade de fiscalização". Nunca afirmar "fraude", "ilegal" ou "crime" sobre um caso. Não ler em voz alta o número AUTEX completo.

| # | Slide | Tempo | Acumulado |
|---|---|---|---|
| 1 | Título | 0:15 | 0:15 |
| 2 | Problema | 0:30 | 0:45 |
| 3 | Insight | 0:30 | 1:15 |
| 4 | Dados | 0:20 | 1:35 |
| 5 | Método | 0:35 | 2:10 |
| 6 | Demo ao vivo | 1:20 | 3:30 |
| 7 | Resultados | 0:30 | 4:00 |
| 8 | Confiabilidade | 0:25 | 4:25 |
| 9 | Limites | 0:20 | 4:45 |
| 10 | Impacto | 0:15 | 5:00 |

---

### 1. Título (0:15)
"Este é o Lastro. Ele responde a uma pergunta simples: o volume de madeira que alguém declarou ter tirado da floresta tem lastro na floresta?"

### 2. Problema (0:30)
"Na Amazônia, madeira sem origem não precisa de documento falso. Basta um documento verdadeiro com volume a mais. O inventário superestima, sobra crédito, e esse crédito acompanha madeira de outro lugar. É o esquentamento, documentado em campo por Brancalion e colegas em 2018. Para dar escala: no Pará, a Rede Simex mapeou 32% da exploração madeireira do último ano sem autorização. O sistema confere o saldo. Ninguém confere se a árvore saiu daquela floresta."

### 3. Insight (0:30)
"Só que o IBAMA publica, em dados abertos, cada árvore declarada como explorada, com coordenada. No nosso polo são 329 mil árvores desde 2022. Se a árvore saiu, a floresta abriu. Então medimos, célula a célula de um hectare, se a abertura vista do satélite comporta o volume declarado. Um detalhe: o dado chega sem sinal e às vezes com latitude e longitude trocadas. Corrigimos e testamos isso antes de qualquer conta."

### 4. Dados (0:20)
"São cinco bases públicas e três perguntas: o que podia (Sinaflor, POA, AUTEX), o que diz que fez (IF100) e o que a floresta mostra (Sentinel-2 a 10 m, CBERS-4A a 2 m e os rótulos DETER e PRODES do INPE). Tudo converge na célula de um hectare."

### 5. Método (0:35)
"Quatro passos. Um: um detector LightGBM treinado só com rótulos do INPE, nunca com a declaração, para não ser circular. Dois: células de um hectare. Três: o distúrbio vira volume com faixa p10 a p90, com ajuste conformal e Monte Carlo por UPA. Quatro: sete assinaturas, cada uma com regra, limiar e fonte. A mais importante, a A, só abre quando o declarado passa do p90 da UPA inteira e a divergência está concentrada. O score só ordena a fila."

### 6. Demo ao vivo (1:20): sequência exata de cliques

> Trocar para a aba do app (Alt+Tab). Se o app não responder em 5 s, ir ao **Plano B**.

1. **Triagem** (já aberta em `#/`). "Esta é a fila do polo: 1.142 autorizações, ordenadas por prioridade." Mostrar o selo "Resultado experimental".
2. No filtro **"Qualquer indício"**, mostrar as opções e voltar. Marcar **"Só com imagem analisada"** e clicar no **1º caso** da lista. Caso exato: [a preencher após a regeneração do index; na versão preliminar era um POA em Candeias do Jamari].
3. **Dossiê.** Apontar o cabeçalho (AUTEX, área, validade) e o card **"O volume declarado tem lastro?"**, com as barras autorizado × declarado × estimado e a faixa p10–p90.
4. Arrastar o **divisor antes/depois** do mapa: "Sentinel-2 antes e depois da exploração."
5. Em **Indícios**, abrir **C (árvores fora do polígono)** e clicar na evidência **"ver no mapa"**: os pontos fora da UPA acendem. "Árvores declaradas fora do polígono autorizado, entre 20 m e 5 km do limite."
6. Abrir **E (fora da validade)**: "Datas de exploração declaradas depois do fim da validade."
7. Abrir **A** e ler o status (indício ou inconclusivo) com a regra. Se estiver inconclusivo: "Há blocos de células sem lastro, mas o total da UPA cabe no intervalo. O sistema não força a mão." [confirmar no index regenerado]
8. Clicar em **Confiabilidade** no topo e passar rápido pelos dois cards (detector e cobertura). Detalhes no próximo slide.
9. (Opcional, se sobrar tempo) **"Analisar autorização"**: digitar o mesmo AUTEX e mostrar que abre do acervo processado.

> Voltar ao deck (Alt+Tab) e avançar para o slide 7.

**Observação:** os 3 casos reais com imagem não têm recorte CBERS nesta execução. O alternador CBERS-4A 2 m aparece no caso de demonstração marcado como SIMULAÇÃO (screenshot do slide 6). Não prometer CBERS no caso real.

### 7. Resultados (0:30)
"No polo inteiro: 1.142 autorizações avaliadas, 46 com algum indício documental (11 com árvore fora do polígono, 10 acima do autorizado, 29 fora da validade) e 1,87 milhão de metros cúbicos declarados confrontados. Os números AUTEX estão mascarados no slide. No app eles são públicos, sem nome nem CNPJ."

### 8. Confiabilidade (0:25)
"Tudo foi medido em áreas que o modelo não viu. O detector dobra o IoU do baseline: 0,56 contra 0,28. E o intervalo de volume cobre o declarado em 83% das células para 80% esperados. Ou seja, quando dizemos p10 a p90, a faixa vale. O ponto central por célula é fraco, por isso nunca decidimos pela mediana."

### 9. Limites (0:20)
"É triagem, não acusação. A clareira de uma árvore fecha em meses; nuvem não vira prova de ausência; dado faltante vira 'não avaliado'. Cada indício mostra regra, limiar e fonte para revisão humana."

### 10. Impacto (0:15)
"Próximos passos: fila semanal para IBAMA e OEMAs, CBERS em todos os casos de topo, parceria de inventário em campo e deep learning, que já treinamos no Colab. O volume declarado tem lastro na floresta? Agora dá para perguntar, autorização por autorização."

---

## Plano B (sem app ou sem rede)

1. **Vídeo:** se existir `pitch/demo.mp4` (gravação Playwright da sequência acima), abrir em tela cheia no slide 6 e narrar os mesmos passos 1 a 8. O vídeo tem ~80 s.
2. **Sem vídeo:** ficar no slide 6 (screenshot do dossiê embutido) e narrar apontando: card de volume → indício A com regra e evidência → "ver no mapa". Em seguida, abrir os PNGs de `tests/web/screens/` (triagem, dossiê, confiabilidade, modal) no visualizador de imagens.
3. **Deck sem navegador moderno:** `deck.html` é autocontido (sem CDN e sem rede). Funciona em qualquer Chrome, Edge ou Firefox, offline.

## Perguntas prováveis da banca

- **"Isso não acusa quem está em dia?"** O sistema abre indício, não conclui. A só dispara com divergência no total da UPA acima do p90 **e** concentrada. [Citar o resultado do index regenerado.]
- **"Por que não árvore por árvore?"** A clareira de uma árvore tem de 200 a 600 m², é quase sub-pixel a 10 m e fecha em meses. Some-se o erro de GPS do IF100. Por isso a decisão é por célula de 1 ha e por UPA.
- **"E a nuvem?"** Célula com menos de 70% de pixels válidos é "não observável" e nunca vira evidência.
- **"O modelo foi treinado com a resposta?"** Não. O detector usa só rótulos do INPE. O IF100 entra apenas na calibração de volume, e com validação por UPA fora da amostra.
- **"Quanto confiar?"** Detector: IoU 0,56 (F1 0,72), validado espacialmente. Volume: cobertura de 83,5% para 80% nominais. O R² por célula é cerca de 0, por isso usamos faixas, não pontos.
