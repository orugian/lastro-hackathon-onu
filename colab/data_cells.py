# %% Configuração
from pathlib import Path
import os, json, random, time, hashlib, math, re
import numpy as np

MODO_RAPIDO = True
SEED = 42
N_CHIPS = 400 if MODO_RAPIDO else 1000
EPOCAS = 10 if MODO_RAPIDO else 20
WORKERS = 8
SALVAR_DRIVE = False  # True solicita também a autorização do Google Drive.
PROJECT = 'project-f5ab0bff-aa9b-4cb2-97d'
BBOX = [-66, -10, -60, -6.5]
ANOS = [2022, 2023, 2024]
BANDAS = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12']
SIZE, RES, BLOCK = 224, 10, 25000
ROOT = Path('/content')
CACHE = ROOT / 'chips'
OUT = ROOT / 'lastro_dl_resultados'
for p in (CACHE, OUT):
    p.mkdir(parents=True, exist_ok=True)
random.seed(SEED)
np.random.seed(SEED)
AOIS = [{"autex": "EXEMPLO-AMACRO", "bbox": [-63.12,-7.64,-63.05,-7.58],
         "pre": ["2023-06-01","2023-09-30"], "pos": ["2024-06-01","2024-09-30"]}]
CONFIG = dict(seed=SEED, modo_rapido=MODO_RAPIDO, n_chips_alvo=N_CHIPS,
              epocas_max=EPOCAS, workers=WORKERS, bbox=BBOX, anos=ANOS,
              bandas=BANDAS, chip_px=SIZE, resolucao_m=RES, bloco_m=BLOCK,
              projeto=PROJECT, aois=AOIS, cloud_probability_lt=40,
              split=[0.70,0.15,0.15], threshold=0.5)

# %% Funções de dados (também usadas no teste local)
import requests
import ee
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from pyproj import Transformer
from shapely.geometry import shape, box, mapping
from shapely.ops import transform as geom_transform
from shapely import make_valid
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

WFS = 'https://terrabrasilis.dpi.inpe.br/geoserver/ows'
CLASSES = ['CS_DESORDENADO','CS_GEOMETRICO','DEGRADACAO','DESMATAMENTO_CR']

def retry(fn, attempts=4):
    for attempt in range(attempts):
        try:
            return fn()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)

def wfs_features(layer, bbox, condition, cache_dir=CACHE):
    """Paginação estável; erro de rede nunca vira conjunto vazio de rótulos."""
    clause = f"BBOX(geom,{','.join(map(str,bbox))},'EPSG:4326') AND ({condition})"
    key = hashlib.sha256((layer + clause).encode()).hexdigest()[:20]
    path = cache_dir / f'wfs_{key}.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    features, seen, start = [], set(), 0
    while True:
        params = dict(service='WFS', version='2.0.0', request='GetFeature',
                      typeNames=layer, outputFormat='application/json',
                      srsName='EPSG:4326', CQL_FILTER=clause,
                      count=2000, startIndex=start, sortBy='fid' if 'prodes' in layer else 'gid')
        def fetch():
            r = requests.get(WFS, params=params, timeout=(20,180))
            r.raise_for_status()
            data = r.json()
            if 'features' not in data:
                raise RuntimeError(str(data)[:500])
            return data
        data = retry(fetch)
        page = data['features']
        if not page:
            break
        fresh = [f for f in page if f['id'] not in seen]
        if not fresh:
            raise RuntimeError('WFS repetiu a página: paginação não confiável.')
        features.extend(fresh)
        seen.update(f['id'] for f in fresh)
        start += len(page)
        total = data.get('numberMatched', data.get('totalFeatures'))
        if isinstance(total, int) and start >= total:
            break
        if len(page) < 2000:
            break
    path.write_text(json.dumps(features), encoding='utf-8')
    return features

def load_labels(bbox, years=ANOS):
    # Histórico também exclui negativos em áreas de distúrbio conhecido.
    prodes = wfs_features('prodes-legal-amz:yearly_deforestation', bbox,
                         f'year >= 2008 AND year <= {max(years)}')
    classes = ','.join("'" + c + "'" for c in CLASSES)
    deter = wfs_features('deter-amz:deter_amz', bbox,
                        f"view_date >= '2008-01-01' AND view_date < '{max(years)+1}-01-01'")
    labels = {}
    for year in years:
        labels[year] = [f for f in prodes if int(f['properties']['year']) == year]
        labels[year] += [f for f in deter
                        if f['properties'].get('classname') in CLASSES
                        and f'{year-1}-10-01' <= str(f['properties'].get('view_date',''))[:10] <= f'{year}-09-30']
    return labels, prodes + deter

