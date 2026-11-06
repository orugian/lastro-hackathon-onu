"""Exporta pequeno stack real GEE para teste de integracao local."""
import json
from pathlib import Path
import ee,requests,rasterio
from pyproj import Transformer
from .dataset import stack,ROOT
from .common import BANDS

def main():
    ee.Initialize(project='project-f5ab0bff-aa9b-4cb2-97d')
    ix,iy,year=json.loads((ROOT/'manifest.json').read_text())['tiles'][0]
    inv=Transformer.from_crs(31980,4326,always_xy=True)
    bounds=[*inv.transform(ix*5000+1500,iy*5000+1500),*inv.transform(ix*5000+3500,iy*5000+3500)]
    region=ee.Geometry.Rectangle(bounds,geodesic=False); image=stack(year,region)
    url=image.unmask(-9999).getDownloadURL({'region':region,'scale':10,'crs':'EPSG:31980','format':'GEO_TIFF','filePerBand':False})
    r=requests.get(url,timeout=180); r.raise_for_status(); path=ROOT/'example_stack.tif'; path.write_bytes(r.content)
    with rasterio.open(path,'r+') as dst:
        dst.nodata=-9999
        for i,name in enumerate(BANDS,1): dst.set_band_description(i,name)
    print(path)
if __name__=='__main__': main()
