"""Testes locais leves; mantidos em colab/ para respeitar o escopo de escrita."""
import numpy as np
import pytest
from check_local import load_data_functions

@pytest.fixture
def ns(tmp_path):
    return load_data_functions(tmp_path)

def test_rasterize_projected_exact_pixels(ns):
    from shapely.geometry import box, mapping
    from shapely.ops import transform
    from pyproj import Transformer
    from rasterio.transform import from_origin
    # Quadrado de 100 m x 100 m = 1 ha = 100 pixels a 10 m.
    g = transform(Transformer.from_crs(31980,4326,always_xy=True).transform,
                  box(500020,9159980,500120,9160080))
    features = [{'type':'Feature','geometry':mapping(g),'properties':{}}]
    a = from_origin(500000,9160100,10,10)
    y = ns['rasterize_labels'](features,a,31980,20)
    assert y.dtype == np.uint8
    assert y.sum() == 100
    assert y[2:12,2:12].all()
    assert ns['rasterize_labels']([],a,31980,20).sum()==0

def test_entire_chip_inside_block(ns):
    for lon in np.linspace(-65.99,-60.01,10):
        for lat in np.linspace(-9.99,-6.51,10):
            c = ns['candidate'](lon,lat,2024)
            ids = {ns['block_id'](x,y,c['epsg'])
                   for x in [c['x']+.001,c['x']+2239.999]
                   for y in [c['y']-.001,c['y']-2239.999]}
            assert ids == {c['bloco']}

def test_disjoint_and_reproducible_spatial_split(ns):
    blocks = [f'b{i}' for i in range(100)]*3
    split = ns['split_blocks'](blocks)
    assert split == ns['split_blocks'](blocks[::-1])
    assert {s:list(split.values()).count(s) for s in set(split.values())} == {'train':70,'val':15,'test':15}
    assert len(split)==100
    with pytest.raises(RuntimeError):
        ns['split_blocks'](['a','b'])

def test_download_chip_grid_and_nodata(ns,monkeypatch):
    received = {}
    names = ['pre_'+b for b in ns['BANDAS']]+['pos_'+b for b in ns['BANDAS']]+['valid']
    result = np.ones((224,224),dtype=[(n,'float32') for n in names])
    result['pre_B2'][0,0] = -9999
    result['valid'][0,1] = 0
    def compute(params):
        received.update(params)
        return result
    monkeypatch.setattr(ns['ee'].data,'computePixels',compute)
    x,valid,affine = ns['download_chip']('image',500000,9160000,31980)
    assert x.shape==(12,224,224)
    assert valid.sum()==224*224-2
    assert (x[:,:1,:2]==0).all()
    assert received['grid']['crsCode']=='EPSG:31980'
    assert affine.a==10 and affine.e==-10

def test_metrics_and_small_windows():
    import ast
    from pathlib import Path
    source = ast.parse((Path(__file__).parent/'train_cells.py').read_text(encoding='utf-8'))
    selected = [n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('metrics','window_starts')]
    ns = {'np':np,'SIZE':224}
    exec(compile(ast.Module(body=selected,type_ignores=[]),'functions','exec'),ns)
    m = ns['metrics'](np.array([[90,10],[5,15]]))
    assert m['iou']==.5 and m['n_pixels_teste']==120
    assert m['matriz_confusao']==[[90,10],[5,15]]
    for size in [1,100,224,225,400,1000]:
        covered = np.zeros(size,bool)
        for start in ns['window_starts'](size):
            covered[start:start+224] = True
        assert covered.all()