def utm_epsg(lon):
    return 31980 if lon < -60 else 31981

def rasterize_labels(features, transform, crs, size=SIZE):
    bounds = rasterio.transform.array_bounds(size, size, transform)
    footprint = box(*bounds)
    project = Transformer.from_crs('EPSG:4326', crs, always_xy=True).transform
    geometries = []
    for feature in features:
        if not feature.get('geometry'):
            continue
        g = geom_transform(project, make_valid(shape(feature['geometry'])))
        if g.intersects(footprint):
            geometries.append((mapping(g), 1))
    return rasterize(geometries, out_shape=(size,size), transform=transform,
                     fill=0, dtype='uint8') if geometries else np.zeros((size,size), np.uint8)

def composite(start, end, region):
    # Datas finais inclusivas na interface, exclusivas no Earth Engine.
    end_exclusive = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    sr = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region).filterDate(start,end_exclusive)
    clouds = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY').filterBounds(region).filterDate(start,end_exclusive)
    joined = ee.Join.saveFirst('clouds').apply(sr, clouds, ee.Filter.equals(leftField='system:index', rightField='system:index'))
    def clean(im):
        im = ee.Image(im)
        scl = im.select('SCL')
        mask = ee.Image(im.get('clouds')).select('probability').lt(40)
        mask = mask.And(scl.neq(0)).And(scl.neq(1)).And(scl.neq(3)).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
        # Máscaras de borda nas bandas de 20/60 m.
        mask = mask.And(im.select('B8A').mask()).And(im.select('B9').mask())
        return im.select(BANDAS).updateMask(mask).multiply(0.0001).toFloat()
    return ee.ImageCollection(joined).map(clean).median()

def stack_image(pre, pos, region):
    a, b = composite(*pre,region), composite(*pos,region)
    names = ['pre_'+x for x in BANDAS] + ['pos_'+x for x in BANDAS]
    im = a.addBands(b).rename(names)
    valid = im.mask().reduce(ee.Reducer.min()).rename('valid')
    return im.unmask(-9999).addBands(valid.unmask(0)).toFloat()

def download_chip(image, x, y, epsg, size=SIZE):
    """x,y = canto superior esquerdo UTM; retorno CHW, máscara e affine."""
    result = retry(lambda: ee.data.computePixels(dict(
        expression=image, fileFormat='NUMPY_NDARRAY',
        grid=dict(dimensions=dict(width=size,height=size),
                  affineTransform=dict(scaleX=RES,shearX=0,translateX=float(x),
                                       shearY=0,scaleY=-RES,translateY=float(y)),
                  crsCode=f'EPSG:{epsg}'))))
    bands = ['pre_'+b for b in BANDAS] + ['pos_'+b for b in BANDAS]
    arr = np.stack([result[b] for b in bands]).astype('float32')
    valid = (result['valid'] > 0) & np.isfinite(arr).all(axis=0) & (arr != -9999).all(axis=0)
    arr[:,~valid] = 0
    return arr, valid, from_origin(x,y,RES,RES)

def ndvi(x, offset=0):
    return (x[offset+3]-x[offset+2]) / (x[offset+3]+x[offset+2]+1e-6)

def block_id(x,y,epsg=31980):
    return f'{epsg}_{math.floor(x/BLOCK)}_{math.floor(y/BLOCK)}'

def candidate(lon,lat,year):
    epsg = utm_epsg(lon)
    x,y = Transformer.from_crs(4326,epsg,always_xy=True).transform(lon,lat)
    # Mantém footprint inteiro dentro de um único bloco; sem sobreposição entre splits.
    bx,by = math.floor(x/BLOCK)*BLOCK, math.floor(y/BLOCK)*BLOCK
    left = max(bx, min(bx+BLOCK-SIZE*RES, math.floor((x-SIZE*RES/2)/RES)*RES))
    top = max(by+SIZE*RES, min(by+BLOCK, math.ceil((y+SIZE*RES/2)/RES)*RES))
    return dict(year=int(year), x=left,y=top,epsg=epsg,bloco=block_id(x,y,epsg))

def split_blocks(blocks):
    unique = sorted(set(blocks))
    if len(unique) < 7:
        raise RuntimeError('Menos de 7 blocos espaciais: ampliar a amostragem.')
    np.random.default_rng(SEED).shuffle(unique)
    ntest = max(1, round(len(unique)*.15))
    nval = max(1, round(len(unique)*.15))
    return {b: ('test' if i<ntest else 'val' if i<ntest+nval else 'train') for i,b in enumerate(unique)}

