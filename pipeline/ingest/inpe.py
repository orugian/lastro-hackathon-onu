import json
from datetime import datetime, timezone
import geopandas as gpd
from shapely import make_valid
from .common import OUT, BBOX, session

URL = 'https://terrabrasilis.dpi.inpe.br/geoserver/ows'

def download(name, layer, temporal, sort, force=False):
    features, offset = [], 0
    s = session()
    while True:
        params = dict(service='WFS',version='2.0.0',request='GetFeature',typeNames=layer,
            outputFormat='application/json',srsName='EPSG:4326',count=2000,startIndex=offset,
            sortBy=sort, CQL_FILTER=f"BBOX(geom,{','.join(map(str,BBOX))},'EPSG:4326') AND {temporal}")
        cache = OUT / 'inpe_cache' / f'{name}_{offset}.json'
        cache.parent.mkdir(exist_ok=True)
        if cache.exists() and not force:
            data = json.loads(cache.read_text(encoding='utf-8'))
        else:
            response = s.get(URL,params=params,timeout=180)
            response.raise_for_status()
            try: data = response.json()
            except ValueError: raise RuntimeError(response.text[:1000])
            cache.write_text(json.dumps(data),encoding='utf-8')
        batch = data['features']; features.extend(batch)
        print(name, 'features:',len(features),flush=True)
        if len(batch) < 2000: break
        offset += len(batch)
    df = gpd.GeoDataFrame.from_features(features,crs=4326) if features else gpd.GeoDataFrame(geometry=[],crs=4326)
    if not df.empty:
        def _fix(geom):
            if geom is None or geom.is_valid:
                return geom
            try:
                return make_valid(geom)
            except Exception:
                return geom.buffer(0)
        df.geometry = df.geometry.map(_fix)
        df = df[df.geometry.notna() & ~df.geometry.is_empty]
        if name == 'deter': df['classe'] = df.classname; df['data'] = df.view_date
        else: df['classe'] = df.class_name; df['ano'] = df.year
    df.to_parquet(OUT / f'{name}.parquet',index=False)
    (OUT / f'{name}.proveniencia.json').write_text(json.dumps(dict(url=URL,layer=layer,bbox=BBOX,filter=temporal,consultado_em=datetime.now(timezone.utc).isoformat(),count=len(df)),indent=2),encoding='utf-8')
    return df

def run(force=False):
    for name,layer,temporal,sort in [('deter','deter-amz:deter_amz',"view_date >= '2021-01-01'",'gid'),('prodes','prodes-legal-amz:yearly_deforestation','year >= 2021','fid')]:
        if force or not (OUT / f'{name}.parquet').exists(): download(name,layer,temporal,sort,force=force)
