# LASTRO no Google Colab

1. Abra o Google Colab e envie **`lastro_dl.ipynb`** (Arquivo → Fazer upload de notebook). O notebook é autocontido: nenhum outro arquivo deste diretório é necessário.
2. Em Ambiente de execução → Alterar tipo de ambiente, escolha GPU T4, L4 ou A100. `MODO_RAPIDO=True` usa 400 chips e até 10 épocas; `False`, 1.000 chips e até 20 épocas. Metas aproximadas: 30 min / 2 h, não garantidas, sobretudo com cache vazio e WFS lento.
3. Opcionalmente substitua a lista `AOIS` pelos AUTEX, bboxes e datas fornecidos pelo orquestrador. O exemplo AMACRO já funciona. Datas finais são inclusivas; coordenadas das bboxes são longitude/latitude. Deixe `SALVAR_DRIVE=False` para não pedir autorização adicional.
4. Clique em Executar tudo e autentique o GEE com uma conta que tenha acesso ao projeto `project-f5ab0bff-aa9b-4cb2-97d`. Instalação, vetores, chips, split, treino, avaliação e inferência seguem automaticamente. Em caso de interrupção de rede, repita a execução: chips e vetores permanecem em `/content/chips` enquanto a sessão existir. A opção Drive copia o cache; para reaproveitá-lo numa sessão nova, restaure `MyDrive/lastro_chips` em `/content/chips`.
5. Baixe **`lastro_dl_resultados.zip`** no fim. Inclui `metrics_dl.json`, `config.json`, `split_manifest.json`, modelo LightGBM refeito nos chips, PNGs de teste, `prob_<autex>.tif` e `mask_<autex>.tif`. Se o navegador bloquear o download automático, baixe o zip pelo painel Arquivos do Colab.

## Protocolo e limites

Blocos de 25 km em UTM SIRGAS2000, 70/15/15 por bloco, seed 42. Um bloco pertence a um único conjunto em todos os anos; cada chip cabe inteiramente no bloco. AOIs configuradas são excluídas da amostragem. O split pode ter proporções diferentes em número de chips. Os três métodos usam exatamente os mesmos pixels observáveis de teste; Otsu usa apenas treino e o limiar LightGBM usa validação. Matriz de confusão: `[[TN, FP], [FN, TP]]`. Probabilidades sem observação: nodata `-9999`; máscara: `0`, `1`, nodata `255`.

PRODES/DETER são rótulos de monitoramento incompletos, especialmente para pequenas clareiras de manejo seletivo. Negativos exigem NDVI pré > 0,75 e ausência de histórico conhecido; pixels restantes não entram na loss/métrica. Essa máscara de supervisão **não** é passada ao modelo como máscara de entrada. A amostra contém pelo menos 50% de chips positivos, portanto suas métricas não medem prevalência regional. O ano PRODES e a janela DETER out/set não coincidem exatamente com as medianas jun/set. São indícios para priorizar fiscalização, nunca prova.

Prithvi é carregado via TerraTorch com dois frames de seis bandas e decoder convolucional de segmentação. Na T4, seleciona-se 100M por memória; GPUs com >=20 GB tentam 300M, depois 100M. Fine-tuning parcial dos últimos 2/4 blocos, precisão mista e early stopping. Falhas de instalação, API, execução ou memória acionam U-Net com encoder ResNet34 compartilhado entre pré/pós, pesos ImageNet e fusão de features. Cada escolha/erro fica em `config.json`. B8 a 10 m aproxima NIR narrow HLS; há mudança de domínio.

O LightGBM do notebook é um comparador treinado sobre estes chips. **Não é o artefato treinado pelo pipeline local.** A spec local usa cinco folds e blocos de 5 km: suas métricas não podem ser apresentadas como comparação direta. Para comparar o detector local, reutilizar `split_manifest.json` e os chips, sem reamostrar o teste. `lightgbm_mesmos_chips` é campo extra livre no JSON do notebook, sem alteração dos contratos compartilhados.

## Manutenção e verificação local

Somente `colab/` é alterada. Testes ficam nesta pasta para respeitar o escopo de escrita, apesar da convenção geral `tests/<area>/`.

```powershell
uv run --with nbformat python colab/build_notebook.py
uv run --with nbformat --with nbconvert python colab/check_local.py
uv run --with nbformat --with nbconvert python colab/check_local.py --real
uv run --with nbformat pytest colab/test_data.py -q
```

`build_notebook.py` incorpora `data_cells.py` e `train_cells.py` integralmente. `check_local.py --real` autentica com as credenciais GEE locais existentes, busca WFS real, baixa um chip e salva `check_chip.png` e `check_result.json`. Não instala PyTorch/TerraTorch nem executa treino local. `local_check/` é cache descartável; não precisa ser enviado ao Colab.

Referências: [TerraTorch/Prithvi](https://torchgeo.org/terratorch/1.2.10/guide/prithvi_eo/), [configuração e normalização oficial 300M-TL](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL/blob/main/config.json), [GEE computePixels](https://developers.google.com/earth-engine/apidocs/ee-data-computepixels), [TerraBrasilis](https://terrabrasilis.dpi.inpe.br/).
