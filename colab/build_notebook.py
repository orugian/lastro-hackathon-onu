"""Gera notebook autocontido; arquivos *_cells.py são apenas fontes de manutenção."""
from pathlib import Path
import nbformat as nbf

HERE = Path(__file__).resolve().parent
nb = nbf.v4.new_notebook()
nb.cells = [nbf.v4.new_markdown_cell('''# LASTRO — segmentação experimental de distúrbio florestal
1. Envie este notebook ao Google Colab e selecione uma GPU T4, L4 ou A100.
2. Opcionalmente edite `AOIS`; o exemplo incluído funciona sem edição.
3. Clique em **Executar tudo**; autentique sua conta quando `ee.Authenticate()` abrir o fluxo GEE.
4. Use uma conta com acesso ao projeto `project-f5ab0bff-aa9b-4cb2-97d`.
5. `MODO_RAPIDO=True` usa 400 chips/até 10 épocas; duração depende da GPU e da rede.
6. Ao final, baixe `lastro_dl_resultados.zip`; cache opcional no Drive pede autorização adicional.
Resultados são indícios para priorizar fiscalização, nunca prova.''')]
nb.cells.append(nbf.v4.new_code_cell('''# Instalar sem alterar a instalação CUDA/PyTorch fornecida pelo Colab.
import subprocess, sys
subprocess.check_call([sys.executable,'-m','pip','install','-q',
    'earthengine-api','rasterio','geopandas','shapely>=2','pyproj','requests',
    'scikit-image','scikit-learn','lightgbm','matplotlib','segmentation-models-pytorch==0.5.0'])
TERRATORCH_INSTALL_ERROR = None
try:
    subprocess.check_call([sys.executable,'-m','pip','install','-q','terratorch==1.2.10'])
except Exception as exc:
    TERRATORCH_INSTALL_ERROR = str(exc)
    print('TerraTorch indisponível; fallback U-Net será usado:',exc)
'''))
for source in ['data_cells.py','train_cells.py']:
    for part in (HERE/source).read_text(encoding='utf-8').split('# %% ')[1:]:
        title,code = part.split('\n',1)
        nb.cells.append(nbf.v4.new_markdown_cell('## '+title))
        if title.startswith('Download e'):
            nb.cells.append(nbf.v4.new_code_cell("ee.Authenticate()\nee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')\nprint('GEE autenticado.')"))
        nb.cells.append(nbf.v4.new_code_cell(code.rstrip()))
nb.cells.append(nbf.v4.new_markdown_cell('''### Referências e limites
- [Prithvi EO / TerraTorch](https://torchgeo.org/terratorch/1.2.10/guide/prithvi_eo/)
- [Prithvi 300M-TL](https://huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL)
- [TerraBrasilis WFS](https://terrabrasilis.dpi.inpe.br/geoserver/ows)
- [GEE computePixels](https://developers.google.com/earth-engine/apidocs/ee-data-computepixels)

Rótulos de monitoramento são incompletos, sobretudo para manejo seletivo. O conjunto foi enriquecido em positivos e não mede a prevalência regional. O LightGBM incluído é treinado nestes mesmos chips; comparar diretamente com o detector local exige que este reutilize `split_manifest.json`. As métricas locais de cinco folds/5 km constituem outro experimento. O zip inclui protocolo, versões, erros de fallback e configuração. A máscara de observação usada como entrada é independente dos rótulos; a máscara de avaliação inclui apenas positivos conhecidos e negativos conservadores.'''))
nb.metadata = dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),
                   language_info=dict(name='python',version='3.11'),
                   colab=dict(name='lastro_dl.ipynb',provenance=[]),accelerator='GPU')
nbf.validate(nb)
nbf.write(nb,HERE/'lastro_dl.ipynb')
print(f'Notebook válido: {len(nb.cells)} células')