# %% Download e amostragem
labels, history = load_labels(BBOX)
print('Rótulos por ano:', {y:len(v) for y,v in labels.items()})
import geopandas as gpd
label_frames = {y:gpd.GeoDataFrame.from_features(fs,crs=4326) for y,fs in labels.items()}
history_frame = gpd.GeoDataFrame.from_features(history,crs=4326)
images = {y:stack_image([f'{y-1}-06-01',f'{y-1}-09-30'],
                        [f'{y}-06-01',f'{y}-09-30'], ee.Geometry.Rectangle(BBOX)) for y in ANOS}
rng = np.random.default_rng(SEED)
demo_boxes = [box(*a['bbox']) for a in AOIS]

def nearby(frame, bbox):
    indices = frame.sindex.query(box(*bbox), predicate='intersects')
    return json.loads(frame.iloc[indices].to_json())['features']

def materialize(c):
    key = hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()[:18]
    path = CACHE / f'chip_v3_{key}.npz'
    affine = from_origin(c['x'],c['y'],RES,RES)
    bounds = rasterio.transform.array_bounds(SIZE,SIZE,affine)
    geo = geom_transform(Transformer.from_crs(c['epsg'],4326,always_xy=True).transform,box(*bounds))
    if not box(*BBOX).covers(geo) or any(geo.intersects(d) for d in demo_boxes):
        return None
    if path.exists():
        with np.load(path) as z:
            positive, frac = bool(z['positive']), float(z['valid'].mean())
    else:
        x,observed,affine = download_chip(images[c['year']],c['x'],c['y'],c['epsg'])
        y = rasterize_labels(nearby(label_frames[c['year']],geo.bounds),affine,c['epsg'])
        known = rasterize_labels(nearby(history_frame,geo.bounds),affine,c['epsg'])
        # Não rotulado não significa floresta intacta. Avaliar negativos conservadores.
        valid = observed & ((y == 1) | ((known == 0) & (ndvi(x) > .75)))
        positive, frac = bool((y[valid] == 1).any()), float(valid.mean())
        np.savez_compressed(path,x=x,y=y,valid=valid,observed=observed,positive=positive)
    if frac < .25:
        return None
    return dict(c,path=str(path),positive=positive,valid_fraction=frac,chip_id=key)

positive_pool = [(year,f) for year,fs in labels.items() for f in fs]
if not positive_pool:
    raise RuntimeError('Nenhum rótulo positivo: verificar WFS, sem criar dados simulados.')
records, used = [], set()
failures = []
for round_id in range(12):
    missing = N_CHIPS-len(records)
    if missing <= 0:
        break
    candidates = []
    for i in range(max(32,int(missing*1.4))):
        if i % 4 != 0 or sum(r['positive'] for r in records) < N_CHIPS//2:
            year,f = positive_pool[int(rng.integers(len(positive_pool)))]
            p = shape(f['geometry']).representative_point()
            lon,lat = p.x,p.y
        else:
            year = int(rng.choice(ANOS))
            lon,lat = rng.uniform(BBOX[0],BBOX[2]),rng.uniform(BBOX[1],BBOX[3])
        c = candidate(lon,lat,year)
        key = (c['year'],c['x'],c['y'],c['epsg'])
        if key not in used:
            candidates.append(c)
            used.add(key)
    # executor.map mantém ordem determinística, independentemente da latência.
    def safe(c):
        try:
            return materialize(c)
        except Exception as exc:
            failures.append(str(exc)[:300])
            return None
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for result in pool.map(safe,candidates):
            if result is not None and len(records)<N_CHIPS:
                if not result['positive'] and sum(not r['positive'] for r in records)>=N_CHIPS//2:
                    continue
                records.append(result)
    print(f'Rodada {round_id+1}: {len(records)}/{N_CHIPS} chips; erros={len(failures)}')
if len(records)<N_CHIPS or sum(r['positive'] for r in records)<len(records)/2:
    raise RuntimeError(f'Meta de chips não atingida; cache preservado. Últimos erros: {failures[-3:]}')
assignment = split_blocks([r['bloco'] for r in records])
for r in records:
    r['split'] = assignment[r['bloco']]
for subset in ['train','val','test']:
    selected = [r for r in records if r['split']==subset]
    if not selected or not any(r['positive'] for r in selected):
        raise RuntimeError(f'Split {subset} sem positivos: não reportar métricas degeneradas.')
    print(subset,len(selected),'chips',len({r['bloco'] for r in selected}),'blocos')
(OUT/'split_manifest.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
CONFIG.update(n_chips=len(records),positive_chips=sum(r['positive'] for r in records),download_errors=failures)
if SALVAR_DRIVE:
    from google.colab import drive
    import shutil
    drive.mount('/content/drive')
    shutil.copytree(CACHE,'/content/drive/MyDrive/lastro_chips',dirs_exist_ok=True)
