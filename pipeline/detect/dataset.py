"""Amostragem real GEE/INPE, cache por tile e exclusao historica de negativos."""
import argparse,json,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import ee,requests,numpy as np,pandas as pd
from pyproj import Transformer
from shapely.geometry import shape,box,mapping
from .common import BANDS
from pipeline.imagery.s2 import initialize
ROOT=Path('data/processed/ml'); URL='https://terrabrasilis.dpi.inpe.br/geoserver/ows'
LAYERS={'deter':'deter-amz:deter_amz','prodes':'prodes-legal-amz:yearly_deforestation'}
def demo_exclusion():
    """Buffer de 2 km das autorizacoes presentes na pre-triagem, em metros."""
    pre=Path('data/processed/pretriagem.csv')
    if not pre.exists():
        return None,'pretriagem.csv ausente na selecao; sobreposicao com demo nao verificada'
    import geopandas as gpd
    ranking=pd.read_csv(pre,dtype={'autex':str})
    polygons=gpd.read_parquet('data/processed/autorizacoes.parquet')
    polygons['autex']=polygons['autex'].astype(str)
    selected=polygons[polygons.autex.isin(ranking.autex.astype(str))]
    missing=set(ranking.autex.astype(str))-set(selected.autex)
    if missing: raise ValueError(f'AOIs demo sem geometria: {sorted(missing)}')
    if selected.geometry.isna().any() or selected.geometry.is_empty.any():
        raise ValueError('AOI demo vazia')
    exclusion=selected.to_crs(31980).geometry.buffer(2000).union_all()
    return exclusion,f'{len(selected)} autorizacoes de pretriagem.csv excluidas com buffer de 2 km'

def exclude_demo_rows(df):
    exclusion,note=demo_exclusion()
    if exclusion is None: return df,note
    blocked=[]
    for block in df.bloco.unique():
        ix,iy=map(int,block.split('_'))
        if box(ix*5000,iy*5000,(ix+1)*5000,(iy+1)*5000).intersects(exclusion): blocked.append(block)
    return df[~df.bloco.isin(blocked)].copy(),note+f'; {len(blocked)} blocos removidos'
def wfs(kind,bounds,extra=''):
    filt='BBOX(geom,'+','.join(map(str,bounds))+",'EPSG:4326')"+(' AND '+extra if extra else '')
    records=[]
    for start in range(0,200000,2000):
        r=requests.get(URL,params=dict(service='WFS',version='2.0.0',request='GetFeature',typeNames=LAYERS[kind],outputFormat='application/json',srsName='EPSG:4326',count=2000,startIndex=start,CQL_FILTER=filt),timeout=180)
        r.raise_for_status(); data=r.json(); records+=data['features']
        if len(data['features'])<2000: break
    else: raise RuntimeError('WFS truncado')
    return records

def composite(year,region):
    sr=ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(region).filterDate(f'{year}-06-01',f'{year}-10-01')
    clouds=ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY').filterBounds(region).filterDate(f'{year}-06-01',f'{year}-10-01')
    joined=ee.ImageCollection(ee.Join.saveFirst('cloud').apply(sr,clouds,ee.Filter.equals(leftField='system:index',rightField='system:index')))
    def clean(im):
        scl=im.select('SCL'); mask=ee.Image(im.get('cloud')).select('probability').lt(40)
        for c in [0,1,3,8,9,10,11]: mask=mask.And(scl.neq(c))
        return im.select(['B2','B3','B4','B8','B11','B12']).multiply(.0001).updateMask(mask)
    return joined.map(clean).median()
def stack(year,region):
    pre=composite(year-1,region); post=composite(year,region)
    ds=[]
    for name,b in [('NDVI','B4'),('NBR','B12'),('NDMI','B11')]:
        ds.append(post.normalizedDifference(['B8',b]).subtract(pre.normalizedDifference(['B8',b])).rename('d'+name))
    out=pre.rename(BANDS[:6]).addBands(post.rename(BANDS[6:12])).addBands(ds)
    return out.addBands(out.mask().reduce(ee.Reducer.min()).rename('valid_mask')).toFloat()
def raster(features):
    fc=ee.FeatureCollection([ee.Feature(ee.Geometry(f['geometry']),{}) for f in features])
    return ee.Image(0).byte().paint(fc,1)
