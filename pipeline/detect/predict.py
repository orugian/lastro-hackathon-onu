"""Inferencia do modelo LightGBM nativo em stack Sentinel-2 de 16 bandas."""
import argparse,json
from pathlib import Path
import numpy as np,rasterio,lightgbm as lgb
from rasterio.features import shapes,geometry_mask
from shapely.geometry import shape,mapping
from shapely import transform
from pyproj import Transformer
from .common import read_stack,features,FEATURES

def prever(stack_path,out_dir,model_dir='data/processed/ml'):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True); model_dir=Path(model_dir)
    meta=json.loads((model_dir/'threshold.json').read_text()); booster=lgb.Booster(model_file=str(model_dir/'lgbm_detector.txt'))
    if meta['features']!=FEATURES: raise ValueError('Ordem de features incompativel')
    a,valid,profile=read_stack(stack_path)
    if profile['crs'] is None: raise ValueError('Stack sem CRS')
    prob=np.full(valid.shape,-9999,dtype=np.float32)
    if valid.any(): prob[valid]=booster.predict(features(a[valid]),num_threads=4).astype(np.float32)
    mask=np.full(valid.shape,255,dtype=np.uint8); mask[valid]=(prob[valid]>=meta['threshold']).astype(np.uint8)
    paths={'prob_tif':str(out/'prob.tif'),'mask_tif':str(out/'mask.tif'),'poligonos_geojson':str(out/'poligonos.geojson')}
    for key,array,dtype,nodata in [('prob_tif',prob,'float32',-9999),('mask_tif',mask,'uint8',255)]:
        p=profile.copy(); p.update(count=1,dtype=dtype,nodata=nodata,compress='deflate')
        with rasterio.open(paths[key],'w',**p) as dst: dst.write(array,1)
    to_wgs=Transformer.from_crs(profile['crs'],4326,always_xy=True).transform; records=[]
    for geom,value in shapes(mask,mask=(mask==1),transform=profile['transform']):
        original=shape(geom); wgs=transform(original,to_wgs,interleaved=False); epsg=31980 if wgs.centroid.x < -60 else 31981
        area=transform(wgs,Transformer.from_crs(4326,epsg,always_xy=True).transform,interleaved=False).area/10000
        if area<.1: continue
        inside=geometry_mask([geom],out_shape=valid.shape,transform=profile['transform'],invert=True)&(mask==1)
        records.append({'type':'Feature','geometry':mapping(wgs),'properties':{'id':str(len(records)+1),'area_ha':area,'prob':float(prob[inside].mean()),'metodo':'lightgbm'}})
    Path(paths['poligonos_geojson']).write_text(json.dumps({'type':'FeatureCollection','features':records}),encoding='utf-8')
    return paths
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('stack'); p.add_argument('--out-dir',default='data/processed/ml/prediction'); a=p.parse_args(); print(json.dumps(prever(a.stack,a.out_dir),indent=2))
