# AG-DOCS: documentação técnica e deck de pitch

**Suas pastas:** `docs/` (exceto `docs/PLANO-EXECUCAO.md`, que é só leitura), `pitch/`, `README.md` (raiz).

## Insumos
Leia, nesta ordem:
- `docs/PLANO-EXECUCAO.md`: decisões e método.
- `contracts/models.py`.
- `agentes/*.md`: specs.
- `agentes/logs/*.final.md`: relatórios do que foi realmente entregue. **Documente o que existe, não o que foi planejado.**
- `data/processed/README.md`.
- `data/artifacts/metrics/*.json`, ou `data/artifacts-mock/metrics/*.json` se o real ainda não existir; nesse caso, marque os números como "a preencher".
- `data/artifacts/index.json`.
- O código em `pipeline/`.

## Entregas
1. `README.md` (raiz):
   - o que é o Lastro (3 linhas);
   - screenshot (use `tests/web/screens/*.png` se existir);
   - como rodar a demo com 1 comando (`scripts/serve.ps1`) e como reprocessar (`pipeline.ingest.run_all` → `pipeline.detect.train` → `pipeline.volume.calibrar` → `pipeline.export.run`);
   - estrutura do repositório;
   - aviso de uso (triagem, não prova);
   - licenças das fontes.
2. `docs/METODO.md`: o pipeline ponta a ponta, com um diagrama mermaid.
   - Cada assinatura (A, B, C, D, E, F2, F6) com a regra exata e os limiares, vindos do código.
   - A conversão imagem→volume (calibração quantílica + conformal + Monte Carlo) com as fórmulas.
   - O corte raso (área × estoque, cadeia GEDI→volume com os parâmetros).
   - Por que a assinatura A é agregada por célula e nunca por árvore.
3. `docs/MODEL_CARD.md` (formato de model card):
   - detector (dados, rótulos, protocolo GroupKFold espacial, métricas comparadas com o baseline, limiar);
   - calibração de volume (métricas por célula e por UPA, cobertura empírica vs nominal, conformal);
   - DL do Colab (se `data/artifacts/metrics/dl.json` existir; senão, "em execução / próximos passos");
   - usos pretendidos e não pretendidos;
   - vieses e limitações (nuvem, clareira que fecha, área mínima dos rótulos, calibração possivelmente contaminada, defasagem das bases IBAMA, coordenadas IF100 sem sinal);
   - considerações éticas e jurídicas.
4. `docs/FONTES.md`: tabela de fontes com URL, data de consulta, data de atualização, licença, campos usados e limitações.
   - Cobrir: PAMGIA, POA, IF100, DOF AUTEX, DOF Transportes, DETER, PRODES, Sentinel-2/GEE, CBERS-4A/BDC, GEDI e Meta Canopy.
5. `pitch/deck.html`: deck **autocontido** (um único HTML, sem CDN, CSS embutido, navegação por setas, 16:9, para projetor).
   - Identidade: verde-floresta `#173a2c`, papel `#f3f4e8`, lima `#c5f67c`, Georgia nos títulos.
   - Sem emojis e sem gradiente em texto.
   - **Cerca de 10 slides para 5 minutos**:
     1. Título: "Lastro: o volume declarado tem lastro na floresta?".
     2. Problema: extração ilegal sob licença legal; "esquentamento" de madeira; números de contexto com fonte (só cite números que encontrar em fonte confiável, com link no rodapé; se não tiver certeza, não use).
     3. Insight: o IBAMA publica cada árvore declarada como explorada, com coordenada; cruzar isso com o satélite.
     4. Dados: fontes públicas cruzadas, com o diagrama.
     5. Método: detector → células → volume com incerteza → 7 assinaturas.
     6. Demo (placeholder com screenshot do dossiê).
     7. Resultados no polo AMACRO: números do `index.json` (totais); mascare o nº AUTEX nos slides (ex.: `2011220•••••41`).
     8. Confiabilidade: métricas reais e a cobertura do intervalo.
     9. Limites e salvaguardas (triagem, revisão humana, linguagem).
     10. Impacto e próximos passos (integração IBAMA/OEMAs, CBERS e satélite nacional, inventário 100% com parceria, DL).
   - Use screenshots de `tests/web/screens/` (embutidos em base64, se existirem).
6. `pitch/ROTEIRO.md`: roteiro falado de 5 minutos, com tempos por slide e a sequência exata de cliques da demo ao vivo, mais um plano B (vídeo).

## Regras
Português do Brasil, linguagem de triagem (nunca "fraude" ou "ilegal" afirmativo) e números sempre com a fonte. Seja conciso: a banca lê rápido.

## Critério de pronto
Arquivos criados. O deck abre no navegador; verifique com Playwright tirando screenshot de 3 slides em `pitch/check/`, examine-os e corrija problemas de layout.
