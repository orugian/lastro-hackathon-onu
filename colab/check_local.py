"""Validação sintática e smoke test real de dados; nunca importa/roda o treino."""
import ast
import json
from pathlib import Path
import nbformat

HERE = Path(__file__).resolve().parent

def load_data_functions(root):
    source = (HERE/'data_cells.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    # Imports, constantes e funções das duas primeiras células; nenhum download global.
    source = source.split('# %% Download e amostragem')[0]
    source = source.replace("ROOT = Path('/content')",f'ROOT = Path({str(root)!r})')
    ns = {}
    exec(compile(source,str(HERE/'data_cells.py'),'exec'),ns)
    return ns

def syntax_check():
    nb = nbformat.read(HERE/'lastro_dl.ipynb',as_version=4)
    nbformat.validate(nb)
    count = 0
    for i,cell in enumerate(nb.cells):
        if cell.cell_type=='code':
            code = '\n'.join(line for line in cell.source.splitlines() if not line.lstrip().startswith(('!','%')))
            ast.parse(code,filename=f'cell_{i}')
            count += 1
    print(f'nbformat.validate OK; ast.parse OK: {count} células de código')

def real_chip_check():
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    ns = load_data_functions(HERE/'local_check')
    ee = ns['ee']
    ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')
    bbox = [-63.12,-7.64,-63.05,-7.58]
    # Apenas a pequena AOI no teste; notebook usa AMACRO inteira.
    labels,history = ns['load_labels'](bbox,[2024])
    print('WFS real: positivos 2024 =',len(labels[2024]),'; histórico =',len(history),flush=True)
    if labels[2024]:
        p = ns['shape'](labels[2024][0]['geometry']).representative_point()
        lon,lat = p.x,p.y
    else:
        lon,lat = -63.085,-7.61
    c = ns['candidate'](lon,lat,2024)
    im = ns['stack_image'](['2023-06-01','2023-09-30'],['2024-06-01','2024-09-30'],ee.Geometry.Rectangle(bbox))
    x,observed,affine = ns['download_chip'](im,c['x'],c['y'],c['epsg'])
    y = ns['rasterize_labels'](labels[2024],affine,c['epsg'])
    assert x.shape==(12,224,224) and y.shape==(224,224)
    assert observed.any() and np.isfinite(x).all()
    fig,axs = plt.subplots(1,3,figsize=(12,4))
    for ax,arr,title in zip(axs,[np.clip(x[[2,1,0]].transpose(1,2,0)/.3,0,1),
                               np.clip(x[[8,7,6]].transpose(1,2,0)/.3,0,1),y],
                            ['Pré jun–set/2023','Pós jun–set/2024','Rótulo PRODES + DETER / 2024']):
        ax.imshow(arr,vmin=0,vmax=1)
        ax.set_title(title)
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(HERE/'check_chip.png',dpi=150)
    plt.close(fig)
    np.savez_compressed(HERE/'local_check'/'chip_checked.npz',x=x,y=y,observed=observed)
    result = dict(shape=list(x.shape),positive_pixels=int(y.sum()),observed_pixels=int(observed.sum()),
                  valid_fraction=float(observed.mean()),epsg=c['epsg'],affine=list(affine),
                  labels_2024=len(labels[2024]),history_features=len(history),seed=42,
                  pre=['2023-06-01','2023-09-30'],pos=['2024-06-01','2024-09-30'],
                  treino_executado=False)
    (HERE/'check_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    import sys
    syntax_check()
    if '--real' in sys.argv:
        real_chip_check()