def tile_job(item):
    ix,iy,year=item; bid=f'{ix}_{iy}'; cache=ROOT/f'tile_{bid}_{year}.parquet'
    if cache.exists(): return pd.read_parquet(cache)
    inv=Transformer.from_crs(31980,4326,always_xy=True)
    bounds=(*inv.transform(ix*5000,iy*5000),*inv.transform((ix+1)*5000,(iy+1)*5000))
    region=ee.Geometry.Rectangle(list(bounds),geodesic=False)
    det=wfs('deter',bounds); pro=wfs('prodes',bounds)
    (ROOT/f'labels_{bid}.json').write_text(json.dumps({'deter':det,'prodes':pro}))
    cr=[f for f in pro if int(f['properties'].get('year') or 0)==year]
    selective=[]
    for f in det:
        p=f['properties']; date=str(p.get('view_date',''))[:10]
        if f'{year-1}-10-01'<=date<f'{year}-10-01':
            if p.get('classname') in ['CS_DESORDENADO','CS_GEOMETRICO','DEGRADACAO']: selective.append(f)
            elif p.get('classname')=='DESMATAMENTO_CR': cr.append(f)
    if not cr and not selective: return pd.DataFrame()
    image=stack(year,region)
    exclusion=raster(det+[f for f in pro if int(f['properties'].get('year') or 0)>=2008])
    stable=image.normalizedDifference(['pre_B8','pre_B4']).gt(.75).And(exclusion.eq(0))
    labels=ee.Image(0).where(raster(cr).eq(1),1).where(raster(selective).eq(1),2).rename('label').byte()
    valid=stable.Or(labels.gt(0)).And(image.select('valid_mask').gt(0))
    # Otsu per full tile; same spatial opening as inference, before sampling.
    score=image.select('dNDVI').add(image.select('dNBR')).multiply(-.5).clamp(0,1).rename('score')
    hist=score.reduceRegion(ee.Reducer.histogram(128),region,10,maxPixels=500000,tileScale=4).getInfo()['score']
    counts=np.array(hist['histogram']); means=np.array(hist['bucketMeans']); weights=np.cumsum(counts); sums=np.cumsum(counts*means)
    between=(sums[-1]*weights-sums*weights[-1])**2/np.maximum(weights*(weights[-1]-weights),1)
    threshold=float(means[int(np.argmax(between[:-1]))]) if len(means)>1 else float(means[0])
    baseline=score.gt(threshold).focalMin(1,'square','pixels').focalMax(1,'square','pixels').rename('baseline')
    sample=image.addBands(labels).addBands(baseline).updateMask(valid).stratifiedSample(numPoints=0,classBand='label',classValues=[0,1,2],classPoints=[1000,500,500],region=region,scale=10,projection='EPSG:31980',seed=42,tileScale=4,geometries=False).getInfo()
    df=pd.DataFrame([f['properties'] for f in sample['features']]); df['bloco']=bid; df['year']=year; df['baseline_threshold']=threshold
    df.to_parquet(cache,index=False); print(bid,year,len(df),flush=True); return df

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--tiles',type=int,default=36); args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True); initialize()
    seeds_path=ROOT/'seeds.json'
    if seeds_path.exists(): seeds=json.loads(seeds_path.read_text())
    else:
        seeds=wfs('deter',(-66,-10,-60,-6.5),"view_date >= '2021-10-01' AND view_date < '2024-10-01' AND classname IN ('CS_DESORDENADO','CS_GEOMETRICO','DEGRADACAO','DESMATAMENTO_CR')")
        seeds_path.write_text(json.dumps(seeds))
    transform=Transformer.from_crs(4326,31980,always_xy=True); candidates={}
    for f in seeds:
        p=shape(f['geometry']).representative_point(); x,y=transform.transform(p.x,p.y); date=f['properties']['view_date']; year=int(date[:4])+(int(date[5:7])>=10)
        key=(int(x//5000),int(y//5000),year)
        candidates[key]=candidates.get(key,0)+(5 if f['properties']['classname']!='DESMATAMENTO_CR' else 1)
    # Fixed geography across years always uses same bloco.
    exclusion,exclusion_note=demo_exclusion()
    ordered=sorted(candidates,key=lambda k:(-candidates[k],k)); chosen=[]; seen=set()
    for yr in [2022,2023,2024]:
        for k in ordered:
            if k[2]==yr and k[:2] not in seen:
                if exclusion is not None and box(k[0]*5000,k[1]*5000,(k[0]+1)*5000,(k[1]+1)*5000).intersects(exclusion): continue
                chosen.append(k); seen.add(k[:2])
                if sum(v[2]==yr for v in chosen)>=args.tiles//3: break
    (ROOT/'manifest.json').write_text(json.dumps({'tiles':chosen,'demo_exclusion':exclusion_note,'source_mode':'real','delta':'pos-pre'}))
    results=[]; errors=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(tile_job,k):k for k in chosen}
        for future in as_completed(jobs):
            try: results.append(future.result())
            except Exception as e: errors.append([jobs[future],str(e)]); print('ERROR',jobs[future],str(e)[:400],flush=True)
    (ROOT/'errors.json').write_text(json.dumps(errors))
    if not results: raise RuntimeError('Nenhum tile amostrado')
    df=pd.concat(results,ignore_index=True); df.to_parquet(ROOT/'dataset.parquet',index=False); print('DATASET',df.shape,df.label.value_counts().to_dict(),flush=True)
if __name__=='__main__': main()
